"""模型训练服务 - 从历史赛事数据中训练模型，并保存训练记录与数据建议。"""

import json
import logging
import time
from datetime import datetime, date
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from db.database import SessionLocal
from db.models import Match, Team, League, Player, MatchPlayerStat, TrainingRecord, User
from services.train_lock import lock_settings, train_lock

logger = logging.getLogger(__name__)

_BUSY = {"status": "error", "code": "TRAIN_BUSY", "message": "训练正在进行中"}
_sweep_guard_at = 0.0


class TrainingAborted(Exception):
    """训练被中止：提交者账号被禁用/删除，或服务关闭。

    与一般异常区分开，避免被记成"训练失败"并生成误导性的建议快照。
    """


class TrainingUserDisabled(TrainingAborted):
    """提交者账号在训练期间被禁用，应停止落库并标记取消。"""


def _record_age_seconds(started, now: datetime) -> float:
    if started is None:
        return lock_settings()["stale_running_seconds"] + 1
    if isinstance(started, str):
        try:
            started = datetime.fromisoformat(started)
        except ValueError:
            return lock_settings()["stale_running_seconds"] + 1
    try:
        return max(0.0, (now - started).total_seconds())
    except TypeError:
        return lock_settings()["stale_running_seconds"] + 1


class TrainingService:
    def __init__(self):
        import threading
        self.is_training = False
        self.training_progress = 0
        self.training_message = ""
        self.current_record_id = None
        self._phase = "idle"
        self._held_token = None
        self._train_thread = None
        self._train_lock = threading.Lock()
        self._aborting = False

    def training_in_progress(self) -> bool:
        """本进程或其它进程（Redis 锁）是否正在训练。"""
        if self.is_training:
            return True
        return train_lock.is_locked()

    def _report(self, progress=None, message=None, *, is_training=None, phase=None, record_id=None):
        if progress is not None:
            self.training_progress = progress
        if message is not None:
            self.training_message = message
        if is_training is not None:
            self.is_training = is_training
        if phase is not None:
            self._phase = phase
        if record_id is not None:
            self.current_record_id = record_id
        train_lock.write_status({
            "is_training": bool(self.is_training),
            "progress": int(self.training_progress or 0),
            "message": self.training_message or "",
            "current_record_id": self.current_record_id,
            "phase": self._phase,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })

    def _claim_lock(self, lock_token: str = None) -> str:
        token = lock_token or self._held_token
        if token and train_lock.refresh(token):
            self._held_token = token
            return token
        token = train_lock.acquire()
        if not token:
            return None
        self._held_token = token
        return token

    def _release_claimed_lock(self):
        token = self._held_token
        self._held_token = None
        if token:
            train_lock.release(token)

    def run_train_or_skip(self, start_date: date = None, end_date: date = None) -> dict:
        """调度 / P0 / 补齐任务：锁被占用时跳过，不把整次采集记为失败。"""
        result = self.train_all(start_date=start_date, end_date=end_date)
        if isinstance(result, dict) and result.get("code") == "TRAIN_BUSY":
            return {"status": "skipped", "message": "训练正在进行中，本次跳过"}
        return result or {"status": "failed", "message": "训练无返回"}

    def start_train_async(self, start_date: date = None, end_date: date = None, user_id: int = None) -> dict:
        """在独立线程中启动 train_all，避免占用 FastAPI 事件循环。"""
        import threading

        with self._train_lock:
            if self._train_thread and self._train_thread.is_alive():
                return dict(_BUSY)
            token = self._claim_lock(None)
            if not token:
                return dict(_BUSY)
            self._aborting = False
            if user_id:
                train_lock.set_queued_user(int(user_id))
            self._report(progress=0, message="训练排队启动中...", is_training=True, phase="starting")

            def _runner():
                try:
                    self.train_all(
                        start_date=start_date,
                        end_date=end_date,
                        lock_token=token,
                        _already_locked=True,
                    )
                except Exception as e:
                    logger.exception("异步训练线程异常: %s", e)
                    self._report(message=f"训练失败: {e}", is_training=False, phase="failed")
                    self._release_claimed_lock()

            # daemon：进程退出不等待训练结束；退出前由 abort_for_shutdown 收口记录并释放锁
            self._train_thread = threading.Thread(
                target=_runner, name="traesolo-train-all", daemon=True
            )
            self._train_thread.start()
        return {"status": "started", "message": "训练已在后台线程启动"}

    def train_all(
        self,
        start_date: date = None,
        end_date: date = None,
        lock_token: str = None,
        _already_locked: bool = False,
    ) -> dict:
        """训练所有模型并写入训练记录。抢不到分布式锁时返回 TRAIN_BUSY。"""
        token = self._claim_lock(lock_token if (lock_token or _already_locked) else None)
        if not token:
            if _already_locked:
                self._report(message="训练正在进行中", is_training=False, phase="idle")
            return dict(_BUSY)

        self._aborting = False
        started = datetime.now()
        record_id = None
        try:
            train_lock.start_heartbeat(token)
            self._report(progress=0, message="开始训练...", is_training=True, phase="running")
            record_id = self._create_record()
            self._report(record_id=record_id)
            db = SessionLocal()
            try:
                matches = self._get_training_data(db, start_date, end_date)
                if not matches:
                    snapshot, suggestions = self._build_training_insights(
                        db, matches=[], results={}, record_id=record_id,
                    )
                    result = {
                        "status": "failed",
                        "message": "没有找到已完赛的训练数据",
                        "results": {},
                        "suggestions": suggestions,
                        "snapshot": snapshot,
                        "total_matches": 0,
                    }
                    self._finish_record(record_id, result, started, suggestions, snapshot)
                    self._report(message=result["message"], progress=100, is_training=False, phase="failed")
                    return result

                logger.info("开始训练，使用 %s 场历史比赛数据", len(matches))

                # 数据加载是整条流水线里最重的一次 DB 往返，先在这里卡一道：
                # 提交者被禁用时立刻停，不进模型训练也不写任何参数。
                self._assert_runner_allowed(db)

                results = {}
                self._report(message="训练 ELO 模型（全局+分联赛 K/主场）...", progress=10)
                results["elo"] = self._train_elo_model(db, matches)

                self._assert_runner_allowed(db)
                self._report(message="训练 泊松模型...", progress=40)
                results["poisson"] = self._train_poisson_model(db, matches)

                self._assert_runner_allowed(db)
                self._report(message="训练 xG 模型...", progress=55)
                results["xg"] = self._train_xg_model(db, matches)

                # 三个模型都算完了，但还没落库——这是最后一个安全卡点。
                self._assert_runner_allowed(db)
                self._report(message="持久化球队/联赛参数...", progress=70)
                results["persist"] = self._persist_trained_params(db, results)

                self._assert_runner_allowed(db)
                self._report(message="训练融合模型（分联赛权重+主场超参）...", progress=80)
                results["ensemble"] = self._train_ensemble_model(db, matches)

                self._report(message="分析数据质量并生成建议...", progress=92)
                snapshot, suggestions = self._build_training_insights(
                    db, matches=matches, results=results, record_id=record_id,
                )

                self._assert_runner_allowed(db)
                self._report(message="保存训练结果...", progress=95)
                version = self._save_training_results(db, results, matches)

                data_start = matches[0].match_date if matches else None
                data_end = matches[-1].match_date if matches else None
                result = {
                    "status": "success",
                    "message": "所有模型训练完成",
                    "results": results,
                    "suggestions": suggestions,
                    "snapshot": snapshot,
                    "total_matches": len(matches),
                    "model_version": version,
                    "data_start": data_start.isoformat() if data_start else None,
                    "data_end": data_end.isoformat() if data_end else None,
                    "trained_at": datetime.now().isoformat(),
                }
                self._finish_record(record_id, result, started, suggestions, snapshot, matches)

                # P0：训练成功后自动按新模型补齐未赛预测 meta
                self._report(message="同步未赛预测 meta...", progress=98)
                try:
                    from services.prediction_refresh import refresh_stale_upcoming
                    refresh = refresh_stale_upcoming(
                        limit=300, only_stale=True, include_unpredicted=True
                    )
                    result["prediction_refresh"] = refresh
                    result["message"] = (
                        f"所有模型训练完成，并已同步 {refresh.get('calculated', 0)} 场未赛预测"
                    )
                except Exception as e:
                    logger.warning("训练后自动同步未赛预测失败: %s", e)
                    result["prediction_refresh"] = {
                        "calculated": 0,
                        "error": str(e),
                    }

                self._report(message=result["message"], progress=100, phase="done")
                return result
            finally:
                db.close()
        except TrainingAborted as e:
            # 账号被禁用/删除或服务关闭导致的主动中止：
            # 不能走"训练失败"路径，否则会生成误导性的错误建议快照。
            logger.info("训练中止: %s", e)
            if record_id:
                self._mark_running_failed(record_id, str(e))
            self._report(message=str(e), is_training=False, phase="aborted")
            return {"status": "aborted", "code": "TRAINING_ABORTED", "message": str(e)}
        except Exception as e:
            logger.error("训练失败: %s", e)
            snapshot, suggestions = {}, []
            try:
                db = SessionLocal()
                try:
                    snapshot, suggestions = self._build_training_insights(
                        db, matches=[], results={}, record_id=record_id,
                    )
                    suggestions = [{
                        "priority": "high",
                        "category": "训练",
                        "title": "训练过程异常中断",
                        "detail": str(e),
                        "action": "根据上述错误修复数据或模型枚举后重新训练。",
                    }] + (suggestions or [])
                finally:
                    db.close()
            except Exception:
                pass
            result = {
                "status": "failed",
                "message": str(e),
                "results": {},
                "suggestions": suggestions,
                "snapshot": snapshot,
            }
            if record_id and not self._aborting:
                self._finish_record(record_id, result, started, suggestions, snapshot)
            self._report(message=f"训练失败: {e}", is_training=False, phase="failed")
            return result
        finally:
            if self.is_training:
                self._report(is_training=False, phase="done" if not self._aborting else "aborted")
            self._release_claimed_lock()
            try:
                from services import prediction_cache
                prediction_cache.invalidate_all()
            except Exception:
                pass

    def _soft_league_sample_floor(self) -> int:
        """与融合 soft_league_samples 对齐：低于此场次的非重点联赛不入训练。"""
        try:
            from services.ensemble_registry import get_ensemble
            ensemble = get_ensemble()
            soft = getattr(ensemble, "soft_league_samples", 20) or 20
        except Exception:
            soft = 20
        return max(1, int(soft))

    def _priority_league_ids(self) -> set:
        try:
            from services.real_team_crawler import get_priority_leagues
            return set(get_priority_leagues()) | {"WC"}
        except Exception:
            return {"EPL", "LALIGA", "BUNDES", "SERIEA", "LIGUE1", "UCL", "UEL", "WC"}

    def _eligible_training_league_ids(self, db: Session) -> set:
        """
        训练联赛白名单：
        - 重点联赛（五大+欧冠+世界杯）始终保留
        - 其余联赛完赛（含比分）≥ soft_league_samples 才纳入
        - 未分类（league_id 为空）永远排除
        """
        priority = self._priority_league_ids()
        soft = self._soft_league_sample_floor()
        rows = (
            db.query(Match.league_id, func.count(Match.id))
            .filter(
                Match.status == "finished",
                Match.league_id.isnot(None),
                Match.home_goals.isnot(None),
                Match.away_goals.isnot(None),
            )
            .group_by(Match.league_id)
            .all()
        )
        allowed = set(priority)
        for lid, n in rows:
            if lid and int(n) >= soft:
                allowed.add(str(lid))
        return allowed

    def _get_training_data(self, db: Session, start_date: date = None, end_date: date = None) -> list:
        allowed = self._eligible_training_league_ids(db)
        if not allowed:
            logger.warning("训练白名单为空，未加载任何完赛样本")
            return []
        query = db.query(Match).filter(
            Match.status == "finished",
            Match.league_id.isnot(None),
            Match.home_goals.isnot(None),
            Match.away_goals.isnot(None),
            Match.league_id.in_(list(allowed)),
        )
        if start_date:
            query = query.filter(Match.match_date >= start_date)
        if end_date:
            query = query.filter(Match.match_date <= end_date)
        matches = query.order_by(Match.match_date, Match.match_time).all()
        logger.info(
            "训练样本过滤：白名单联赛 %s 个，加载完赛 %s 场",
            len(allowed),
            len(matches),
        )
        return matches

    def _get_previous_record(self, db: Session, exclude_id: int = None):
        q = db.query(TrainingRecord).filter(TrainingRecord.status == 'success')
        if exclude_id:
            q = q.filter(TrainingRecord.id != exclude_id)
        return q.order_by(TrainingRecord.started_at.desc()).first()

    def _build_training_insights(self, db: Session, matches: list, results: dict, record_id: int = None):
        """训练结束后基于最新库内数据 + 本次训练结果生成快照与建议。"""
        snapshot, suggestions = self._analyze_data_quality(db)

        sample_n = len(matches or [])
        ensemble = (results or {}).get("ensemble") or {}
        elo = (results or {}).get("elo") or {}
        poisson = (results or {}).get("poisson") or {}
        val_acc = float(ensemble.get("validation_accuracy") or 0)
        val_n = int(ensemble.get("validation_matches") or 0)

        snapshot["analysis_at"] = datetime.now().isoformat()
        snapshot["training_sample"] = sample_n
        snapshot["validation_accuracy"] = round(val_acc, 4) if val_acc else None
        snapshot["validation_matches"] = val_n
        snapshot["elo_trained_teams"] = elo.get("trained_teams", 0)
        snapshot["poisson_trained_teams"] = poisson.get("trained_teams", 0)
        snapshot["leagues_optimized"] = ensemble.get("leagues_optimized", 0)
        snapshot["leagues_fallback"] = ensemble.get("leagues_fallback", 0)
        snapshot["by_league_weights"] = ensemble.get("by_league") or {}
        if matches:
            snapshot["training_data_start"] = matches[0].match_date.isoformat()
            snapshot["training_data_end"] = matches[-1].match_date.isoformat()
        finished = snapshot.get("finished_matches") or 0
        if finished and sample_n:
            snapshot["training_coverage_pct"] = round(sample_n / finished * 100, 1)

        ev = ensemble.get("evaluation") or {}
        if ev:
            snapshot["validation_brier"] = ev.get("global_brier")
            snapshot["validation_log_loss"] = ev.get("global_log_loss")
            snapshot["validation_ece"] = ev.get("global_ece")
            snapshot["eval_primary_metric"] = ev.get("primary_metric")
            snapshot["walk_forward_folds"] = ev.get("global_folds") or ev.get("walk_forward_folds")
        td = ensemble.get("time_decay") or {}
        if td:
            snapshot["time_decay"] = td
        if ensemble.get("max_monte_carlo_weight") is not None:
            snapshot["max_monte_carlo_weight"] = ensemble.get("max_monte_carlo_weight")

        prev = self._get_previous_record(db, exclude_id=record_id)
        prev_acc = float(prev.accuracy) if prev and prev.accuracy is not None else None
        prev_sample = prev.total_matches if prev else None
        if prev_acc is not None:
            snapshot["prev_validation_accuracy"] = prev_acc
        if prev_sample is not None:
            snapshot["prev_training_sample"] = prev_sample

        training_suggestions = self._suggestions_from_training_results(
            snapshot, results, sample_n, val_acc, val_n, prev,
        )
        # 训练结果建议排在前面，便于看到本次变化
        suggestions = training_suggestions + [
            s for s in suggestions
            if s.get("title") not in {x.get("title") for x in training_suggestions}
        ]
        return snapshot, suggestions

    def _suggestions_from_training_results(
        self, snapshot: dict, results: dict, sample_n: int, val_acc: float, val_n: int, prev,
    ) -> list:
        """根据本次训练结果与上次对比，生成动态建议。"""
        out = []
        finished = snapshot.get("finished_matches") or 0
        teams_n = snapshot.get("teams") or 0
        elo_teams = (results or {}).get("elo", {}).get("trained_teams", 0)

        if sample_n == 0:
            if finished > 0:
                out.append({
                    "priority": "high",
                    "category": "训练",
                    "title": "完赛数据存在但训练加载失败",
                    "detail": (
                        f"库内完赛 {finished} 场且通常含比分，但 ORM 加载训练样本为 0。"
                        "常见原因：matches.stage / status / result 等枚举值与模型定义不一致。"
                    ),
                    "action": "查看训练记录中的失败 message，或检查 matches 表是否存在未声明的 stage（如 qualifying/knockout）。",
                })
            else:
                out.append({
                    "priority": "high",
                    "category": "训练",
                    "title": "无可用的完赛样本",
                    "detail": "库内没有 status=finished 的比赛，无法训练。",
                    "action": "到联赛列表采集历史赛果，或检查 matches 表中 status/home_goals/away_goals 字段。",
                })
            return out

        acc_pct = val_acc * 100
        leagues_opt = int((results or {}).get("ensemble", {}).get("leagues_optimized") or 0)
        by_league = (results or {}).get("ensemble", {}).get("by_league") or {}
        out.append({
            "priority": "low",
            "category": "训练",
            "title": "本次训练概况",
            "detail": (
                f"使用 {sample_n} 场完赛训练，验证集 {val_n} 场，"
                f"验证准确率 {acc_pct:.1f}%；ELO 覆盖 {elo_teams}/{teams_n} 支球队；"
                f"已对 {leagues_opt} 个联赛单独优化融合权重。"
            ),
            "action": "每轮联赛结束后重新训练，对照分联赛验证准确率是否提升。",
        })

        if by_league:
            top_rows = []
            for lid, meta in sorted(
                by_league.items(),
                key=lambda x: float(x[1].get("validation_accuracy") or 0),
                reverse=True,
            )[:8]:
                acc = meta.get("validation_accuracy")
                src = meta.get("source") or "?"
                if acc is None:
                    top_rows.append(f"{lid}: 样本{meta.get('sample_n', 0)}→回退全局")
                else:
                    top_rows.append(f"{lid}: {float(acc)*100:.1f}% ({src})")
            out.append({
                "priority": "low",
                "category": "训练",
                "title": "分联赛融合权重验证",
                "detail": "；".join(top_rows),
                "action": "样本不足的联赛继续补历史赛果；准确率偏低的联赛优先核对比分完整性。",
            })

        if prev and prev.accuracy is not None:
            prev_pct = float(prev.accuracy) * 100 if float(prev.accuracy) <= 1 else float(prev.accuracy)
            delta = acc_pct - prev_pct
            if abs(delta) >= 0.5:
                trend = "上升" if delta > 0 else "下降"
                out.insert(0, {
                    "priority": "mid" if delta > 0 else "high",
                    "category": "训练",
                    "title": f"验证准确率较上次{trend}",
                    "detail": (
                        f"上次（#{prev.id}）验证 {prev_pct:.1f}%，本次 {acc_pct:.1f}%，"
                        f"变化 {delta:+.1f} 个百分点；样本 {prev.total_matches or 0} → {sample_n} 场。"
                    ),
                    "action": "准确率下降时优先补齐缺比分/缺轮次的联赛数据后再训；上升则保持当前采集节奏。",
                })

        if val_acc < 0.45 and val_n >= 5:
            out.append({
                "priority": "high",
                "category": "训练",
                "title": "融合模型验证准确率偏低",
                "detail": f"本次验证准确率仅 {acc_pct:.1f}%（{val_n} 场），模型区分度不足。",
                "action": "增加五大联赛完整赛季样本，并补球员进球/出场数据以改善攻击力估计。",
            })
        elif val_acc >= 0.55 and sample_n >= 200:
            out.append({
                "priority": "low",
                "category": "训练",
                "title": "验证表现尚可",
                "detail": f"验证准确率 {acc_pct:.1f}%，样本 {sample_n} 场，可继续微调采集频率。",
                "action": "关注逐场球员统计与天气字段，尝试进一步提升 xG 权重贡献。",
            })

        if teams_n and elo_teams < teams_n * 0.7:
            out.append({
                "priority": "mid",
                "category": "训练",
                "title": "部分球队未参与 ELO 训练",
                "detail": f"仅 {elo_teams}/{teams_n} 支球队出现在训练样本中，其余球队仍用默认评级。",
                "action": "为无完赛记录的球队所在联赛补采历史赛程，或合并重复球队 ID。",
            })

        if finished and sample_n < finished * 0.85:
            out.append({
                "priority": "mid",
                "category": "训练",
                "title": "训练样本未覆盖全部完赛",
                "detail": f"库内 {finished} 场完赛，本次实际训练 {sample_n} 场（覆盖率约 {snapshot.get('training_coverage_pct', 0)}%）。",
                "action": "检查是否有未完赛标记的历史比赛，或 date 过滤导致部分场次被排除。",
            })

        weights = (results or {}).get("ensemble", {}).get("weights") or {}
        if weights.get("monte_carlo", 0) >= 0.45 and snapshot.get("finished_matches", 0) < 30:
            out.append({
                "priority": "mid",
                "category": "训练",
                "title": "蒙特卡洛权重偏高但完赛样本不足",
                "detail": (
                    f"融合权重 monte_carlo={weights.get('monte_carlo', 0):.0%}，"
                    f"完赛样本仅 {snapshot.get('finished_matches', 0)} 场。"
                ),
                "action": "先补充历史赛果再训练，或降低蒙特卡洛权重。",
            })

        return out

    def _analyze_data_quality(self, db: Session):
        """统计训练数据缺口，生成可执行的完善建议。"""
        finished = db.query(Match).filter(Match.status == 'finished').count()
        upcoming = db.query(Match).filter(Match.status == 'upcoming').count()
        live = db.query(Match).filter(Match.status == 'live').count()
        teams_n = db.query(Team).count()
        players_n = db.query(Player).count()
        leagues_n = db.query(League).filter(League.is_active == True).count()
        player_stats_n = db.query(MatchPlayerStat).count()
        matches_with_player_stats = (
            db.query(func.count(func.distinct(MatchPlayerStat.match_id))).scalar() or 0
        )

        no_venue = db.query(Match).filter(Match.status == 'finished', or_(Match.venue.is_(None), Match.venue == '')).count()
        no_weather = db.query(Match).filter(Match.status == 'finished', or_(Match.weather.is_(None), Match.weather == '')).count()
        no_pitch = db.query(Match).filter(Match.status == 'finished', or_(Match.pitch_condition.is_(None), Match.pitch_condition == '')).count()
        no_score = db.query(Match).filter(
            Match.status == 'finished',
            or_(Match.home_goals.is_(None), Match.away_goals.is_(None)),
        ).count()

        players_no_photo = 0
        try:
            players_no_photo = db.query(Player).filter(
                or_(Player.photo.is_(None), Player.photo == '', ~Player.photo.like('/static/%'))
            ).count()
        except Exception:
            players_no_photo = players_n

        players_no_apps = db.query(Player).filter(func.coalesce(Player.appearances, 0) == 0).count()
        players_no_nation = db.query(Player).filter(or_(Player.nationality.is_(None), Player.nationality == '')).count()

        league_rows = db.query(Match.league_id, func.count(Match.id)).filter(
            Match.status == 'finished'
        ).group_by(Match.league_id).all()
        league_finished = {lid or '未分类': int(n) for lid, n in league_rows}
        soft_floor = self._soft_league_sample_floor()
        priority_ids = self._priority_league_ids()
        # 重点联赛完赛不足 → 真·高优先；未分类/零散联赛 → 噪声，勿催「补齐五大」
        thin_priority = sorted(
            lid for lid, n in league_finished.items()
            if lid in priority_ids and n < soft_floor
        )
        thin_noise = sorted(
            lid for lid, n in league_finished.items()
            if lid not in priority_ids and n < soft_floor
        )
        eligible = self._eligible_training_league_ids(db)

        snapshot = {
            "finished_matches": finished,
            "upcoming_matches": upcoming,
            "live_matches": live,
            "teams": teams_n,
            "players": players_n,
            "active_leagues": leagues_n,
            "player_match_stats": player_stats_n,
            "matches_with_player_stats": int(matches_with_player_stats),
            "finished_missing_venue": no_venue,
            "finished_missing_weather": no_weather,
            "finished_missing_pitch": no_pitch,
            "finished_missing_score": no_score,
            "players_missing_photo": players_no_photo,
            "players_missing_apps": players_no_apps,
            "players_missing_nationality": players_no_nation,
            "finished_by_league": league_finished,
            "thin_priority_leagues": thin_priority,
            "thin_noise_leagues": thin_noise,
            "training_eligible_leagues": sorted(eligible),
            "soft_league_samples": soft_floor,
        }

        suggestions = []
        if finished < 80:
            suggestions.append({
                "priority": "high",
                "category": "赛事",
                "title": "完赛样本偏少",
                "detail": f"当前仅有 {finished} 场完赛记录，融合模型很难稳定估计权重。建议至少凑齐 200 场以上。",
                "action": "打开联赛列表，对英超/西甲/德甲/意甲/法甲点击「采集球队/赛事」，并勾选上一赛季赛果。",
            })
        if no_score:
            suggestions.append({
                "priority": "high",
                "category": "赛事",
                "title": "完赛缺少比分",
                "detail": f"有 {no_score} 场已结束比赛没有主客队进球数，ELO 和泊松训练会把它们当成 0-0。",
                "action": "重新采集对应联赛赛程，或到历史赛事中核对比分后补录。",
            })
        if thin_priority:
            suggestions.append({
                "priority": "high",
                "category": "联赛覆盖",
                "title": "重点联赛完赛过少",
                "detail": (
                    f"以下重点联赛完赛不足 {soft_floor} 场："
                    + "、".join(str(x) for x in thin_priority[:8])
                    + (" 等" if len(thin_priority) > 8 else "")
                    + "。"
                ),
                "action": "对上述联赛执行历史采集（seasons_back≥2）补齐完整轮次，再跑 priority_train / 全量训练。",
            })
        elif thin_noise:
            suggestions.append({
                "priority": "mid",
                "category": "联赛覆盖",
                "title": "非重点联赛样本过少（已排除训练）",
                "detail": (
                    f"以下联赛完赛不足 {soft_floor} 场，不参与分联赛权重也不进入训练样本："
                    + "、".join(str(x) for x in thin_noise[:8])
                    + (" 等" if len(thin_noise) > 8 else "")
                    + "。五大联赛与欧冠样本充足时无需为这些零散场次补数。"
                ),
                "action": "清理未分类/竞彩未映射场次；勿用少量杯赛或零散联赛硬凑训练。重点联赛保持增量采集即可。",
            })
        if player_stats_n < max(20, finished):
            suggestions.append({
                "priority": "mid",
                "category": "球员",
                "title": "缺少逐场球员统计",
                "detail": f"完赛 {finished} 场，但逐场球员统计只有 {player_stats_n} 条，xG/阵容特征几乎用不上。",
                "action": "采集各队阵容后，再补历史赛事的球员出场数据（射门、传球、抢断等）。",
            })
        if players_n < teams_n * 8:
            suggestions.append({
                "priority": "mid",
                "category": "球员",
                "title": "球队阵容不完整",
                "detail": f"现有 {teams_n} 支球队、{players_n} 名球员，平均每队不足 8 人。",
                "action": "进入球队详情页点击「采集阵容」，或对联赛执行阵容采集。",
            })
        if players_no_apps > players_n * 0.6:
            suggestions.append({
                "priority": "mid",
                "category": "球员",
                "title": "球员出场/进球数据空缺",
                "detail": f"{players_no_apps} 名球员出场数为 0，攻击力特征会被低估。",
                "action": "在定时任务中启用「球员进球统计」，或手动采集联赛球员统计。",
            })
        if no_venue > finished * 0.5 and finished:
            suggestions.append({
                "priority": "low",
                "category": "环境",
                "title": "场地信息缺失",
                "detail": f"{no_venue} 场完赛没有球场，主场优势只能用默认值。",
                "action": "采集联赛积分榜/赛程页中的场地字段，或在赛事详情中补录主场馆。",
            })
        if no_weather > finished * 0.7 and finished:
            suggestions.append({
                "priority": "low",
                "category": "环境",
                "title": "天气与草坪数据不足",
                "detail": f"{no_weather} 场缺少天气，{no_pitch} 场缺少草坪状况，风控和临场修正会偏弱。",
                "action": "开启 Live500 实时采集，赛中/赛后回写天气和草坪。",
            })
        if players_no_photo > 0 and players_n:
            suggestions.append({
                "priority": "low",
                "category": "媒体",
                "title": "球员头像未采全",
                "detail": f"{players_no_photo} 名球员没有本地头像，不影响训练精度，但后台展示不完整。",
                "action": "在定时任务中启用「球员头像采集」，或手动执行图片采集。",
            })
        if upcoming < 10:
            suggestions.append({
                "priority": "mid",
                "category": "赛程",
                "title": "未来赛事偏少",
                "detail": f"当前未开赛仅 {upcoming} 场，训练完成后可用于验证的新样本不多。",
                "action": "刷新未来赛事采集（竞彩 + 联赛赛程），保证最近两周赛程完整。",
            })
        if not suggestions:
            suggestions.append({
                "priority": "low",
                "category": "状态",
                "title": "数据质量良好",
                "detail": (
                    f"完赛 {finished} 场、球员 {players_n} 人、逐场统计 {player_stats_n} 条。"
                    f"可继续补充天气与球员细节以提升融合模型上限。"
                ),
                "action": "保持五大联赛定时采集，每轮结束后再训练一次对照准确率。",
            })
        return snapshot, suggestions

    def get_latest_insights(self) -> dict:
        """返回最新一次已完成训练记录中的快照与建议；若无记录则基于当前库实时分析。"""
        db = SessionLocal()
        try:
            rec = (
                db.query(TrainingRecord)
                .filter(TrainingRecord.status.in_(("success", "failed")))
                .order_by(TrainingRecord.started_at.desc())
                .first()
            )
            if rec:
                return self.record_to_dict(rec, include_detail=True)
            snapshot, suggestions = self._analyze_data_quality(db)
            snapshot["analysis_at"] = datetime.now().isoformat()
            return {
                "id": None,
                "status": "preview",
                "message": "尚未完成训练，以下为当前库内数据实时分析",
                "snapshot": snapshot,
                "suggestions": suggestions,
            }
        finally:
            db.close()

    def _train_elo_model(self, db: Session, matches: list) -> dict:
        """时序训练 ELO，并搜索全局/分联赛 K 与主场加成。"""
        from services.ensemble_registry import get_ensemble
        ensemble = get_ensemble()

        options_k = list(getattr(ensemble, "hyperparam_options", {}).get("elo_k") or [20, 24, 28, 32, 36, 40])
        options_ha = list(
            getattr(ensemble, "hyperparam_options", {}).get("elo_home_advantage")
            or [50, 75, 100, 125, 150]
        )
        min_league = getattr(ensemble, "min_league_samples", 40) or 40
        soft_league = getattr(ensemble, "soft_league_samples", 20) or 20
        soft_league = max(1, min(int(soft_league), int(min_league)))

        by_league = {}
        for m in matches:
            by_league.setdefault(m.league_id or "UNKNOWN", []).append(m)

        global_val = []
        for lid, lm in by_league.items():
            global_val.extend(self._validation_slice(lm))
        if len(global_val) < 5:
            global_val = matches[-min(40, max(5, len(matches) // 5)):]
        if len(global_val) > 120:
            from services.real_team_crawler import get_priority_leagues
            priority_set = set(get_priority_leagues()) | {"WC"}
            preferred = [m for m in global_val if (m.league_id or "") in priority_set]
            others = [m for m in global_val if (m.league_id or "") not in priority_set]
            global_val = (preferred + others)[:120]

        # —— 全局 K / 主场加成 ——
        best_global = {
            "elo_k": float(ensemble.elo.k),
            "elo_home_advantage": float(ensemble.elo.home_advantage),
        }
        best_global_acc = -1.0
        best_ratings = None
        for k in options_k:
            for ha in options_ha:
                ratings = self._simulate_elo_ratings(
                    matches, ensemble, {}, {}, default_k=k, default_ha=ha
                )
                acc = self._score_elo_predictions(
                    global_val, ratings, ensemble, {}, default_ha=ha
                )
                if acc > best_global_acc:
                    best_global_acc = acc
                    best_global = {"elo_k": float(k), "elo_home_advantage": float(ha)}
                    best_ratings = ratings

        # —— 分联赛坐标下降：逐联赛搜 K/主场 ——
        k_map = {}
        ha_map = {}
        league_hp_meta = {}
        for lid, lm in by_league.items():
            sample_n = len(lm)
            soft_mode = soft_league <= sample_n < min_league
            min_val = 5 if soft_mode else 8
            if sample_n < soft_league:
                league_hp_meta[lid] = {
                    "elo_k": best_global["elo_k"],
                    "elo_home_advantage": best_global["elo_home_advantage"],
                    "source": "global_fallback",
                    "train_matches": sample_n,
                    "validation_accuracy": None,
                    "blend_beta": None,
                }
                continue
            val_slice = self._validation_slice(lm)
            if len(val_slice) < min_val:
                league_hp_meta[lid] = {
                    "elo_k": best_global["elo_k"],
                    "elo_home_advantage": best_global["elo_home_advantage"],
                    "source": "global_fallback",
                    "train_matches": sample_n,
                    "validation_accuracy": None,
                    "blend_beta": None,
                }
                continue

            baseline_ratings = self._simulate_elo_ratings(
                matches, ensemble, k_map, ha_map,
                default_k=best_global["elo_k"], default_ha=best_global["elo_home_advantage"],
            )
            baseline_acc = self._score_elo_predictions(
                val_slice, baseline_ratings, ensemble, ha_map,
                default_ha=best_global["elo_home_advantage"],
            )
            best_k = best_global["elo_k"]
            best_ha = best_global["elo_home_advantage"]
            best_acc = baseline_acc
            for k in options_k:
                for ha in options_ha:
                    trial_k = {**k_map, lid: float(k)}
                    trial_ha = {**ha_map, lid: float(ha)}
                    ratings = self._simulate_elo_ratings(
                        matches, ensemble, trial_k, trial_ha,
                        default_k=best_global["elo_k"],
                        default_ha=best_global["elo_home_advantage"],
                    )
                    acc = self._score_elo_predictions(
                        val_slice, ratings, ensemble, trial_ha,
                        default_ha=best_global["elo_home_advantage"],
                    )
                    if acc > best_acc + 0.005:
                        best_acc = acc
                        best_k = float(k)
                        best_ha = float(ha)

            blend_beta = None
            if best_k != best_global["elo_k"] or best_ha != best_global["elo_home_advantage"]:
                if best_acc + 0.01 < baseline_acc:
                    source = "global_better"
                    best_k = best_global["elo_k"]
                    best_ha = best_global["elo_home_advantage"]
                    best_acc = baseline_acc
                else:
                    source = "league"
                    if soft_mode:
                        blend_beta = ensemble.soft_blend_beta(sample_n)
                        best_k = blend_beta * best_k + (1.0 - blend_beta) * best_global["elo_k"]
                        best_ha = blend_beta * best_ha + (1.0 - blend_beta) * best_global["elo_home_advantage"]
                        source = "league_blended"
                    k_map[lid] = best_k
                    ha_map[lid] = best_ha
            else:
                source = "global_better" if best_acc >= 0 else "global_fallback"

            league_hp_meta[lid] = {
                "elo_k": best_k,
                "elo_home_advantage": best_ha,
                "source": source,
                "train_matches": sample_n,
                "validation_matches": len(val_slice),
                "validation_accuracy": round(best_acc, 4),
                "blend_beta": round(float(blend_beta), 4) if blend_beta is not None else None,
            }

        # 最终以搜到的超参重放一遍评级
        final_ratings = self._simulate_elo_ratings(
            matches, ensemble, k_map, ha_map,
            default_k=best_global["elo_k"],
            default_ha=best_global["elo_home_advantage"],
        )
        ensemble.elo.ratings = final_ratings
        poisson_ha = float(getattr(ensemble, "home_advantage", 1.15) or 1.15)
        ensemble.set_global_hyperparams({
            **best_global,
            "poisson_home_advantage": poisson_ha,
        })
        # 先写入 ELO 相关分联赛超参；泊松主场在融合阶段补全
        league_hp = {}
        for lid, meta in league_hp_meta.items():
            league_hp[lid] = {
                "elo_k": meta["elo_k"],
                "elo_home_advantage": meta["elo_home_advantage"],
                "poisson_home_advantage": poisson_ha,
            }
        ensemble.set_league_hyperparams(league_hp)

        top_id = max(final_ratings, key=final_ratings.get) if final_ratings else None
        top_team = db.query(Team).filter(Team.id == top_id).first() if top_id else None
        return {
            "status": "success",
            "trained_teams": len(final_ratings),
            "avg_rating": round(sum(final_ratings.values()) / len(final_ratings), 1) if final_ratings else 0,
            "top_team_id": top_id,
            "top_team": top_team.name if top_team else top_id,
            "top_rating": round(final_ratings[top_id], 1) if top_id else 0,
            "global_hyperparams": {
                **best_global,
                "poisson_home_advantage": poisson_ha,
            },
            "global_elo_validation_accuracy": round(max(0.0, best_global_acc), 4),
            "by_league_hyperparams": league_hp_meta,
            "leagues_optimized": sum(1 for m in league_hp_meta.values() if m.get("source") == "league"),
        }

    def _simulate_elo_ratings(
        self,
        matches: list,
        ensemble,
        k_by_league: dict,
        ha_by_league: dict,
        default_k: float = 32,
        default_ha: float = 100,
    ) -> dict:
        """按时间序重放 ELO；k/ha 可按联赛覆盖。"""
        ratings = {}
        for match in matches:
            home_team = match.home_team_id
            away_team = match.away_team_id
            if not home_team or not away_team:
                continue
            if home_team not in ratings:
                ratings[home_team] = float(ensemble.elo.get_rating(home_team))
            if away_team not in ratings:
                ratings[away_team] = float(ensemble.elo.get_rating(away_team))
            lid = match.league_id or "UNKNOWN"
            k = float(k_by_league.get(lid, default_k))
            ha = float(ha_by_league.get(lid, default_ha))
            ensemble.elo.update_match(
                ratings,
                home_team,
                away_team,
                int(match.home_goals or 0),
                int(match.away_goals or 0),
                k_factor=k,
                home_advantage=ha,
            )
        return ratings

    def _score_elo_predictions(
        self,
        matches: list,
        ratings: dict,
        ensemble,
        ha_by_league: dict,
        default_ha: float = 100,
    ) -> float:
        if not matches:
            return 0.0
        correct = 0
        n = 0
        for match in matches:
            hg = match.home_goals
            ag = match.away_goals
            if hg is None or ag is None:
                continue
            home_id = match.home_team_id
            away_id = match.away_team_id
            if home_id not in ratings or away_id not in ratings:
                continue
            lid = match.league_id or "UNKNOWN"
            ha = float(ha_by_league.get(lid, default_ha))
            probs = ensemble.elo.predict_prob(
                home_id, away_id,
                rating_a=ratings[home_id],
                rating_b=ratings[away_id],
                home_advantage=ha,
            )
            h, d, a = probs["home_win_prob"], probs["draw_prob"], probs["away_win_prob"]
            pred = "home" if h >= d and h >= a else ("away" if a >= d else "draw")
            actual = "home" if hg > ag else ("away" if hg < ag else "draw")
            if pred == actual:
                correct += 1
            n += 1
        return (correct / n) if n else 0.0

    def _train_poisson_model(self, db: Session, matches: list) -> dict:
        from services.ensemble_registry import get_ensemble
        ensemble = get_ensemble()
        from services.eval_metrics import decay_weight

        td = getattr(ensemble, "time_decay", {}) or {}
        decay_on = bool(td.get("enabled", True))
        half_life = float(td.get("half_life_days", 180) or 180)
        ref_date = matches[-1].match_date if matches else date.today()

        team_stats = {}
        league_matches = {}

        for match in matches:
            home_team = match.home_team_id
            away_team = match.away_team_id
            home_goals = match.home_goals or 0
            away_goals = match.away_goals or 0
            league_id = match.league_id
            w = decay_weight(
                match.match_date,
                ref_date=ref_date,
                half_life_days=half_life,
                enabled=decay_on,
            )

            if league_id not in league_matches:
                league_matches[league_id] = {"total_matches": 0.0, "total_goals": 0.0}
            league_matches[league_id]["total_matches"] += w
            league_matches[league_id]["total_goals"] += w * (home_goals + away_goals)

            for team_id, goals_scored, goals_conceded, is_home in [
                (home_team, home_goals, away_goals, True),
                (away_team, away_goals, home_goals, False),
            ]:
                if team_id not in team_stats:
                    team_stats[team_id] = {
                        "home_matches": 0.0, "away_matches": 0.0,
                        "home_goals": 0.0, "away_goals": 0.0,
                        "home_conceded": 0.0, "away_conceded": 0.0,
                        "league": league_id,
                    }
                if is_home:
                    team_stats[team_id]["home_matches"] += w
                    team_stats[team_id]["home_goals"] += w * goals_scored
                    team_stats[team_id]["home_conceded"] += w * goals_conceded
                else:
                    team_stats[team_id]["away_matches"] += w
                    team_stats[team_id]["away_goals"] += w * goals_scored
                    team_stats[team_id]["away_conceded"] += w * goals_conceded

        league_avg = {}
        for league_id, stats in league_matches.items():
            key = league_id or "UNKNOWN"
            league_avg[key] = stats["total_goals"] / stats["total_matches"] if stats["total_matches"] else 2.7

        new_team_params = {}
        for team_id, stats in team_stats.items():
            league_id = stats["league"]
            avg_goals = league_avg.get(league_id or "UNKNOWN", 2.7) or 2.7
            # 联赛场次全 0-0 时 avg_goals=0，避免后续除零
            if avg_goals <= 0:
                avg_goals = 2.7
            half_avg = avg_goals / 2
            home_attack = away_attack = home_defense = away_defense = 1.0
            if stats["home_matches"] > 0:
                home_attack = (stats["home_goals"] / stats["home_matches"]) / half_avg
                home_defense = (stats["home_conceded"] / stats["home_matches"]) / half_avg
            if stats["away_matches"] > 0:
                away_attack = (stats["away_goals"] / stats["away_matches"]) / half_avg
                away_defense = (stats["away_conceded"] / stats["away_matches"]) / half_avg
            attack = max(0.5, min(2.0, (home_attack + away_attack) / 2))
            defense = max(0.5, min(2.0, (home_defense + away_defense) / 2))
            new_team_params[team_id] = {
                "attack": round(attack, 2),
                "defense": round(defense, 2),
                "league": league_id,
            }

        ensemble.team_params = new_team_params
        ensemble.league_avg = league_avg
        return {
            "status": "success",
            "trained_teams": len(new_team_params),
            "leagues": len(league_avg),
            "league_avg": {str(k): round(v, 3) for k, v in league_avg.items()},
            "avg_attack": round(sum(p["attack"] for p in new_team_params.values()) / len(new_team_params), 2) if new_team_params else 0,
            "avg_defense": round(sum(p["defense"] for p in new_team_params.values()) / len(new_team_params), 2) if new_team_params else 0,
            "time_decay": {"enabled": decay_on, "half_life_days": half_life},
        }

    def _train_xg_model(self, db: Session, matches: list) -> dict:
        """从 match_player_stats 射门/射正估计球队 xG 攻防参数。"""
        from services.ensemble_registry import get_ensemble
        ensemble = get_ensemble()
        from models.xg_model import XGModel

        if not matches:
            return {"status": "success", "trained_teams": 0, "matches_with_stats": 0}

        match_by_id = {m.id: m for m in matches}
        match_ids = list(match_by_id.keys())

        # 分批查询，避免 IN 过长
        rows = []
        batch = 500
        for i in range(0, len(match_ids), batch):
            chunk = match_ids[i:i + batch]
            rows.extend(
                db.query(MatchPlayerStat)
                .filter(MatchPlayerStat.match_id.in_(chunk))
                .all()
            )

        per_match_team = {}
        for r in rows:
            m = match_by_id.get(r.match_id)
            if not m:
                continue
            tid = r.team_id
            if not tid:
                tid = m.home_team_id if r.is_home else m.away_team_id
            if not tid:
                continue
            key = (r.match_id, str(tid))
            bucket = per_match_team.setdefault(key, {
                "shots": 0, "sot": 0, "goals_stat": 0, "is_home": bool(r.is_home),
            })
            bucket["shots"] += int(r.shots or 0)
            bucket["sot"] += int(r.shots_on_target or 0)
            bucket["goals_stat"] += int(r.goals or 0)

        # P2：球员行缺失时用 match_team_stats 补球队射门
        try:
            from db.models import MatchTeamStat
            team_rows = []
            for i in range(0, len(match_ids), batch):
                chunk = match_ids[i:i + batch]
                team_rows.extend(
                    db.query(MatchTeamStat)
                    .filter(MatchTeamStat.match_id.in_(chunk))
                    .all()
                )
            for r in team_rows:
                key = (r.match_id, str(r.team_id))
                if key in per_match_team:
                    continue
                per_match_team[key] = {
                    "shots": int(r.shots or 0),
                    "sot": int(r.shots_on_target or 0),
                    "goals_stat": 0,
                    "is_home": bool(r.is_home),
                }
        except Exception as e:
            logger.debug("merge match_team_stats for xG skipped: %s", e)

        if not per_match_team:
            return {
                "status": "success",
                "trained_teams": 0,
                "matches_with_stats": 0,
                "message": "无 match_player_stats / match_team_stats，跳过 xG",
            }

        # 联赛转化率先验
        league_tot = {}
        for (mid, tid), s in per_match_team.items():
            m = match_by_id.get(mid)
            if not m:
                continue
            lid = m.league_id or "UNKNOWN"
            tot = league_tot.setdefault(lid, {"shots": 0, "sot": 0, "goals": 0, "matches": set()})
            tot["shots"] += s["shots"]
            tot["sot"] += s["sot"]
            if tid == m.home_team_id:
                tot["goals"] += int(m.home_goals or 0)
            elif tid == m.away_team_id:
                tot["goals"] += int(m.away_goals or 0)
            tot["matches"].add(mid)

        prior_shot = float(ensemble.xg.prior_xg_per_shot)
        prior_sot = float(ensemble.xg.prior_xg_per_sot)
        league_priors = {}
        for lid, tot in league_tot.items():
            n_m = len(tot["matches"]) or 1
            xps = (tot["goals"] / tot["shots"]) if tot["shots"] > 0 else prior_shot
            xpso = (tot["goals"] / tot["sot"]) if tot["sot"] > 0 else prior_sot
            # 夹紧到合理区间，避免极端脏数据
            xps = max(0.05, min(0.25, float(xps)))
            xpso = max(0.15, min(0.55, float(xpso)))
            xg_for_avg = max(0.6, min(2.5, (
                0.4 * (tot["shots"] / n_m) * xps + 0.6 * (tot["sot"] / n_m) * xpso
            )))
            prior = {
                "xg_per_shot": round(xps, 4),
                "xg_per_sot": round(xpso, 4),
                "xg_for_avg": round(xg_for_avg, 3),
                "shots_pg": round(tot["shots"] / n_m, 2),
                "sot_pg": round(tot["sot"] / n_m, 2),
                "matches": n_m,
            }
            league_priors[lid] = prior
            ensemble.xg.set_league_prior(lid, prior)

        # 球队逐场 xG for / against
        team_agg = {}
        matches_with_stats = set()
        for m in matches:
            home_s = per_match_team.get((m.id, str(m.home_team_id)))
            away_s = per_match_team.get((m.id, str(m.away_team_id)))
            if not home_s and not away_s:
                continue
            matches_with_stats.add(m.id)
            lid = m.league_id or "UNKNOWN"
            prior = league_priors.get(lid, {})
            xps = float(prior.get("xg_per_shot", prior_shot))
            xpso = float(prior.get("xg_per_sot", prior_sot))

            home_xg = XGModel.match_team_xg_from_shots(
                home_s["shots"], home_s["sot"], xps, xpso
            ) if home_s else None
            away_xg = XGModel.match_team_xg_from_shots(
                away_s["shots"], away_s["sot"], xps, xpso
            ) if away_s else None

            def _ensure(tid, league):
                return team_agg.setdefault(tid, {
                    "xg_for": [], "xg_against": [],
                    "shots": 0, "sot": 0, "matches": 0, "league": league,
                })

            if home_xg is not None:
                th = _ensure(str(m.home_team_id), lid)
                th["xg_for"].append(home_xg)
                th["shots"] += home_s["shots"]
                th["sot"] += home_s["sot"]
                th["matches"] += 1
                if away_xg is not None:
                    th["xg_against"].append(away_xg)
            if away_xg is not None:
                ta = _ensure(str(m.away_team_id), lid)
                ta["xg_for"].append(away_xg)
                ta["shots"] += away_s["shots"]
                ta["sot"] += away_s["sot"]
                ta["matches"] += 1
                if home_xg is not None:
                    ta["xg_against"].append(home_xg)

        trained = 0
        xg_params = {}
        for tid, agg in team_agg.items():
            n = int(agg["matches"] or 0)
            if n < 1:
                continue
            xg_for = sum(agg["xg_for"]) / len(agg["xg_for"]) if agg["xg_for"] else 1.35
            if agg["xg_against"]:
                xg_against = sum(agg["xg_against"]) / len(agg["xg_against"])
            else:
                lid = agg["league"]
                xg_against = float(league_priors.get(lid, {}).get("xg_for_avg", 1.35))
            params = {
                "xg_for": round(max(0.4, min(3.5, xg_for)), 3),
                "xg_against": round(max(0.4, min(3.5, xg_against)), 3),
                "shots_pg": round(agg["shots"] / n, 2),
                "sot_pg": round(agg["sot"] / n, 2),
                "matches": n,
                "xg_matches": n,
                "league": agg["league"],
            }
            ensemble.xg.set_team(tid, params)
            xg_params[tid] = params
            # 合并进 team_params，供持久化与预测
            base = dict(ensemble.team_params.get(tid) or {})
            base.update(params)
            if "attack" not in base:
                base["attack"] = 1.0
            if "defense" not in base:
                base["defense"] = 1.0
            ensemble.team_params[tid] = base
            trained += 1

        avg_for = (
            sum(p["xg_for"] for p in xg_params.values()) / len(xg_params)
            if xg_params else 0
        )
        return {
            "status": "success",
            "trained_teams": trained,
            "matches_with_stats": len(matches_with_stats),
            "leagues": len(league_priors),
            "league_priors": league_priors,
            "avg_xg_for": round(avg_for, 3),
        }

    def _persist_trained_params(self, db: Session, results: dict) -> dict:
        """将 ELO / 攻防 / xG / 联赛场均进球回写数据库，供预测与重启后使用。"""
        from services.ensemble_registry import get_ensemble
        ensemble = get_ensemble()
        from db.models import League

        elo_n = 0
        for team_id, rating in (ensemble.elo.ratings or {}).items():
            team = db.query(Team).filter(Team.id == team_id).first()
            if not team:
                continue
            team.elo_rating = int(round(float(rating)))
            elo_n += 1

        strength_n = 0
        xg_n = 0
        for team_id, params in (ensemble.team_params or {}).items():
            team = db.query(Team).filter(Team.id == team_id).first()
            if not team:
                continue
            if params.get("attack") is not None:
                team.attack_strength = float(params["attack"])
            if params.get("defense") is not None:
                team.defense_strength = float(params["defense"])
            strength_n += 1
            if params.get("xg_for") is not None:
                team.xg_for = float(params["xg_for"])
                xg_n += 1
            if params.get("xg_against") is not None:
                team.xg_against = float(params["xg_against"])

        league_n = 0
        for league_id, avg in (ensemble.league_avg or {}).items():
            if not league_id or league_id == "UNKNOWN":
                continue
            league = db.query(League).filter(League.id == str(league_id)).first()
            if not league:
                continue
            league.avg_goals = round(float(avg), 2)
            league_n += 1

        db.commit()
        return {
            "status": "success",
            "elo_updated": elo_n,
            "strength_updated": strength_n,
            "xg_updated": xg_n,
            "league_avg_updated": league_n,
        }

    def _train_ensemble_model(self, db: Session, matches: list) -> dict:
        """全局 + 分联赛网格搜索融合权重，并搜索泊松主场优势。"""
        from services.ensemble_registry import get_ensemble
        ensemble = get_ensemble()

        if len(matches) < 10:
            return {
                "status": "success",
                "message": "数据不足，使用默认权重",
                "weights": ensemble.weights,
                "league_weights": {},
                "by_league": {},
                "validation_accuracy": 0,
                "validation_matches": 0,
            }

        min_league = getattr(ensemble, "min_league_samples", 40) or 40
        soft_league = getattr(ensemble, "soft_league_samples", 20) or 20
        soft_league = max(1, min(int(soft_league), int(min_league)))
        weight_options = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
        poisson_ha_options = list(
            getattr(ensemble, "hyperparam_options", {}).get("poisson_home_advantage")
            or [1.05, 1.10, 1.15, 1.20, 1.25]
        )

        # 训练前快照：用于 EMA，降低小样本联赛权重抖动
        prev_global_w = dict(ensemble.weights or {})
        prev_league_w = {
            str(lid): dict(w)
            for lid, w in (getattr(ensemble, "league_weights", {}) or {}).items()
            if isinstance(w, dict)
        }

        # 按联赛分组（保持时间序）
        by_league = {}
        for m in matches:
            lid = m.league_id or "UNKNOWN"
            by_league.setdefault(lid, []).append(m)

        # —— 全局权重：各联赛验证尾部拼成混合验证集 ——
        global_val = []
        for lid, lm in by_league.items():
            global_val.extend(self._validation_slice(lm))
        if len(global_val) < 5:
            global_val = matches[-min(40, max(5, len(matches) // 5)):]
        if len(global_val) > 150:
            from services.real_team_crawler import get_priority_leagues
            priority_set = set(get_priority_leagues()) | {"WC"}
            preferred = [m for m in global_val if (m.league_id or "") in priority_set]
            others = [m for m in global_val if (m.league_id or "") not in priority_set]
            global_val = (preferred + others)[:150]

        ghp = ensemble.get_hyperparams_for_league(None)
        best_global_hp = dict(ghp)
        best_global_acc = -1.0
        best_global_w = dict(ensemble.weights)
        best_global_cache_n = 0
        best_global_cache = []
        best_global_metrics = {"n": 0, "accuracy": -1.0, "brier": 9e9}
        from services.eval_metrics import is_better, score_cache as eval_score_cache

        for p_ha in poisson_ha_options:
            trial_hp = {
                **ghp,
                "poisson_home_advantage": float(p_ha),
            }
            cache = self._precompute_components(global_val, ensemble, hyperparams=trial_hp)
            if len(cache) < 5:
                continue
            w, acc, metrics = self._grid_search_weights(cache, weight_options, ensemble=ensemble)
            if is_better(metrics, best_global_metrics, primary=(getattr(ensemble, "evaluation", {}) or {}).get("primary_metric", "brier")):
                best_global_metrics = metrics
                best_global_acc = acc
                best_global_w = w
                best_global_hp = trial_hp
                best_global_cache_n = len(cache)
                best_global_cache = cache

        # 全局权重 EMA（按总样本自适应 α）
        raw_global_w = dict(best_global_w)
        best_global_w, global_alpha = ensemble.smooth_weights(
            best_global_w, prev_global_w, sample_n=len(matches),
        )
        if best_global_cache and abs(global_alpha - 1.0) > 1e-6:
            best_global_metrics = eval_score_cache(best_global_cache, best_global_w)
            best_global_acc = float(best_global_metrics.get("accuracy") or 0)

        ensemble.set_weights(best_global_w)
        ensemble.set_global_hyperparams(best_global_hp)

        # —— 分联赛权重 + 泊松主场 ——
        league_weight_map = {}
        league_hp_map = dict(getattr(ensemble, "league_hyperparams", {}) or {})
        league_meta = {}
        for lid, lm in by_league.items():
            sample_n = len(lm)
            base_hp = ensemble.get_hyperparams_for_league(lid)
            soft_mode = soft_league <= sample_n < min_league
            min_val = 5 if soft_mode else 8
            if sample_n < soft_league:
                league_meta[lid] = {
                    "train_matches": sample_n,
                    "sample_n": sample_n,
                    "validation_matches": 0,
                    "validation_accuracy": None,
                    "source": "global_fallback",
                    "hyper_source": "global_fallback",
                    "smooth_alpha": None,
                    "blend_beta": None,
                    "weights": {k: round(v, 4) for k, v in best_global_w.items()},
                    "hyperparams": {
                        "elo_k": round(float(base_hp["elo_k"]), 2),
                        "elo_home_advantage": round(float(base_hp["elo_home_advantage"]), 2),
                        "poisson_home_advantage": round(float(best_global_hp["poisson_home_advantage"]), 4),
                    },
                }
                league_hp_map[lid] = league_meta[lid]["hyperparams"]
                continue

            val_slice = self._validation_slice(lm)
            if len(val_slice) < min_val:
                league_meta[lid] = {
                    "train_matches": sample_n,
                    "sample_n": sample_n,
                    "validation_matches": len(val_slice),
                    "validation_accuracy": None,
                    "source": "global_fallback",
                    "hyper_source": "global_fallback",
                    "smooth_alpha": None,
                    "blend_beta": None,
                    "weights": {k: round(v, 4) for k, v in best_global_w.items()},
                    "hyperparams": {
                        "elo_k": round(float(base_hp["elo_k"]), 2),
                        "elo_home_advantage": round(float(base_hp["elo_home_advantage"]), 2),
                        "poisson_home_advantage": round(float(best_global_hp["poisson_home_advantage"]), 4),
                    },
                }
                league_hp_map[lid] = league_meta[lid]["hyperparams"]
                continue

            best_w = best_global_w
            best_acc = -1.0
            best_metrics = {"n": 0, "accuracy": -1.0, "brier": 9e9}
            best_hp = {
                **base_hp,
                "poisson_home_advantage": best_global_hp["poisson_home_advantage"],
            }
            best_cache_n = 0
            best_cache = []
            global_cache = self._precompute_components(
                val_slice, ensemble, hyperparams=best_global_hp
            )
            global_metrics = eval_score_cache(global_cache, best_global_w) if global_cache else {"n": 0, "accuracy": 0.0, "brier": 1.0}
            global_on_league = float(global_metrics.get("accuracy") or 0)
            primary = (getattr(ensemble, "evaluation", {}) or {}).get("primary_metric", "brier")
            for p_ha in poisson_ha_options:
                trial_hp = {**base_hp, "poisson_home_advantage": float(p_ha)}
                cache = self._precompute_components(val_slice, ensemble, hyperparams=trial_hp)
                if len(cache) < min_val:
                    continue
                w, acc, metrics = self._grid_search_weights(cache, weight_options, ensemble=ensemble)
                if is_better(metrics, best_metrics, primary=primary):
                    best_metrics = metrics
                    best_acc = acc
                    best_w = w
                    best_hp = trial_hp
                    best_cache_n = len(cache)
                    best_cache = cache

            if best_acc < 0:
                best_acc = global_on_league
                best_metrics = global_metrics
                best_w = best_global_w
                best_hp = {
                    **base_hp,
                    "poisson_home_advantage": best_global_hp["poisson_home_advantage"],
                }
                best_cache_n = len(global_cache)
                best_cache = global_cache

            # 与全局对比：主指标优先；Brier 越低越好
            league_worse_than_global = False
            if primary == "accuracy":
                league_worse_than_global = best_acc + 0.01 < global_on_league
            else:
                league_worse_than_global = float(best_metrics.get(primary) or 9) > float(global_metrics.get(primary) or 9) + 0.005

            if league_worse_than_global:
                chosen_w, acc, source = best_global_w, global_on_league, "global_better"
                chosen_metrics = global_metrics
                chosen_hp = {
                    **base_hp,
                    "poisson_home_advantage": best_global_hp["poisson_home_advantage"],
                }
                hyper_source = "global_better"
                score_cache = global_cache
                blend_beta = None
            else:
                chosen_w, acc, source = best_w, best_acc, "league"
                chosen_metrics = best_metrics
                chosen_hp = best_hp
                score_cache = best_cache if best_cache else global_cache
                hyper_source = (
                    "league"
                    if abs(float(chosen_hp["poisson_home_advantage"]) - float(best_global_hp["poisson_home_advantage"])) > 1e-6
                    or abs(float(chosen_hp["elo_k"]) - float(best_global_hp["elo_k"])) > 1e-6
                    or abs(float(chosen_hp["elo_home_advantage"]) - float(best_global_hp["elo_home_advantage"])) > 1e-6
                    else "global_better"
                )
                blend_beta = None
                # 小样本：联赛网格结果向全局收缩，减轻过拟合
                if soft_mode and source == "league":
                    blend_beta = ensemble.soft_blend_beta(sample_n)
                    chosen_w = ensemble.blend_weights(chosen_w, best_global_w, blend_beta)
                    source = "league_blended"
                    if score_cache:
                        chosen_metrics = eval_score_cache(score_cache, chosen_w)
                        acc = float(chosen_metrics.get("accuracy") or 0)
                    # 超参同步软混合（泊松主场）
                    if hyper_source == "league":
                        g_ha = float(best_global_hp["poisson_home_advantage"])
                        l_ha = float(chosen_hp["poisson_home_advantage"])
                        chosen_hp = {
                            **chosen_hp,
                            "poisson_home_advantage": blend_beta * l_ha + (1.0 - blend_beta) * g_ha,
                        }
                        hyper_source = "league_blended"

            # 分联赛权重 EMA：无历史联赛权重时向旧全局靠拢
            prev_w = prev_league_w.get(str(lid)) or prev_global_w
            chosen_w, smooth_alpha = ensemble.smooth_weights(
                chosen_w, prev_w, sample_n=sample_n,
            )
            if score_cache and abs(smooth_alpha - 1.0) > 1e-6:
                chosen_metrics = eval_score_cache(score_cache, chosen_w)
                acc = float(chosen_metrics.get("accuracy") or 0)

            league_weight_map[lid] = chosen_w
            league_hp_map[lid] = {
                "elo_k": round(float(chosen_hp["elo_k"]), 2),
                "elo_home_advantage": round(float(chosen_hp["elo_home_advantage"]), 2),
                "poisson_home_advantage": round(float(chosen_hp["poisson_home_advantage"]), 4),
            }
            league_meta[lid] = {
                "train_matches": sample_n,
                "sample_n": sample_n,
                "validation_matches": best_cache_n or len(global_cache),
                "validation_accuracy": round(acc, 4),
                "validation_brier": round(float(chosen_metrics.get("brier") or 0), 4) if chosen_metrics else None,
                "validation_log_loss": round(float(chosen_metrics.get("log_loss") or 0), 4) if chosen_metrics else None,
                "validation_ece": round(float(chosen_metrics.get("ece") or 0), 4) if chosen_metrics else None,
                "source": source,
                "hyper_source": hyper_source,
                "smooth_alpha": round(float(smooth_alpha), 4),
                "blend_beta": round(float(blend_beta), 4) if blend_beta is not None else None,
                "weights": {k: round(v, 4) for k, v in chosen_w.items()},
                "hyperparams": league_hp_map[lid],
            }

        ensemble.set_league_weights(league_weight_map)
        ensemble.set_league_hyperparams(league_hp_map)

        total_correct = 0.0
        total_n = 0
        for lid, meta in league_meta.items():
            if meta.get("validation_accuracy") is not None and meta.get("validation_matches"):
                total_correct += meta["validation_accuracy"] * meta["validation_matches"]
                total_n += meta["validation_matches"]
        if total_n == 0:
            total_n = best_global_cache_n
            total_correct = best_global_acc * total_n
        overall_acc = (total_correct / total_n) if total_n else 0.0

        sm_cfg = getattr(ensemble, "weight_smoothing", {}) or {}
        payload = ensemble.export_weights_payload(league_meta)
        return {
            "status": "success",
            "weights": {k: round(v, 4) for k, v in ensemble.weights.items()},
            "weights_raw_global": {k: round(v, 4) for k, v in raw_global_w.items()},
            "smooth_alpha_global": round(float(global_alpha), 4),
            "hyperparams": {
                "elo_k": round(float(best_global_hp["elo_k"]), 2),
                "elo_home_advantage": round(float(best_global_hp["elo_home_advantage"]), 2),
                "poisson_home_advantage": round(float(best_global_hp["poisson_home_advantage"]), 4),
            },
            "league_weights": {
                lid: meta["weights"] for lid, meta in league_meta.items()
                if meta.get("source") in ("league", "global_better", "league_blended")
            },
            "by_league": league_meta,
            "weights_payload": payload,
            "validation_accuracy": round(overall_acc, 4),
            "validation_matches": total_n,
            "global_validation_accuracy": round(max(0.0, best_global_acc), 4),
            "global_validation_matches": best_global_cache_n,
            "evaluation": {
                "primary_metric": (getattr(ensemble, "evaluation", {}) or {}).get("primary_metric", "brier"),
                "walk_forward_folds": int((getattr(ensemble, "evaluation", {}) or {}).get("walk_forward_folds") or 3),
                "global_brier": round(float(best_global_metrics.get("brier") or 0), 4),
                "global_log_loss": round(float(best_global_metrics.get("log_loss") or 0), 4),
                "global_ece": round(float(best_global_metrics.get("ece") or 0), 4),
                "global_folds": int(best_global_metrics.get("folds") or 1),
            },
            "time_decay": dict(getattr(ensemble, "time_decay", {}) or {}),
            "max_monte_carlo_weight": float(getattr(ensemble, "max_monte_carlo_weight", 0.28) or 0.28),
            "leagues_optimized": sum(1 for m in league_meta.values() if m.get("source") == "league"),
            "leagues_blended": sum(1 for m in league_meta.values() if m.get("source") == "league_blended"),
            "leagues_fallback": sum(1 for m in league_meta.values() if m.get("source") == "global_fallback"),
            "leagues_hyper_optimized": sum(
                1 for m in league_meta.values() if m.get("hyper_source") == "league"
            ),
            "min_league_samples": min_league,
            "soft_league_samples": soft_league,
            "weight_smoothing": {
                "enabled": bool(sm_cfg.get("enabled", True)),
                "prior_strength": sm_cfg.get("prior_strength"),
                "min_alpha": sm_cfg.get("min_alpha"),
                "max_alpha": sm_cfg.get("max_alpha"),
                "global_alpha": round(float(global_alpha), 4),
            },
        }

    @staticmethod
    def _validation_slice(matches: list, max_n: int = 40) -> list:
        if not matches:
            return []
        n = len(matches)
        take = min(max_n, max(8, n // 5))
        return matches[-take:]

    def _precompute_components(self, matches: list, ensemble, hyperparams: dict = None) -> list:
        """预计算各子模型概率，网格搜索时只做加权，避免重复蒙特卡洛。"""
        from services.eval_metrics import decay_weight

        cache = []
        old_sims = ensemble.monte_carlo.simulations
        # 训练期降采样加速；结果仍足用于相对比较权重
        ensemble.monte_carlo.simulations = min(old_sims, 2000)
        td = getattr(ensemble, "time_decay", {}) or {}
        ref_date = matches[-1].match_date if matches else date.today()
        try:
            for match in matches:
                home_goals = match.home_goals
                away_goals = match.away_goals
                if home_goals is None or away_goals is None:
                    continue
                actual = "home" if home_goals > away_goals else ("away" if home_goals < away_goals else "draw")
                try:
                    comps = self._match_model_components(match, ensemble, hyperparams=hyperparams)
                    if not comps:
                        continue
                    comps["actual"] = actual
                    comps["match_date"] = match.match_date
                    comps["sample_weight"] = decay_weight(
                        match.match_date,
                        ref_date=ref_date,
                        half_life_days=float(td.get("half_life_days", 180) or 180),
                        enabled=bool(td.get("enabled", True)),
                    )
                    cache.append(comps)
                except Exception:
                    continue
        finally:
            ensemble.monte_carlo.simulations = old_sims
        return cache

    def _match_model_components(self, match, ensemble, hyperparams: dict = None) -> dict:
        home_id = match.home_team_id
        away_id = match.away_team_id
        home = ensemble.team_params.get(home_id) or ensemble._get_team_params(home_id)
        away = ensemble.team_params.get(away_id) or ensemble._get_team_params(away_id)
        lid = match.league_id or home.get("league")
        avg = ensemble.league_avg.get(lid, ensemble.league_avg.get(home.get("league"), 2.70))
        if avg is None or float(avg) <= 0:
            avg = 2.70

        hp = hyperparams or ensemble.get_hyperparams_for_league(lid)
        poisson_ha = float(hp.get("poisson_home_advantage", getattr(ensemble, "home_advantage", 1.15)))
        elo_ha = float(hp.get("elo_home_advantage", ensemble.elo.home_advantage))

        ensemble._hydrate_xg_from_params(home_id, home, lid)
        ensemble._hydrate_xg_from_params(away_id, away, lid)

        lambda_home = ensemble.poisson.calculate_lambda(
            float(home["attack"]), float(away["defense"]), float(avg),
            is_home=True, home_adv=poisson_ha,
        )
        lambda_away = ensemble.poisson.calculate_lambda(
            float(away["attack"]), float(home["defense"]), float(avg),
            is_home=False, home_adv=poisson_ha,
        )
        poisson = ensemble.poisson.predict(lambda_home, lambda_away)
        elo = ensemble.elo.predict_prob(
            home_id, away_id,
            rating_a=ensemble.elo.get_rating(home_id),
            rating_b=ensemble.elo.get_rating(away_id),
            home_advantage=elo_ha,
        )
        mc = ensemble.monte_carlo.simulate(lambda_home, lambda_away)

        old_xg_ha = ensemble.xg.home_advantage
        try:
            x_cfg = (ensemble.config or {}).get("xg") or {}
            base_p = float(((ensemble.config or {}).get("poisson") or {}).get("home_advantage", 1.15)) or 1.15
            base_x = float(x_cfg.get("home_advantage", 1.08))
            ensemble.xg.home_advantage = max(1.0, base_x * (poisson_ha / base_p))
            xg = ensemble.xg.predict_prob(
                home_id, away_id, league_id=lid, poisson_model=ensemble.poisson
            )
        finally:
            ensemble.xg.home_advantage = old_xg_ha

        return {
            "elo": {
                "home": elo["home_win_prob"],
                "draw": elo["draw_prob"],
                "away": elo["away_win_prob"],
            },
            "poisson": {
                "home": poisson["home_win_prob"],
                "draw": poisson.get("draw_prob", 0),
                "away": poisson["away_win_prob"],
            },
            "xg": {
                "home": xg["home_win_prob"],
                "draw": xg.get("draw_prob", 0),
                "away": xg["away_win_prob"],
            },
            "xg_coverage": float(xg.get("coverage") or 0),
            "monte_carlo": {
                "home": mc["home_win_prob"],
                "draw": mc["draw_prob"],
                "away": mc["away_win_prob"],
            },
            "league_id": lid,
        }

    def _grid_search_weights(self, cache: list, weight_options: list, ensemble=None):
        from services.eval_metrics import (
            average_metrics,
            is_better,
            score_cache,
            walk_forward_slices,
        )

        if ensemble is None:
            from services.ensemble_registry import get_ensemble
            ensemble = get_ensemble()

        ev = getattr(ensemble, "evaluation", {}) or {}
        primary = str(ev.get("primary_metric") or "brier").lower()
        folds = int(ev.get("walk_forward_folds") or 3)
        bins = int(ev.get("calibration_bins") or 5)
        max_mc = float(getattr(ensemble, "max_monte_carlo_weight", 0.28) or 0.28)
        min_mc = float(getattr(ensemble, "min_monte_carlo_weight", 0.05) or 0.05)

        best_weights = ensemble._normalize_weights(
            {"elo": 0.30, "poisson": 0.30, "xg": 0.22, "monte_carlo": 0.18}
        )
        best_metrics = {"n": 0, "accuracy": -1.0, "brier": 9e9}
        if not cache:
            return best_weights, 0.0, best_metrics

        slices = walk_forward_slices(cache, folds=folds)

        for elo_w in weight_options:
            for poisson_w in weight_options:
                for xg_w in weight_options:
                    mc_w = 1.0 - elo_w - poisson_w - xg_w
                    if mc_w < min_mc - 1e-9 or mc_w > max_mc + 1e-9:
                        continue
                    temp = {
                        "elo": elo_w,
                        "poisson": poisson_w,
                        "xg": xg_w,
                        "monte_carlo": mc_w,
                    }
                    temp = ensemble._normalize_weights(temp)
                    fold_metrics = [
                        score_cache(sl, temp, calibration_bins=bins) for sl in slices
                    ]
                    metrics = average_metrics(fold_metrics)
                    if is_better(metrics, best_metrics, primary=primary):
                        best_metrics = metrics
                        best_weights = temp

        # 全量缓存再算一遍，便于落库展示
        final_metrics = score_cache(cache, best_weights, calibration_bins=bins)
        final_metrics["folds"] = best_metrics.get("folds") or len(slices)
        final_metrics["primary_metric"] = primary
        return best_weights, float(final_metrics.get("accuracy") or 0), final_metrics

    @staticmethod
    def _score_weights(cache: list, weights: dict) -> float:
        from services.eval_metrics import score_cache
        return float(score_cache(cache, weights).get("accuracy") or 0)

    def _validate_weights(self, weights: dict, matches: list, ensemble, db=None) -> float:
        """兼容旧调用：预计算后评分。"""
        cache = self._precompute_components(matches, ensemble)
        return self._score_weights(cache, weights)

    def _save_training_results(self, db: Session, results: dict, matches: list) -> str:
        from services import ModelService
        from services.ensemble_registry import get_ensemble
        ensemble = get_ensemble()

        version = f"v{datetime.now().strftime('%Y%m%d.%H%M%S')}"
        ens = results.get("ensemble", {}) or {}
        acc = float(ens.get("validation_accuracy") or 0)
        elo_n = results.get("elo", {}).get("trained_teams", 0)
        poisson_n = results.get("poisson", {}).get("trained_teams", 0)
        xg_n = results.get("xg", {}).get("trained_teams", 0)
        leagues_opt = ens.get("leagues_optimized", 0)
        description = (
            f"自动训练 - ELO: {elo_n}队, 泊松: {poisson_n}队, xG: {xg_n}队, "
            f"验证准确率: {acc:.2%}, 样本: {len(matches)}场, "
            f"分联赛优化: {leagues_opt}"
        )
        weights_payload = ens.get("weights_payload") or ensemble.export_weights_payload(
            ens.get("by_league") or {}
        )
        ModelService.create(db, {
            "version": version,
            "description": description,
            "accuracy": round(acc * 100, 2),
            "status": "archived",
            "training_data_start": matches[0].match_date if matches else None,
            "training_data_end": matches[-1].match_date if matches else None,
            "weights_json": json.dumps(weights_payload, ensure_ascii=False),
        })
        ModelService.set_current_by_version(db, version)
        self._record_accuracy_trend(db, version, acc, ens.get("validation_matches") or len(matches))
        try:
            ensemble.apply_weights_payload(weights_payload)
        except Exception as e:
            logger.warning("训练后应用权重到内存失败: %s", e)
        try:
            from services.ensemble_registry import publish_weights_version
            publish_weights_version(version)
        except Exception as e:
            logger.warning("广播模型版本失败: %s", e)
        return version

    def _record_accuracy_trend(self, db: Session, version: str, accuracy: float, val_matches: int) -> None:
        """训练完成后写入准确率趋势，供模型管理页图表展示。"""
        from services import TrendService
        from db.models import AccuracyTrend

        acc_pct = float(accuracy) * 100 if float(accuracy) <= 1 else float(accuracy)
        correct = int(round(val_matches * float(accuracy))) if val_matches else 0
        today = date.today()
        existing = db.query(AccuracyTrend).filter(
            AccuracyTrend.model_version == version,
            AccuracyTrend.date == today,
        ).first()
        payload = {
            "model_version": version,
            "date": today,
            "accuracy": round(acc_pct, 2),
            "total_matches": val_matches,
            "correct_matches": correct,
        }
        if existing:
            for k, v in payload.items():
                if k != "model_version":
                    setattr(existing, k, v)
            db.commit()
        else:
            TrendService.create(db, payload)

    def _create_record(self) -> int:
        db = SessionLocal()
        try:
            rec = TrainingRecord(
                status="running",
                message="训练进行中",
                started_at=datetime.now(),
            )
            db.add(rec)
            db.commit()
            db.refresh(rec)
            return rec.id
        finally:
            db.close()

    def _finish_record(self, record_id, result: dict, started: datetime, suggestions, snapshot, matches=None):
        if not record_id or self._aborting:
            return
        db = SessionLocal()
        try:
            rec = db.query(TrainingRecord).filter(TrainingRecord.id == record_id).first()
            if not rec or rec.status != "running":
                return
            finished = datetime.now()
            rec.status = "success" if result.get("status") == "success" else "failed"
            rec.message = (result.get("message") or "")[:255]
            rec.model_version = result.get("model_version")
            rec.total_matches = result.get("total_matches") or (len(matches) if matches else 0)
            if matches:
                rec.data_start = matches[0].match_date
                rec.data_end = matches[-1].match_date
            acc = (result.get("results") or {}).get("ensemble", {}).get("validation_accuracy")
            rec.accuracy = acc
            rec.duration_ms = int((finished - started).total_seconds() * 1000)
            rec.results_json = json.dumps(result.get("results") or {}, ensure_ascii=False, default=str)
            rec.suggestions_json = json.dumps(suggestions or [], ensure_ascii=False)
            rec.snapshot_json = json.dumps(snapshot or {}, ensure_ascii=False, default=str)
            rec.finished_at = finished
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning("保存训练记录失败: %s", e)
        finally:
            db.close()

    def _mark_running_failed(self, record_id: int, message: str) -> bool:
        if not record_id:
            return False
        db = SessionLocal()
        try:
            rec = db.query(TrainingRecord).filter(TrainingRecord.id == record_id).first()
            if not rec or rec.status != "running":
                return False
            finished = datetime.now()
            rec.status = "failed"
            rec.message = (message or "训练已中断")[:255]
            rec.finished_at = finished
            if rec.started_at:
                try:
                    rec.duration_ms = max(0, int((finished - rec.started_at).total_seconds() * 1000))
                except Exception:
                    rec.duration_ms = 0
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.warning("标记训练记录失败时出错: %s", e)
            return False
        finally:
            db.close()

    def fail_abandoned_running_records(self, force: bool = False) -> int:
        """把僵死的 running 记录标为 failed。

        Redis 锁仍被心跳续期时，不打断当前这条。
        锁已释放且超过宽限（锁 TTL 的 2 倍）的记录视为进程已死。
        Redis 不可用时，只处理超过 stale_running_seconds（默认 3 小时，且不低于队列超时）的记录。
        """
        global _sweep_guard_at
        now_ts = time.time()
        if not force and now_ts - _sweep_guard_at < 30:
            return 0
        _sweep_guard_at = now_ts

        settings = lock_settings()
        grace = settings["grace_seconds"]
        stale = settings["stale_running_seconds"]
        redis_ok = train_lock.using_redis
        lock_held = train_lock.is_locked()
        shared = train_lock.read_status() or {}
        live_id = shared.get("current_record_id") if lock_held else None
        if self.is_training and self.current_record_id:
            live_id = self.current_record_id

        db = SessionLocal()
        changed = 0
        try:
            rows = db.query(TrainingRecord).filter(TrainingRecord.status == "running").all()
            now = datetime.now()
            for rec in rows:
                if live_id is not None and rec.id == live_id:
                    continue
                if self.is_training and rec.id == self.current_record_id:
                    continue
                age = _record_age_seconds(rec.started_at, now)
                abandon = False
                if redis_ok and lock_held:
                    if live_id is None:
                        abandon = age >= grace
                    else:
                        abandon = True
                elif redis_ok:
                    abandon = age >= grace
                else:
                    abandon = age >= stale
                if not abandon:
                    continue
                rec.status = "failed"
                rec.message = "训练进程已中断（锁已释放或超过僵死阈值），请重新训练"[:255]
                rec.finished_at = now
                if rec.started_at:
                    try:
                        rec.duration_ms = max(0, int(age * 1000))
                    except Exception:
                        rec.duration_ms = 0
                changed += 1
            if changed:
                db.commit()
                logger.warning("已将 %s 条僵死训练记录标为 failed", changed)
            return changed
        except Exception as e:
            db.rollback()
            logger.warning("清理僵死训练记录失败: %s", e)
            return 0
        finally:
            db.close()

    def abort_for_shutdown(self) -> None:
        """进程退出时收口本进程持有的训练：记录标失败并释放锁。"""
        if not self.is_training and not self._held_token:
            return
        self._aborting = True
        if self.current_record_id:
            self._mark_running_failed(self.current_record_id, "服务关闭，训练已中断")
        self._report(message="服务关闭，训练已中断", is_training=False, phase="aborted")
        self._release_claimed_lock()

    def _assert_runner_allowed(self, db: Session) -> None:
        """检查训练提交者账号是否仍有效；无效则抛 TrainingAborted 中止训练。

        已排队的训练最长跑 2h，期间提交者被禁用/删除时不能继续写库。
        锁状态里带 queued_user_id（train_lock.set_queued_user），
        本进程线程模式与 RQ 队列模式共用这一份信息。
        """
        if self._aborting:
            raise TrainingAborted("服务关闭，训练已中断")

        info = train_lock.read_status() or {}
        uid = info.get("queued_user_id")
        if not uid:
            return
        try:
            user = db.query(User).filter(User.id == int(uid)).first()
        except Exception as e:
            logger.warning("训练提交者校验查询失败 user=%s: %s", uid, e)
            return
        if user is None:
            raise TrainingAborted("训练提交者账号已删除")
        if not user.is_active:
            raise TrainingUserDisabled("训练提交者账号已禁用")

    def get_training_status(self) -> dict:
        self.fail_abandoned_running_records()
        shared = train_lock.read_status()
        locked = train_lock.is_locked()
        if shared:
            training = bool(shared.get("is_training")) and (locked or self.is_training)
            if shared.get("is_training") and not training:
                shared = dict(shared)
                shared["is_training"] = False
                shared["phase"] = "aborted"
                if not shared.get("message"):
                    shared["message"] = "训练已中断"
                train_lock.write_status(shared)
            return {
                "is_training": training,
                "progress": int(shared.get("progress") or 0),
                "message": shared.get("message") or "",
                "current_record_id": shared.get("current_record_id"),
            }
        return {
            "is_training": self.is_training,
            "progress": self.training_progress,
            "message": self.training_message,
            "current_record_id": self.current_record_id,
        }

    @staticmethod
    def record_to_dict(rec: TrainingRecord, include_detail: bool = True) -> dict:
        def _loads(raw, fallback):
            if not raw:
                return fallback
            try:
                return json.loads(raw)
            except Exception:
                return fallback

        data = {
            "id": rec.id,
            "status": rec.status,
            "message": rec.message,
            "model_version": rec.model_version,
            "total_matches": rec.total_matches or 0,
            "data_start": rec.data_start.isoformat() if rec.data_start else None,
            "data_end": rec.data_end.isoformat() if rec.data_end else None,
            "accuracy": float(rec.accuracy) if rec.accuracy is not None else None,
            "duration_ms": rec.duration_ms or 0,
            "started_at": rec.started_at.isoformat() if rec.started_at else None,
            "finished_at": rec.finished_at.isoformat() if rec.finished_at else None,
        }
        if include_detail:
            data["results"] = _loads(rec.results_json, {})
            data["suggestions"] = _loads(rec.suggestions_json, [])
            data["snapshot"] = _loads(rec.snapshot_json, {})
        else:
            sugg = _loads(rec.suggestions_json, [])
            data["suggestion_count"] = len(sugg)
            data["high_priority_count"] = sum(1 for s in sugg if s.get("priority") == "high")
        return data

    def list_records(self, page: int = 1, page_size: int = 20) -> dict:
        db = SessionLocal()
        try:
            query = db.query(TrainingRecord).order_by(TrainingRecord.started_at.desc())
            total = query.count()
            rows = query.offset((page - 1) * page_size).limit(page_size).all()
            return {
                "records": [self.record_to_dict(r, include_detail=False) for r in rows],
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": (total + page_size - 1) // page_size if page_size else 0,
            }
        finally:
            db.close()

    def get_record(self, record_id: int) -> dict:
        db = SessionLocal()
        try:
            rec = db.query(TrainingRecord).filter(TrainingRecord.id == record_id).first()
            if not rec:
                return None
            return self.record_to_dict(rec, include_detail=True)
        finally:
            db.close()


training_service = TrainingService()
