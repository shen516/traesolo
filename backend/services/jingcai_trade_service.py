"""竞彩足球全玩法服务：落库 / 查询。

设计要点：
- 以 500 侧主键 process_id + process_date 做 upsert（先查后更 / 插入）。
- 只保留最近 KEEP_DAYS 个销售日，过期销售日数据由调度清理。
- 提供按玩法过滤的查询，供玩法列表页使用（只读，无投注功能）。
"""
from __future__ import annotations

import itertools
import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from db import models
from services.jingcai_trade_crawler import PLAY_OPTION_ORDER

logger = logging.getLogger(__name__)

KEEP_DAYS = 7
# 玩法 key → 前端可展示的玩法名
PLAY_LABELS = {
    "dg": "单关",
    "spf": "胜平负/让球",
    "hhgg": "混合过关",
    "bf": "比分",
    "jqs": "进球数",
    "bqc": "半全场",
}
# 可查询的玩法集合（数据落库键）
PLAY_KEYS = ("spf", "nspf", "bf", "jqs", "bqc")

# 销售时序状态
SALE_STATUS_LABELS = {
    "open": "在售",
    "closing": "临场",
    "closed": "封盘",
    "started": "已开赛",
    "ended": "已完赛",
}
# 临场阈值（分钟）：距封盘/开赛 ≤ 此值时标记为「临场」
CLOSING_THRESHOLD_MIN = 15
# 前端轮询周期内视为「临近开赛、值得刷新 SP」的分钟数
NEAR_KICKOFF_MIN = 60


def upsert_crawl_result(db: Session, rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """把采集结果 upsert 到 jingcai_match_odds。返回统计。"""
    inserted = updated = 0
    today = date.today()
    for row in rows:
        process_id = (row.get("process_id") or "").strip()
        process_date = (row.get("process_date") or "").strip()
        if not process_id or not process_date:
            continue
        # 只保留最近 N 个销售日
        try:
            if (today - datetime.strptime(process_date, "%Y-%m-%d").date()).days > KEEP_DAYS:
                continue
        except ValueError:
            continue

        odds_json = json.dumps(row.get("odds") or {}, ensure_ascii=False, separators=(",", ":"))
        subactive_json = json.dumps(
            row.get("subactive") or {}, ensure_ascii=False, separators=(",", ":")
        )

        existing = (
            db.query(models.JingcaiMatchOdds)
            .filter_by(process_id=process_id, process_date=process_date)
            .first()
        )
        if existing:
            existing.home_name = row.get("home_name")
            existing.away_name = row.get("away_name")
            existing.league_name = row.get("league_name")
            existing.match_num = row.get("match_num")
            existing.fixture_id = row.get("fixture_id")
            existing.match_id_500 = row.get("match_id")
            existing.home_team_id = row.get("home_team_id")
            existing.away_team_id = row.get("away_team_id")
            existing.match_date = row.get("match_date")
            existing.match_time = row.get("match_time")
            existing.buy_end_time = row.get("buy_end_time")
            existing.is_end = bool(row.get("is_end"))
            existing.handicap = row.get("handicap")
            existing.kdg = bool(row.get("kdg"))
            existing.subactive_json = subactive_json
            existing.odds_json = odds_json
            existing.home_goals = row.get("home_goals")
            existing.away_goals = row.get("away_goals")
            existing.result = row.get("result")
            existing.source = row.get("source") or "500_trade_mix"
            existing.updated_at = datetime.now()
            updated += 1
        else:
            rec = models.JingcaiMatchOdds(
                process_id=process_id,
                process_date=process_date,
                match_num=row.get("match_num"),
                fixture_id=row.get("fixture_id"),
                match_id_500=row.get("match_id"),
                home_team_id=row.get("home_team_id"),
                away_team_id=row.get("away_team_id"),
                league_name=row.get("league_name"),
                league_rank=row.get("league_rank"),
                home_name=row.get("home_name"),
                away_name=row.get("away_name"),
                match_date=row.get("match_date"),
                match_time=row.get("match_time"),
                buy_end_time=row.get("buy_end_time"),
                is_end=bool(row.get("is_end")),
                handicap=row.get("handicap"),
                kdg=bool(row.get("kdg")),
                subactive_json=subactive_json,
                odds_json=odds_json,
                home_goals=row.get("home_goals"),
                away_goals=row.get("away_goals"),
                result=row.get("result"),
                source=row.get("source") or "500_trade_mix",
            )
            db.add(rec)
            inserted += 1

    try:
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("jingcai trade upsert commit failed: %s", e)
        raise
    return {"inserted": inserted, "updated": updated}


def cleanup_old(db: Session, keep_days: int = KEEP_DAYS) -> int:
    """删除超过 keep_days 的销售日记录。"""
    cutoff = (date.today() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    try:
        deleted = (
            db.query(models.JingcaiMatchOdds)
            .filter(models.JingcaiMatchOdds.process_date < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
        return int(deleted)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("jingcai trade cleanup failed: %s", e)
        return 0


def _load_odds(rec: models.JingcaiMatchOdds) -> Dict[str, Dict[str, Optional[float]]]:
    try:
        return json.loads(rec.odds_json or "{}")
    except (ValueError, TypeError):
        return {}


def _load_subactive(rec: models.JingcaiMatchOdds) -> Dict[str, bool]:
    try:
        return json.loads(rec.subactive_json or "{}")
    except (ValueError, TypeError):
        return {}


def query_matches(
    db: Session,
    play: str = "dg",
    process_date: Optional[str] = None,
    league_name: Optional[str] = None,
    only_single: bool = False,
    only_handicap: bool = False,
) -> List[Dict[str, Any]]:
    """按玩法查询在售比赛列表。

    play: dg(单关) | spf | nspf | hhgg(混合过关) | bf | jqs | bqc
    单关视图过滤 kdg=1；混合过关视图返回全部玩法数据；其余按对应玩法过滤。
    """
    q = db.query(models.JingcaiMatchOdds)
    if process_date:
        q = q.filter(models.JingcaiMatchOdds.process_date == process_date)
    else:
        # 默认最近有数据的销售日
        latest = (
            db.query(func.max(models.JingcaiMatchOdds.process_date)).scalar()
        )
        if latest:
            q = q.filter(models.JingcaiMatchOdds.process_date == latest)
    if league_name:
        q = q.filter(models.JingcaiMatchOdds.league_name == league_name)
    if only_single:
        q = q.filter(models.JingcaiMatchOdds.kdg.is_(True))
    q = q.order_by(models.JingcaiMatchOdds.match_num)
    recs = q.limit(500).all()

    result = []
    for rec in recs:
        odds = _load_odds(rec)
        subactive = _load_subactive(rec)
        # 按玩法过滤 SP
        if play == "dg":
            # 单关：只保留可单关的玩法（spf/nspf 按 kdg + subactive）
            if not rec.kdg:
                continue
            filtered = {k: v for k, v in odds.items() if k in PLAY_KEYS}
        elif play == "hhgg":
            filtered = {k: v for k, v in odds.items() if k in PLAY_KEYS}
        elif play == "spf":
            # 胜平负/让球：同时返回 spf 与 nspf
            filtered = {k: v for k, v in odds.items() if k in ("spf", "nspf")}
        else:
            filtered = {}
            if play in odds:
                filtered[play] = odds[play]
        item = {
            "process_id": rec.process_id,
            "process_date": rec.process_date,
            "match_num": rec.match_num,
            "fixture_id": rec.fixture_id,
            "league_name": rec.league_name,
            "home_name": rec.home_name,
            "away_name": rec.away_name,
            "match_date": rec.match_date.strftime("%Y-%m-%d") if rec.match_date else None,
            "match_time": rec.match_time,
            "buy_end_time": rec.buy_end_time,
            "is_end": rec.is_end,
            "handicap": rec.handicap,
            "kdg": rec.kdg,
            "subactive": subactive,
            "odds": filtered,
            "result": rec.result,
            "home_goals": rec.home_goals,
            "away_goals": rec.away_goals,
            "updated_at": rec.updated_at.strftime("%Y-%m-%d %H:%M:%S") if rec.updated_at else None,
        }
        item.update(derive_sale_status(rec))
        result.append(item)
    return result


def list_dates(db: Session) -> List[str]:
    """返回有数据的销售日（倒序）。"""
    rows = (
        db.query(models.JingcaiMatchOdds.process_date)
        .distinct()
        .order_by(models.JingcaiMatchOdds.process_date.desc())
        .all()
    )
    return [r[0] for r in rows]


def option_order(play: str) -> List[str]:
    return PLAY_OPTION_ORDER.get(play, [])


# ===== P3：销售时序派生 =====

_KICKOFF_RE = re.compile(r"(\d{1,2}):(\d{2})")
_END_RE = re.compile(r"(\d{1,2}):(\d{2})")


def _combine_dt(process_date: Optional[str], time_str: Optional[str]) -> Optional[datetime]:
    """把销售日 + 'HH:MM' 拼成 datetime；无法解析返回 None。"""
    if not time_str or not process_date:
        return None
    m = _KICKOFF_RE.search(time_str)
    if not m:
        return None
    try:
        base = datetime.strptime(process_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    return base.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)


def derive_sale_status(rec) -> Dict[str, Any]:
    """派生销售时序状态。

    返回 {sale_status, sale_status_label, buy_end_dt, kickoff_dt, remaining_seconds, closed}
    - sale_status: open | closing | closed | started | ended
    - remaining_seconds: 距封盘/开赛的秒数（正数），无明确时间或已过为 None
    - closed: 是否已封盘（含已开赛/已完赛），前端据此禁用选号
    仅供学习研究，不构成投注建议。
    """
    now = datetime.now()
    process_date = getattr(rec, "process_date", None)
    buy_end_dt = _combine_dt(process_date, getattr(rec, "buy_end_time", None))
    kickoff_dt = _combine_dt(
        getattr(rec, "match_date", None) and str(getattr(rec, "match_date")),
        getattr(rec, "match_time", None),
    )
    if not kickoff_dt and getattr(rec, "match_date", None):
        # match_date 为 date 对象时直接拼接
        try:
            kickoff_dt = datetime.combine(getattr(rec, "match_date"), datetime.min.time())
            kt = getattr(rec, "match_time", None)
            if kt:
                m = _KICKOFF_RE.search(str(kt))
                if m:
                    kickoff_dt = kickoff_dt.replace(hour=int(m.group(1)), minute=int(m.group(2)))
        except (TypeError, ValueError):
            kickoff_dt = None

    is_end = bool(getattr(rec, "is_end", False))

    # 优先以封盘时间判定；无封盘时间则用开赛时间
    ref_dt = buy_end_dt or kickoff_dt
    remaining_seconds: Optional[int] = None
    if ref_dt:
        remaining_seconds = int((ref_dt - now).total_seconds())

    if is_end:
        status = "ended"
        closed = True
    elif kickoff_dt and now >= kickoff_dt:
        # 已开赛：开赛后 ~120 分钟内为 started，超出视为已完赛（供回补）
        if (now - kickoff_dt) <= timedelta(minutes=120):
            status = "started"
        else:
            status = "ended"
        closed = True
    elif buy_end_dt and remaining_seconds is not None and remaining_seconds <= 0:
        status = "closed"
        closed = True
    elif ref_dt and remaining_seconds is not None and remaining_seconds <= CLOSING_THRESHOLD_MIN * 60:
        status = "closing"
        closed = False
    else:
        status = "open"
        closed = False

    return {
        "sale_status": status,
        "sale_status_label": SALE_STATUS_LABELS.get(status, status),
        "buy_end_dt": buy_end_dt.strftime("%Y-%m-%d %H:%M") if buy_end_dt else None,
        "kickoff_dt": kickoff_dt.strftime("%Y-%m-%d %H:%M") if kickoff_dt else None,
        "remaining_seconds": max(remaining_seconds, 0) if remaining_seconds is not None else None,
        "closed": closed,
    }


def count_pending_refresh(db: Session) -> Dict[str, int]:
    """统计「值得刷新 SP」的场次：临近开赛（≤NEAR_KICKOFF_MIN 且未封盘）或已开赛/完赛但缺赛果。

    供轮询任务判断是否需要真正抓取（低成本跳过）。
    """
    now = datetime.now()
    recs = db.query(models.JingcaiMatchOdds).limit(500).all()
    near_kickoff = 0
    pending_result = 0
    ended_unfilled = 0
    for rec in recs:
        st = derive_sale_status(rec)
        if st["sale_status"] in ("open", "closing"):
            # 临近开赛：距封盘/开赛 ≤ NEAR_KICKOFF_MIN
            ref_sec = st["remaining_seconds"]
            if ref_sec is not None and ref_sec <= NEAR_KICKOFF_MIN * 60:
                near_kickoff += 1
        elif st["sale_status"] in ("started", "ended"):
            # 已开赛/完赛但缺赛果 → 需要回补
            if not rec.result and (rec.home_goals is None or rec.away_goals is None):
                pending_result += 1
                if st["sale_status"] == "ended":
                    ended_unfilled += 1
    return {
        "near_kickoff": near_kickoff,
        "pending_result": pending_result,
        "ended_unfilled": ended_unfilled,
        "total": len(recs),
    }


def refresh_trigger_required(db: Session) -> bool:
    """是否应触发一次轻量采集（临近开赛或已开赛/完赛缺赛果）。"""
    stat = count_pending_refresh(db)
    return (stat["near_kickoff"] + stat["pending_result"]) > 0


def verify_results(db: Session, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """赛果校验：把采集行（含赛果）与 DB 中已开赛/完赛场次对比。

    仅做只读校验，不改写 DB；对缺赛果的 DB 记录标记 missing。
    rows 来自 JingcaiTradeCrawler.crawl(days_ahead=0, days_back=N)，每行含
    process_id / process_date / home_goals / away_goals / result。
    返回统计与不一致明细（mismatches），供分析对照（非投注建议）。
    """
    from collections import defaultdict

    # 采集侧：process_key -> 赛果
    crawled: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        pid = (row.get("process_id") or "").strip()
        pdate = (row.get("process_date") or "").strip()
        if not pid or not pdate:
            continue
        key = f"{pid}|{pdate}"
        if row.get("result") or (row.get("home_goals") is not None and row.get("away_goals") is not None):
            crawled[key] = {
                "home_goals": row.get("home_goals"),
                "away_goals": row.get("away_goals"),
                "result": row.get("result"),
            }

    if not crawled:
        return {
            "checked": 0, "matched": 0, "mismatched": 0, "missing": 0,
            "updated_result": 0, "mismatches": [], "note": BET_NOTE,
        }

    # DB 侧：只校验已开赛/完赛或已有赛果的记录
    keys = list(crawled.keys())
    recs = (
        db.query(models.JingcaiMatchOdds)
        .filter(
            (models.JingcaiMatchOdds.process_id + "|" + models.JingcaiMatchOdds.process_date).in_(keys)
        )
        .limit(5000)
        .all()
    )
    checked = matched = mismatched = missing = 0
    mismatches: List[Dict[str, Any]] = []
    # 按 process_key 聚合（DB 端 process_id|process_date 字符串拼接）
    rec_map: Dict[str, models.JingcaiMatchOdds] = {}
    for rec in recs:
        rec_map[f"{rec.process_id}|{rec.process_date}"] = rec

    for key, cr in crawled.items():
        rec = rec_map.get(key)
        if not rec:
            continue
        # 只校验「已开赛/完赛」或「已有赛果」的场次
        st = derive_sale_status(rec)
        has_db_result = bool(rec.result) or (rec.home_goals is not None and rec.away_goals is not None)
        if st["sale_status"] not in ("started", "ended") and not has_db_result:
            continue
        checked += 1
        db_result = rec.result
        cr_result = cr.get("result")
        if not cr_result:
            missing += 1
            continue
        if db_result and db_result == cr_result:
            matched += 1
            continue
        if not db_result:
            # DB 缺赛果，采集侧有 → 记为缺失（回补后应补上）
            missing += 1
        else:
            mismatched += 1
            mismatches.append({
                "process_id": rec.process_id,
                "process_date": rec.process_date,
                "match_num": rec.match_num,
                "home_name": rec.home_name,
                "away_name": rec.away_name,
                "db_result": db_result,
                "crawled_result": cr_result,
                "db_score": f"{rec.home_goals}:{rec.away_goals}" if rec.home_goals is not None and rec.away_goals is not None else None,
                "crawled_score": (
                    f"{cr.get('home_goals')}:{cr.get('away_goals')}"
                    if cr.get("home_goals") is not None and cr.get("away_goals") is not None else None
                ),
            })

    return {
        "checked": checked,
        "matched": matched,
        "mismatched": mismatched,
        "missing": missing,
        "updated_result": 0,
        "mismatches": mismatches[:50],
        "note": BET_NOTE,
    }


# ===== P4：SP 异动监测 =====
# 告警阈值：单选项 SP 涨跌幅 ≥ 此值（±）触发告警
SP_ALERT_THRESHOLD = 0.20  # 20%


def detect_sp_changes(
    db: Session,
    rows: List[Dict[str, Any]],
    threshold: float = SP_ALERT_THRESHOLD,
    max_records: int = 200,
) -> Dict[str, Any]:
    """对比采集行与 DB 既有 SP，检测异动并写入 jingcai_sp_change。

    仅对比 rows 中已存在于 DB 的记录（同 process_id+process_date），
    逐玩法逐选项比较 old_sp vs new_sp，|涨跌幅| ≥ threshold 记为 spike/告警。
    返回统计与告警列表。仅供分析，不构成投注建议。
    """
    if not rows:
        return {"changed": 0, "alerts": 0, "changes": [], "note": BET_NOTE}

    # 采集侧聚合
    new_map: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        pid = (row.get("process_id") or "").strip()
        pdate = (row.get("process_date") or "").strip()
        if not pid or not pdate:
            continue
        key = f"{pid}|{pdate}"
        new_map[key] = row

    # DB 侧既有 SP
    keys = list(new_map.keys())
    recs = (
        db.query(models.JingcaiMatchOdds)
        .filter(
            (models.JingcaiMatchOdds.process_id + "|" + models.JingcaiMatchOdds.process_date).in_(keys)
        )
        .limit(5000)
        .all()
    )
    rec_map: Dict[str, models.JingcaiMatchOdds] = {}
    for rec in recs:
        rec_map[f"{rec.process_id}|{rec.process_date}"] = rec

    changes: List[Dict[str, Any]] = []
    alerts: List[Dict[str, Any]] = []
    for key, new_row in new_map.items():
        rec = rec_map.get(key)
        if not rec:
            continue
        old_odds = _load_odds(rec)
        new_odds = new_row.get("odds") or {}
        for play_key, play_odds in new_odds.items():
            if not isinstance(play_odds, dict):
                continue
            old_play = old_odds.get(play_key) or {}
            for opt, new_sp in play_odds.items():
                if new_sp is None:
                    continue
                try:
                    new_sp_f = float(new_sp)
                except (TypeError, ValueError):
                    continue
                old_sp = old_play.get(opt)
                if old_sp is None:
                    continue
                try:
                    old_sp_f = float(old_sp)
                except (TypeError, ValueError):
                    continue
                if old_sp_f <= 0:
                    continue
                change_pct = (new_sp_f - old_sp_f) / old_sp_f
                if abs(change_pct) < 1e-6:
                    continue
                is_alert = abs(change_pct) >= threshold
                item = {
                    "process_id": rec.process_id,
                    "process_date": rec.process_date,
                    "match_num": rec.match_num,
                    "home_name": rec.home_name,
                    "away_name": rec.away_name,
                    "league_name": rec.league_name,
                    "play": play_key,
                    "option": str(opt),
                    "old_sp": round(old_sp_f, 3),
                    "new_sp": round(new_sp_f, 3),
                    "change_pct": round(change_pct, 4),
                    "change_type": "spike" if is_alert else "normal",
                    "alert": is_alert,
                    "threshold": threshold,
                }
                changes.append(item)
                if is_alert:
                    alerts.append(item)

    # 落库（只保留最近 max_records 条异动）
    now = datetime.now()
    for item in changes:
        db.add(models.JingcaiSpChange(
            process_id=item["process_id"],
            process_date=item["process_date"],
            match_num=item["match_num"],
            home_name=item["home_name"],
            away_name=item["away_name"],
            league_name=item["league_name"],
            play=item["play"],
            option=item["option"],
            old_sp=item["old_sp"],
            new_sp=item["new_sp"],
            change_pct=item["change_pct"],
            change_type=item["change_type"],
            alert=item["alert"],
            threshold=item["threshold"],
            detected_at=now,
        ))
    # 清理过旧异动记录（保留近 3 天）
    try:
        cutoff = (date.today() - timedelta(days=3)).strftime("%Y-%m-%d 00:00:00")
        db.query(models.JingcaiSpChange).filter(
            models.JingcaiSpChange.detected_at < cutoff
        ).delete(synchronize_session=False)
    except Exception as e:  # noqa: BLE001
        logger.debug("sp change cleanup failed: %s", e)

    try:
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("sp change commit failed: %s", e)
        return {"changed": 0, "alerts": 0, "changes": [], "note": BET_NOTE}

    return {
        "changed": len(changes),
        "alerts": len(alerts),
        "changes": changes[:max_records],
        "alert_list": alerts[:50],
        "threshold": threshold,
        "note": BET_NOTE,
    }


def query_sp_changes(
    db: Session,
    play: Optional[str] = None,
    only_alert: bool = False,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """查询最近 SP 异动记录（倒序）。"""
    q = db.query(models.JingcaiSpChange)
    if play:
        q = q.filter(models.JingcaiSpChange.play == play)
    if only_alert:
        q = q.filter(models.JingcaiSpChange.alert.is_(True))
    q = q.order_by(models.JingcaiSpChange.detected_at.desc(), models.JingcaiSpChange.id.desc())
    recs = q.limit(min(limit, 500)).all()
    return [
        {
            "id": r.id,
            "process_id": r.process_id,
            "process_date": r.process_date,
            "match_num": r.match_num,
            "home_name": r.home_name,
            "away_name": r.away_name,
            "league_name": r.league_name,
            "play": r.play,
            "option": r.option,
            "old_sp": float(r.old_sp) if r.old_sp is not None else None,
            "new_sp": float(r.new_sp) if r.new_sp is not None else None,
            "change_pct": float(r.change_pct) if r.change_pct is not None else None,
            "change_type": r.change_type,
            "alert": r.alert,
            "threshold": float(r.threshold) if r.threshold is not None else None,
            "detected_at": r.detected_at.strftime("%Y-%m-%d %H:%M:%S") if r.detected_at else None,
        }
        for r in recs
    ]


# ===== P4：数据导出与报表 =====

# 导出列定义（CSV 表头 / 行取值）
EXPORT_COLUMNS = [
    ("process_date", "销售日"),
    ("match_num", "场次编号"),
    ("league_name", "联赛"),
    ("home_name", "主队"),
    ("away_name", "客队"),
    ("match_time", "开赛时间"),
    ("buy_end_time", "截止时间"),
    ("sale_status", "销售状态"),
    ("handicap", "让球"),
    ("kdg", "可单关"),
    ("spf", "胜平负SP"),
    ("nspf", "让球胜平负SP"),
    ("bf", "比分SP"),
    ("jqs", "进球数SP"),
    ("bqc", "半全场SP"),
    ("result", "赛果"),
    ("home_goals", "主队进球"),
    ("away_goals", "客队进球"),
]


def _format_sp_for_export(play_odds: Dict[str, Optional[float]], option_order: List[str]) -> str:
    """把某玩法 SP dict 序列化为 'opt:sp opt:sp' 字符串。"""
    if not play_odds:
        return ""
    parts = []
    for opt in option_order:
        sp = play_odds.get(opt)
        if sp is not None:
            parts.append(f"{opt}:{sp}")
    return " ".join(parts)


def export_matches(db: Session, process_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """导出全玩法数据为 CSV 行列表（供 /export 下载）。"""
    q = db.query(models.JingcaiMatchOdds)
    if process_date:
        q = q.filter(models.JingcaiMatchOdds.process_date == process_date)
    else:
        latest = db.query(func.max(models.JingcaiMatchOdds.process_date)).scalar()
        if latest:
            q = q.filter(models.JingcaiMatchOdds.process_date == latest)
    q = q.order_by(models.JingcaiMatchOdds.match_num)
    recs = q.limit(10000).all()

    rows = []
    for rec in recs:
        odds = _load_odds(rec)
        st = derive_sale_status(rec)
        row = {
            "process_date": rec.process_date,
            "match_num": rec.match_num,
            "league_name": rec.league_name,
            "home_name": rec.home_name,
            "away_name": rec.away_name,
            "match_time": rec.match_time,
            "buy_end_time": rec.buy_end_time,
            "sale_status": st.get("sale_status_label", ""),
            "handicap": rec.handicap if rec.handicap is not None else "",
            "kdg": "是" if rec.kdg else "否",
            "spf": _format_sp_for_export(odds.get("spf") or {}, PLAY_OPTION_ORDER.get("spf", [])),
            "nspf": _format_sp_for_export(odds.get("nspf") or {}, PLAY_OPTION_ORDER.get("nspf", [])),
            "bf": _format_sp_for_export(odds.get("bf") or {}, PLAY_OPTION_ORDER.get("bf", [])),
            "jqs": _format_sp_for_export(odds.get("jqs") or {}, PLAY_OPTION_ORDER.get("jqs", [])),
            "bqc": _format_sp_for_export(odds.get("bqc") or {}, PLAY_OPTION_ORDER.get("bqc", [])),
            "result": rec.result or "",
            "home_goals": rec.home_goals if rec.home_goals is not None else "",
            "away_goals": rec.away_goals if rec.away_goals is not None else "",
        }
        rows.append(row)
    return rows


def summarize_matches(db: Session, process_date: Optional[str] = None) -> Dict[str, Any]:
    """按销售日/玩法汇总统计（供 /summary 报表）。"""
    q = db.query(models.JingcaiMatchOdds)
    if process_date:
        q = q.filter(models.JingcaiMatchOdds.process_date == process_date)
    else:
        latest = db.query(func.max(models.JingcaiMatchOdds.process_date)).scalar()
        if latest:
            q = q.filter(models.JingcaiMatchOdds.process_date == latest)
    recs = q.limit(10000).all()

    total = len(recs)
    by_league: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    play_coverage: Dict[str, int] = {k: 0 for k in PLAY_KEYS}
    ended = 0
    ended_with_result = 0
    avg_handicap_total = 0
    avg_handicap_count = 0
    kdg_count = 0

    for rec in recs:
        odds = _load_odds(rec)
        st = derive_sale_status(rec)
        if rec.league_name:
            by_league[rec.league_name] = by_league.get(rec.league_name, 0) + 1
        by_status[st.get("sale_status_label", st.get("sale_status", "unknown"))] = \
            by_status.get(st.get("sale_status_label", st.get("sale_status", "unknown")), 0) + 1
        for play in PLAY_KEYS:
            if odds.get(play):
                play_coverage[play] = play_coverage.get(play, 0) + 1
        if st.get("sale_status") in ("started", "ended"):
            ended += 1
            if rec.result:
                ended_with_result += 1
        if rec.handicap is not None:
            avg_handicap_total += rec.handicap
            avg_handicap_count += 1
        if rec.kdg:
            kdg_count += 1

    return {
        "process_date": recs[0].process_date if recs else (process_date or ""),
        "total_matches": total,
        "ended_matches": ended,
        "ended_with_result": ended_with_result,
        "result_coverage": round(ended_with_result / ended, 4) if ended else 0.0,
        "kdg_matches": kdg_count,
        "avg_handicap": round(avg_handicap_total / avg_handicap_count, 3) if avg_handicap_count else None,
        "by_league": sorted(by_league.items(), key=lambda x: -x[1]),
        "by_status": by_status,
        "play_coverage": play_coverage,
        "dates": list_dates(db),
        "note": BET_NOTE,
    }


# ===== P2：选号奖金计算 =====
# 过关方式 → 该方式包含的串关宽度集合（宽度=每注包含的场次数）。
# 注数按 C(实际场次数, 宽度) 自动展开，因此同一张表可适配不同场次数。
PASS_STRUCT: Dict[str, List[int]] = {
    "2x1": [2],
    "3x1": [3], "3x3": [2], "3x4": [2, 3],
    "4x1": [4], "4x4": [3], "4x5": [3, 4], "4x6": [2], "4x11": [2, 3, 4],
    "5x1": [5], "5x5": [4], "5x6": [4, 5], "5x10": [2],
    "5x16": [3, 4, 5], "5x20": [2, 3], "5x26": [2, 3, 4, 5],
    "6x1": [6], "6x6": [5], "6x7": [5, 6], "6x15": [2],
    "6x22": [4, 5, 6], "6x42": [3, 4, 5, 6], "6x57": [2, 3, 4, 5, 6],
}

BET_NOTE = "仅供学习研究与数据分析，不构成投注建议。"


def _load_sp_map(db: Session, keys: List[tuple]) -> Dict[str, models.JingcaiMatchOdds]:
    """按 (process_id, process_date) 批量取记录。"""
    if not keys:
        return {}
    process_ids = list({k[0] for k in keys})
    recs = (
        db.query(models.JingcaiMatchOdds)
        .filter(models.JingcaiMatchOdds.process_id.in_(process_ids))
        .all()
    )
    want = set(keys)
    return {
        f"{r.process_id}|{r.process_date}": r
        for r in recs
        if (r.process_id, r.process_date) in want
    }


def _iter_bets(option_groups: List[List[Dict[str, Any]]]):
    """为一组比赛（每场一个选项列表）展开所有注：笛卡尔积，返回 (sp乘积, 选项列表)。"""
    for choice in itertools.product(*option_groups):
        sp_product = 1.0
        for sel in choice:
            sp_product *= float(sel["sp"])
        yield sp_product, list(choice)


def _group_min_max(option_groups: List[List[Dict[str, Any]]]) -> tuple:
    """一组比赛的最低保/最高保 SP 乘积（每场取该场最小/最大 SP）。"""
    lo = hi = 1.0
    for group in option_groups:
        sps = [float(s["sp"]) for s in group]
        lo *= min(sps)
        hi *= max(sps)
    return lo, hi


def calculate_bet(
    db: Session,
    selections: List[Dict[str, Any]],
    pass_types: Optional[List[str]] = None,
    times: int = 1,
    single_amount: float = 2.0,
    detail_limit: int = 200,
) -> Dict[str, Any]:
    """按选号计算注数 / 总金额 / 预计奖金区间 / 明细。

    selections: [{process_id, process_date, play, option}]
    pass_types: ["single"] 表示单关；["3x1"] / ["2x1","3x1"] 等表示过关。
                为空时：仅 1 场自动单关，多场默认 N串1。
    """
    times = max(1, min(int(times or 1), 999))
    single_amount = 2.0 if single_amount is None else float(single_amount)
    if single_amount <= 0:
        single_amount = 2.0

    if not selections:
        return {
            "ok": False, "reason": "未选择任何选项",
            "bet_count": 0, "total_amount": 0.0, "min_amount": 0.0,
            "max_amount": 0.0, "details": [], "invalid": [], "note": BET_NOTE,
        }

    # 去重（同场同玩法同选项只算一次）
    uniq: Dict[str, Dict[str, Any]] = {}
    for sel in selections:
        key = f"{sel.get('process_id')}|{sel.get('process_date')}|{sel.get('play')}|{sel.get('option')}"
        if key not in uniq:
            uniq[key] = {
                "process_id": (sel.get("process_id") or "").strip(),
                "process_date": (sel.get("process_date") or "").strip(),
                "play": (sel.get("play") or "").strip(),
                "option": str(sel.get("option")),
            }

    keys = [(s["process_id"], s["process_date"]) for s in uniq.values()]
    rec_map = _load_sp_map(db, keys)

    invalid: List[Dict[str, Any]] = []
    valid: List[Dict[str, Any]] = []
    for sel in uniq.values():
        rec = rec_map.get(f"{sel['process_id']}|{sel['process_date']}")
        if not rec:
            invalid.append({**sel, "reason": "比赛不存在或已过期"})
            continue
        odds = _load_odds(rec)
        sp = (odds.get(sel["play"]) or {}).get(sel["option"])
        if sp is None:
            invalid.append({**sel, "reason": "该选项暂无可售 SP"})
            continue
        valid.append({
            **sel,
            "sp": float(sp),
            "home_name": rec.home_name,
            "away_name": rec.away_name,
            "match_num": rec.match_num,
            "league_name": rec.league_name,
        })

    if not valid:
        return {
            "ok": False, "reason": "没有可计算的选项（SP 缺失或比赛过期）",
            "bet_count": 0, "total_amount": 0.0, "min_amount": 0.0,
            "max_amount": 0.0, "details": [], "invalid": invalid, "note": BET_NOTE,
        }

    # 按比赛分组：同一场比赛的多个选中项视为复式，展开组合
    match_groups: Dict[str, List[Dict[str, Any]]] = {}
    for sel in valid:
        mid = f"{sel['process_id']}|{sel['process_date']}"
        match_groups.setdefault(mid, []).append(sel)

    match_ids = list(match_groups.keys())
    n_matches = len(match_ids)

    # 解析过关方式
    pt_list = [p.strip() for p in (pass_types or []) if p and p.strip()]
    is_single = "single" in pt_list or (not pt_list and n_matches == 1)
    if invalid_pass := [p for p in pt_list if p != "single" and p not in PASS_STRUCT]:
        return {
            "ok": False, "reason": f"不支持的过关方式: {','.join(invalid_pass)}",
            "bet_count": 0, "total_amount": 0.0, "min_amount": 0.0,
            "max_amount": 0.0, "details": [], "invalid": invalid, "note": BET_NOTE,
        }

    details: List[Dict[str, Any]] = []
    bet_count = 0
    min_amount = 0.0
    max_amount = 0.0

    if is_single:
        # 单关：每个选中项各 1 注，奖金 = SP × 单注金额 × 倍数
        for sel in valid:
            bet_amount = sel["sp"] * single_amount * times
            bet_count += 1
            min_amount += bet_amount
            max_amount += bet_amount
            if len(details) < detail_limit:
                details.append({
                    "items": [{
                        "match_num": sel.get("match_num"),
                        "home_name": sel.get("home_name"),
                        "away_name": sel.get("away_name"),
                        "play": sel["play"],
                        "option": sel["option"],
                        "sp": sel["sp"],
                    }],
                    "sp_product": round(sel["sp"], 4),
                    "amount": round(bet_amount, 2),
                    "pass_type": "single",
                })
        effective_pass = ["single"]
    else:
        # 过关：合并各 pass_type 的串关宽度
        widths: List[int] = []
        for pt in (pt_list or [f"{n_matches}x1"]):
            for w in PASS_STRUCT.get(pt, []):
                if w not in widths:
                    widths.append(w)
        widths.sort()
        effective_pass = [p for p in pt_list if p != "single"] or [f"{n_matches}x1"]

        for width in widths:
            if width > n_matches:
                continue
            for combo in itertools.combinations(match_ids, width):
                option_groups = [match_groups[mid] for mid in combo]
                lo_prod, hi_prod = _group_min_max(option_groups)
                combo_count = 1
                for g in option_groups:
                    combo_count *= len(g)
                bet_count += combo_count
                # 复式组合实际只中 1 注，奖金区间按单注最高/最低计，不乘注数
                min_amount += lo_prod * single_amount * times
                max_amount += hi_prod * single_amount * times
                # 明细（仅在未超上限时逐注展开）
                if len(details) < detail_limit:
                    for sp_product, choice in _iter_bets(option_groups):
                        if len(details) >= detail_limit:
                            break
                        details.append({
                            "items": [{
                                "match_num": s.get("match_num"),
                                "home_name": s.get("home_name"),
                                "away_name": s.get("away_name"),
                                "play": s["play"],
                                "option": s["option"],
                                "sp": s["sp"],
                            } for s in choice],
                            "sp_product": round(sp_product, 4),
                            "amount": round(sp_product * single_amount * times, 2),
                            "pass_type": f"{width}x1",
                        })

    total_amount = round(bet_count * single_amount * times, 2)
    return {
        "ok": bet_count > 0,
        "reason": "" if bet_count > 0 else "所选场次不足以组成该过关方式",
        "bet_count": bet_count,
        "total_amount": total_amount,
        "times": times,
        "single_amount": single_amount,
        "match_count": n_matches,
        "pass_types": effective_pass,
        "min_amount": round(min_amount, 2),
        "max_amount": round(max_amount, 2),
        "details": details,
        "truncated": bet_count > len(details),
        "invalid": invalid,
        "note": BET_NOTE,
    }
