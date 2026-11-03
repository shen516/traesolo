"""数据质量看板：覆盖率、训练滞后、队名/UCL 映射缺口。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import distinct, func, or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

QUALITY_LEAGUES = (
    "EPL", "LALIGA", "BUNDES", "SERIEA", "LIGUE1", "UCL", "UEL", "WC",
    "MLS", "BRA", "SWE", "FIN", "NOR", "K1", "ECH",
)
XG_DEFAULT = Decimal("1.350")


class DataQualityService:
    """聚合重点联赛数据覆盖、训练滞后与映射缺口。"""

    def _priority_leagues(self) -> List[str]:
        """质量看板分联赛：重点 + 扩展 + P3 双源 + WC。"""
        from services.real_team_crawler import get_stats_leagues
        return list(dict.fromkeys([*get_stats_leagues(), "WC"]))

    def _compute_totals_and_model(self, db: Session) -> dict:
        """全局汇总 KPI 与当前模型信息（不含分联赛循环）。"""
        from db.models import Match, MatchPlayerStat, MatchPrediction, MatchTeamStat, Team
        from services import ModelService

        finished_n = int(
            db.query(func.count(Match.id))
            .filter(Match.status == "finished", Match.home_goals.isnot(None))
            .scalar()
            or 0
        )
        player_stats_n = int(
            db.query(func.count(distinct(MatchPlayerStat.match_id))).scalar() or 0
        )
        team_only_n = int(
            db.query(func.count(distinct(MatchTeamStat.match_id)))
            .filter(~MatchTeamStat.match_id.in_(db.query(MatchPlayerStat.match_id).distinct()))
            .scalar()
            or 0
        )
        stats_n = player_stats_n + team_only_n
        env_finished = int(
            db.query(func.count(Match.id))
            .filter(
                Match.status == "finished",
                Match.weather.isnot(None),
                Match.weather != "",
                Match.pitch_condition.isnot(None),
                Match.pitch_condition != "",
            )
            .scalar()
            or 0
        )
        env_upcoming = int(
            db.query(func.count(Match.id))
            .filter(
                Match.status.in_(["upcoming", "live"]),
                Match.weather.isnot(None),
                Match.weather != "",
                Match.pitch_condition.isnot(None),
                Match.pitch_condition != "",
            )
            .scalar()
            or 0
        )
        upcoming_n = int(
            db.query(func.count(Match.id))
            .filter(Match.status.in_(["upcoming", "live"]))
            .scalar()
            or 0
        )
        xg_teams = int(
            db.query(func.count(Team.id))
            .filter(or_(Team.xg_for != XG_DEFAULT, Team.xg_against != XG_DEFAULT))
            .scalar()
            or 0
        )
        pred_total = int(db.query(func.count(MatchPrediction.id)).scalar() or 0)
        pred_with_meta = 0
        pred_with_scenarios = 0
        try:
            pred_with_meta = int(
                db.query(func.count(MatchPrediction.id))
                .filter(
                    MatchPrediction.meta_json.isnot(None),
                    MatchPrediction.meta_json != "",
                    MatchPrediction.meta_json != "{}",
                )
                .scalar()
                or 0
            )
            # 粗略统计：meta 含 primary_scenario 视为已写入分析场景
            pred_with_scenarios = int(
                db.query(func.count(MatchPrediction.id))
                .filter(MatchPrediction.meta_json.like("%primary_scenario%"))
                .scalar()
                or 0
            )
        except Exception:
            pred_with_meta = 0
            pred_with_scenarios = 0

        current = ModelService.get_current(db)
        lag = self._training_lag(db, current, finished_n, stats_n, xg_teams)

        weights_has_hp = False
        if current and current.weights_json:
            try:
                payload = json.loads(current.weights_json)
                weights_has_hp = isinstance(payload.get("hyperparams"), dict)
            except Exception:
                weights_has_hp = False

        totals = {
            "finished_matches": finished_n,
            "matches_with_player_stats": stats_n,
            "player_stats_coverage_pct": round(100.0 * stats_n / finished_n, 1) if finished_n else 0,
            "env_finished": env_finished,
            "env_finished_pct": round(100.0 * env_finished / finished_n, 1) if finished_n else 0,
            "env_upcoming": env_upcoming,
            "upcoming_matches": upcoming_n,
            "env_upcoming_pct": round(100.0 * env_upcoming / upcoming_n, 1) if upcoming_n else 0,
            "xg_teams_non_default": xg_teams,
            "predictions": pred_total,
            "predictions_with_meta": pred_with_meta,
            "predictions_with_scenarios": pred_with_scenarios,
        }
        model = {
            "version": current.version if current else None,
            "accuracy": float(current.accuracy) if current and current.accuracy is not None else None,
            "training_data_start": current.training_data_start.isoformat() if current and current.training_data_start else None,
            "training_data_end": current.training_data_end.isoformat() if current and current.training_data_end else None,
            "weights_has_hyperparams": weights_has_hp,
        }
        return {
            "totals": totals,
            "training_lag": lag,
            "model": model,
            "weights_has_hyperparams": weights_has_hp,
            "env_finished": env_finished,
            "finished_n": finished_n,
        }

    def summary(self, db: Session) -> dict:
        """KPI + 训练滞后 + 基础建议（不含分联赛表）。"""
        core = self._compute_totals_and_model(db)
        actions = self._suggested_actions(
            [],
            core["training_lag"],
            core["weights_has_hyperparams"],
            core["env_finished"],
            core["finished_n"],
        )
        quality_alerts = []
        try:
            from services.quality_alert_service import list_open_quality_alerts
            quality_alerts = list_open_quality_alerts(db)
        except Exception as e:
            logger.debug("list quality alerts failed: %s", e)
        if quality_alerts:
            high = any(a.get("level") == "high" for a in quality_alerts)
            actions.insert(0, {
                "priority": "high" if high else "mid",
                "title": f"{len(quality_alerts)} 条未处理数据质量告警",
                "action": "见数据质量看板；处理映射别名或检查采集日志 / 定时任务 quality_alert_check",
            })
        sla_meta = {}
        try:
            from services.crawler_sla import sla_enabled, sla_section
            sec = sla_section()
            sla_meta = {
                "enabled": sla_enabled(),
                "budget_per_run": int(sec.get("budget_per_run") or 900),
                "min_limit": int(sec.get("min_limit") or 20),
                "max_limit": int(sec.get("max_limit") or 400),
                "priority_budget": int(sec.get("priority_budget") or 400),
            }
        except Exception:
            sla_meta = {"enabled": False}
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "priority_leagues": self._priority_leagues(),
            "totals": core["totals"],
            "training_lag": core["training_lag"],
            "model": core["model"],
            "actions": actions,
            "quality_alerts": quality_alerts,
            "sla": sla_meta,
        }

    def by_league(
        self,
        db: Session,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """分联赛覆盖明细，支持分页（默认一次取全部分联赛）。"""
        leagues = self._priority_leagues()
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        total = len(leagues)
        start = (page - 1) * page_size
        slice_leagues = leagues[start : start + page_size]
        rows = [self._league_coverage(db, lid) for lid in slice_leagues]
        sla_plan = {}
        try:
            from services.crawler_sla import apply_sla_to_rows
            sla_plan = apply_sla_to_rows(rows)
        except Exception as e:
            logger.debug("apply SLA to coverage rows failed: %s", e)
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "by_league": rows,
            "sla": {
                "enabled": sla_plan.get("enabled"),
                "budget": sla_plan.get("budget"),
                "min_limit": sla_plan.get("min_limit"),
                "max_limit": sla_plan.get("max_limit"),
                "allocated": sla_plan.get("allocated"),
            },
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": (total + page_size - 1) // page_size if page_size else 0,
            },
        }

    def overview(self, db: Session) -> dict:
        """完整看板（兼容旧接口）。"""
        summary = self.summary(db)
        league_block = self.by_league(db, page=1, page_size=100)
        by_league = league_block["by_league"]
        actions = self._suggested_actions(
            by_league,
            summary["training_lag"],
            summary["model"]["weights_has_hyperparams"],
            summary["totals"]["env_finished"],
            summary["totals"]["finished_matches"],
        )
        alerts = summary.get("quality_alerts") or []
        if alerts:
            high = any(a.get("level") == "high" for a in alerts)
            actions.insert(0, {
                "priority": "high" if high else "mid",
                "title": f"{len(alerts)} 条未处理数据质量告警",
                "action": "见数据质量看板；处理映射别名或检查采集日志 / 定时任务 quality_alert_check",
            })
        return {
            **summary,
            "by_league": by_league,
            "actions": actions,
            "sla": league_block.get("sla") or summary.get("sla"),
        }

    def mapping_gaps(self, db: Session, *, limit_per_league: int = 40) -> dict:
        """完整映射缺口（兼容旧接口）。"""
        summary_payload = self.mapping_gaps_summary(db)
        rows_payload = self.mapping_gaps_rows(
            db,
            page=1,
            page_size=max(20, limit_per_league * 2),
            limit_per_league=limit_per_league,
        )
        return {
            **summary_payload,
            "by_league": rows_payload.get("by_league", {}),
            "rows": rows_payload.get("rows", []),
        }

    def mapping_gaps_summary(self, db: Session) -> dict:
        """映射缺口 KPI + 难映射球队（不含场次明细）。"""
        from services.real_team_crawler import get_priority_leagues

        leagues = list(get_priority_leagues())
        summary = {
            "no_source": 0,
            "mapping_gap": 0,
            "pending_crawl": 0,
            "total_missing": 0,
        }
        weak_teams: List[dict] = []
        seen_teams: set = set()
        league_stats: List[dict] = []

        for lid in leagues:
            _, partial, weak, listed = self._scan_league_mapping_gaps(
                db,
                lid,
                limit_per_league=0,
                include_rows=False,
                seen_teams=seen_teams,
            )
            for key in ("no_source", "mapping_gap", "pending_crawl", "total_missing"):
                summary[key] = summary.get(key, 0) + int(partial.get(key) or 0)
            weak_teams.extend(weak)
            if partial.get("total_missing"):
                league_stats.append({
                    "league_id": lid,
                    "total_missing": partial["total_missing"],
                    "listed": listed,
                })

        weak_teams.sort(key=lambda x: (x["map_score"], x["league_id"] or "", x["team_id"]))
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "summary": summary,
            "league_stats": league_stats,
            "weak_teams": weak_teams[:80],
            "notes": self._mapping_gap_notes(),
        }

    def mapping_gaps_rows(
        self,
        db: Session,
        *,
        page: int = 1,
        page_size: int = 20,
        league_id: str | None = None,
        reason: str | None = None,
        limit_per_league: int = 50,
    ) -> dict:
        """映射缺口场次明细分页。"""
        from services.real_team_crawler import get_priority_leagues

        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        limit_per_league = max(5, min(limit_per_league, 100))
        leagues = [league_id] if league_id else list(get_priority_leagues())

        rows: List[dict] = []
        by_league: Dict[str, list] = {}
        seen_teams: set = set()
        for lid in leagues:
            league_rows, _, _, _ = self._scan_league_mapping_gaps(
                db,
                lid,
                limit_per_league=limit_per_league,
                include_rows=True,
                seen_teams=seen_teams,
            )
            by_league[lid] = league_rows
            rows.extend(league_rows)

        if reason:
            rows = [r for r in rows if r.get("reason") == reason]
            by_league = {
                lid: [r for r in league_rows if r.get("reason") == reason]
                for lid, league_rows in by_league.items()
            }

        rows.sort(key=lambda r: r.get("match_date") or "", reverse=True)
        total = len(rows)
        start = (page - 1) * page_size
        page_rows = rows[start : start + page_size]
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "rows": page_rows,
            "by_league": by_league,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": (total + page_size - 1) // page_size if page_size else 0,
            },
        }

    def _mapping_gap_notes(self) -> List[str]:
        return [
            "no_source：UCL 资格赛等 ESPN 通常无射门源，属数据边界。",
            "mapping_gap：队名/别名难映射到 ESPN，补采会被跳过。",
            "pending_crawl：可映射但尚未补到 match_player_stats，可用 backfill。",
        ]

    def _scan_league_mapping_gaps(
        self,
        db: Session,
        lid: str,
        *,
        limit_per_league: int = 40,
        include_rows: bool = True,
        seen_teams: set | None = None,
    ) -> tuple:
        """扫描单联赛缺统计场次。返回 (rows, summary, weak_teams, listed_count)。"""
        from db.models import Match, MatchPlayerStat, MatchTeamStat, Team
        from services.crawler_service import crawler_service

        if seen_teams is None:
            seen_teams = set()

        covered = (
            db.query(MatchPlayerStat.match_id)
            .union(db.query(MatchTeamStat.match_id))
        )
        scan_limit = max(80, limit_per_league * 2) if limit_per_league else 500
        missing = (
            db.query(Match)
            .filter(
                Match.league_id == lid,
                Match.status == "finished",
                Match.home_goals.isnot(None),
                ~Match.id.in_(covered),
            )
            .order_by(Match.match_date.desc())
            .limit(scan_limit)
            .all()
        )

        rows: List[dict] = []
        partial = {
            "no_source": 0,
            "mapping_gap": 0,
            "pending_crawl": 0,
            "total_missing": 0,
        }
        weak: List[dict] = []

        for m in missing:
            reason, detail = self._classify_missing(m)
            home = db.query(Team).filter(Team.id == m.home_team_id).first()
            away = db.query(Team).filter(Team.id == m.away_team_id).first()
            home_score = crawler_service._team_espn_map_score(home)
            away_score = crawler_service._team_espn_map_score(away)
            if reason == "mapping_gap" or (home_score + away_score) <= 2:
                reason = "mapping_gap" if reason != "no_source" else reason
                for t, sc in ((home, home_score), (away, away_score)):
                    if not t or sc > 2 or t.id in seen_teams:
                        continue
                    seen_teams.add(t.id)
                    weak.append({
                        "team_id": t.id,
                        "name": t.name,
                        "short_name": t.short_name,
                        "league_id": t.league_id,
                        "map_score": sc,
                    })
            partial[reason] = partial.get(reason, 0) + 1
            partial["total_missing"] += 1
            if include_rows and (limit_per_league <= 0 or len(rows) < limit_per_league):
                rows.append({
                    "match_id": m.id,
                    "league_id": lid,
                    "match_date": m.match_date.isoformat() if m.match_date else None,
                    "stage": m.stage,
                    "round_name": m.round_name,
                    "home_team_id": m.home_team_id,
                    "away_team_id": m.away_team_id,
                    "home_name": getattr(home, "name", None),
                    "away_name": getattr(away, "name", None),
                    "home_map_score": home_score,
                    "away_map_score": away_score,
                    "reason": reason,
                    "detail": detail,
                })

        return rows, partial, weak, len(rows)

    def _league_coverage(self, db: Session, league_id: str) -> dict:
        from db.models import Match, MatchPlayerStat, MatchTeamStat

        finished = int(
            db.query(func.count(Match.id))
            .filter(
                Match.league_id == league_id,
                Match.status == "finished",
                Match.home_goals.isnot(None),
            )
            .scalar()
            or 0
        )
        with_player = int(
            db.query(func.count(distinct(MatchPlayerStat.match_id)))
            .join(Match, Match.id == MatchPlayerStat.match_id)
            .filter(
                Match.league_id == league_id,
                Match.status == "finished",
            )
            .scalar()
            or 0
        )
        with_team_only = int(
            db.query(func.count(distinct(MatchTeamStat.match_id)))
            .join(Match, Match.id == MatchTeamStat.match_id)
            .filter(
                Match.league_id == league_id,
                Match.status == "finished",
                ~Match.id.in_(db.query(MatchPlayerStat.match_id).distinct()),
            )
            .scalar()
            or 0
        )
        with_stats = with_player + with_team_only
        with_env = int(
            db.query(func.count(Match.id))
            .filter(
                Match.league_id == league_id,
                Match.status == "finished",
                Match.weather.isnot(None),
                Match.weather != "",
                Match.pitch_condition.isnot(None),
                Match.pitch_condition != "",
            )
            .scalar()
            or 0
        )
        missing = max(0, finished - with_stats)
        # UCL：资格赛缺场不计入「可补」压力
        no_source = 0
        if league_id == "UCL" and missing:
            covered = (
                db.query(MatchPlayerStat.match_id)
                .union(db.query(MatchTeamStat.match_id))
                .subquery()
            )
            no_source = int(
                db.query(func.count(Match.id))
                .filter(
                    Match.league_id == "UCL",
                    Match.status == "finished",
                    Match.home_goals.isnot(None),
                    ~Match.id.in_(db.query(covered.c.match_id)),
                    or_(
                        Match.stage == "qualifying",
                        Match.round_name.contains("资格"),
                    ),
                )
                .scalar()
                or 0
            )
        crawlable_missing = max(0, missing - no_source)
        return {
            "league_id": league_id,
            "finished": finished,
            "with_player_stats": with_stats,
            "with_player_rows": with_player,
            "with_team_stats_only": with_team_only,
            "stats_coverage_pct": round(100.0 * with_stats / finished, 1) if finished else 0,
            "missing_stats": missing,
            "no_source_missing": no_source,
            "crawlable_missing": crawlable_missing,
            "with_environment": with_env,
            "env_coverage_pct": round(100.0 * with_env / finished, 1) if finished else 0,
        }

    def _training_lag(
        self,
        db: Session,
        current,
        finished_n: int,
        stats_n: int,
        xg_teams: int,
    ) -> dict:
        from db.models import Match, TrainingRecord

        latest_finished = (
            db.query(func.max(Match.match_date))
            .filter(Match.status == "finished", Match.home_goals.isnot(None))
            .scalar()
        )
        train_end = current.training_data_end if current else None
        days_behind = None
        if latest_finished and train_end:
            days_behind = (latest_finished - train_end).days

        last_record = (
            db.query(TrainingRecord)
            .filter(TrainingRecord.status == "success")
            .order_by(TrainingRecord.id.desc())
            .first()
        )
        train_samples = int(last_record.total_matches) if last_record and last_record.total_matches else None
        sample_gap = (finished_n - train_samples) if train_samples is not None else None

        snap_stats = None
        if last_record and last_record.snapshot_json:
            try:
                snap = json.loads(last_record.snapshot_json)
                snap_stats = snap.get("matches_with_player_stats")
            except Exception:
                snap_stats = None

        stale = bool(
            (days_behind is not None and days_behind > 3)
            or (sample_gap is not None and sample_gap >= 30)
            or (snap_stats is not None and stats_n - int(snap_stats) >= 200)
        )
        return {
            "is_stale": stale,
            "latest_finished_date": latest_finished.isoformat() if latest_finished else None,
            "model_data_end": train_end.isoformat() if train_end else None,
            "days_behind": days_behind,
            "db_finished_matches": finished_n,
            "last_train_samples": train_samples,
            "sample_gap": sample_gap,
            "db_matches_with_stats": stats_n,
            "last_train_stats_hint": snap_stats,
            "db_xg_teams": xg_teams,
            "last_train_at": last_record.finished_at.isoformat() if last_record and last_record.finished_at else None,
            "last_train_version": last_record.model_version if last_record else None,
        }

    def _classify_missing(self, match) -> tuple:
        lid = str(getattr(match, "league_id", "") or "").upper()
        stage = str(getattr(match, "stage", "") or "").strip().lower()
        rn = str(getattr(match, "round_name", "") or "")
        if lid == "UCL" and (stage == "qualifying" or "资格" in rn):
            return "no_source", "UCL 资格赛 ESPN 通常无射门源"
        if lid == "UCL" and any(k in rn for k in ("第一圈", "第二圈")) and stage in ("", "play_in"):
            # 圈次可能无源，标 pending 但仍提示
            return "pending_crawl", "UCL 圈次阶段，优先尝试补采"
        return "pending_crawl", "缺 match_player_stats，可 backfill"

    def _suggested_actions(
        self,
        by_league: list,
        lag: dict,
        weights_has_hp: bool,
        env_finished: int,
        finished_n: int,
    ) -> List[dict]:
        actions = []
        if lag.get("is_stale"):
            actions.append({
                "priority": "high",
                "title": "训练滞后于库内数据",
                "action": "数据质量页点击「仅重训」或「执行 P0 补齐+训练」；亦可 POST /api/v1/model/train",
                "cta": "train",
            })
        if not weights_has_hp:
            actions.append({
                "priority": "high",
                "title": "当前权重缺少 hyperparams",
                "action": "执行「仅重训」或 P0，使分联赛 K/主场超参写入 weights_json",
                "cta": "train",
            })
        crawlable = sum(int(x.get("crawlable_missing") or 0) for x in by_league)
        if crawlable >= 50:
            actions.append({
                "priority": "mid",
                "title": f"约 {crawlable} 场可补射门统计",
                "action": "执行 P0，或 POST /crawler/matches/player-stats/backfill?prefer_older=true；难映射队可在数据质量页确认别名",
                "cta": "p0",
            })
        env_pct = (100.0 * env_finished / finished_n) if finished_n else 0
        if env_pct < 30:
            actions.append({
                "priority": "mid",
                "title": f"完赛环境覆盖仅 {env_pct:.0f}%",
                "action": "点击「仅完赛环境」或 POST /crawler/environment/backfill?finished_only=true",
                "cta": "env_finished",
            })
        # 重点联赛伤病提示（无分联赛表时也给出）
        actions.append({
            "priority": "low",
            "title": "重点联赛伤病风控",
            "action": "定时 injury_crawl 或数据质量页「拉取伤病」刷新临场 injury 预警",
            "cta": "injury",
        })
        actions.append({
            "priority": "low",
            "title": "未赛预测补齐多场景 meta",
            "action": "模型概览「一键补齐过期未赛」或赛事列表「重算本页过期」（缺 scenarios 视为过期）",
            "cta": "recalc_stale",
        })
        sla_misses = [x for x in by_league if x.get("sla_met") is False]
        for row in sla_misses[:3]:
            actions.append({
                "priority": "mid",
                "title": (
                    f"{row.get('league_id')} 可补覆盖 {row.get('sla_coverage_pct')}%"
                    f" 低于 SLA {row.get('sla_target_pct')}%"
                ),
                "action": (
                    f"下次配额约 {row.get('sla_limit')} 场；"
                    "执行 P0 或 POST /crawler/matches/player-stats/backfill"
                ),
            })
        uel = next((x for x in by_league if str(x.get("league_id") or "") == "UEL"), None)
        if uel:
            finished = int(uel.get("finished") or 0)
            coverage = float(uel.get("stats_coverage_pct") or 0)
            if finished < 40 or coverage < 50:
                actions.append({
                    "priority": "high" if finished < 20 else "mid",
                    "title": f"UEL 样本偏少（完赛 {finished}，射门覆盖 {coverage:.0f}%）",
                    "action": "数据质量页「UEL 补齐+训练」，或 POST /crawler/uel/catchup",
                })
        return actions


data_quality_service = DataQualityService()
