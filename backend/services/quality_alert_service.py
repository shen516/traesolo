"""采集质量告警：射门 miss 连续失败、完赛回写停滞、映射缺口环比。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

KEY_PREFIX = "quality:"
SNAPSHOT_LEAGUE_NAME = "quality_snapshot"


def _crawler_cfg() -> dict:
    try:
        from db.database import config as app_config
        return dict((app_config or {}).get("crawler") or {})
    except Exception:
        return {}


def quality_alert_cfg(cfg: Optional[dict] = None) -> dict:
    raw = (cfg if cfg is not None else _crawler_cfg()).get("quality_alerts") or {}
    return dict(raw) if isinstance(raw, dict) else {}


def alerts_enabled(cfg: Optional[dict] = None) -> bool:
    sec = quality_alert_cfg(cfg)
    if "enabled" not in sec:
        return True
    return bool(sec.get("enabled"))


def alert_key(kind: str, league_id: Optional[str] = None) -> str:
    if league_id:
        return f"{KEY_PREFIX}{kind}:{league_id}"
    return f"{KEY_PREFIX}{kind}"


def serialize_alert(alert) -> dict:
    return {
        "id": getattr(alert, "id", None),
        "match_name": getattr(alert, "match_name", None),
        "type": getattr(alert, "type", None),
        "level": getattr(alert, "level", None),
        "description": getattr(alert, "description", None),
        "recommended_action": getattr(alert, "recommended_action", None),
        "created_at": alert.created_at.isoformat() if getattr(alert, "created_at", None) else None,
        "kind": _kind_from_key(getattr(alert, "match_name", None)),
    }


def _kind_from_key(match_name: Optional[str]) -> str:
    text = str(match_name or "")
    if not text.startswith(KEY_PREFIX):
        return "quality"
    parts = text.split(":")
    return parts[1] if len(parts) > 1 else "quality"


def miss_rate_from_log(log, min_found: int = 5) -> Optional[float]:
    """返回 miss/found；样本不足时返回 None。"""
    found = int(getattr(log, "found_count", 0) or 0)
    if found < int(min_found):
        return None
    miss = None
    raw = getattr(log, "crawled_data", None)
    if raw:
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(payload, dict) and payload.get("miss_count") is not None:
                miss = int(payload.get("miss_count") or 0)
        except Exception:
            miss = None
    if miss is None:
        miss = max(0, found - int(getattr(log, "updated_count", 0) or 0))
    return miss / found if found else None


def miss_streak_triggered(
    rates: List[Optional[float]],
    *,
    streak: int = 3,
    threshold: float = 0.5,
) -> bool:
    if len(rates) < streak:
        return False
    window = rates[:streak]
    if any(r is None for r in window):
        return False
    return all(float(r) > threshold for r in window)


def mapping_gap_wow_triggered(
    current: int,
    previous: int,
    *,
    ratio: float = 1.2,
    min_delta: int = 10,
) -> bool:
    current = int(current or 0)
    previous = int(previous or 0)
    if previous <= 0:
        return False
    return current >= previous * float(ratio) and (current - previous) >= int(min_delta)


def list_open_quality_alerts(db: Session, limit: int = 20) -> List[dict]:
    from db.models import RiskAlert

    rows = (
        db.query(RiskAlert)
        .filter(
            RiskAlert.is_processed == False,  # noqa: E712
            RiskAlert.type == "data_abnormal",
            RiskAlert.match_name.like(f"{KEY_PREFIX}%"),
        )
        .order_by(RiskAlert.created_at.desc())
        .limit(max(1, min(int(limit), 50)))
        .all()
    )
    return [serialize_alert(r) for r in rows]


def _exists_dedup(db: Session, key: str, hours: int) -> bool:
    from db.models import RiskAlert

    cutoff = datetime.now() - timedelta(hours=max(1, int(hours)))
    q = db.query(RiskAlert).filter(
        RiskAlert.type == "data_abnormal",
        RiskAlert.match_name == key,
    )
    open_one = q.filter(RiskAlert.is_processed == False).first()  # noqa: E712
    if open_one:
        return True
    recent = q.filter(RiskAlert.created_at >= cutoff).first()
    return recent is not None


def _insert_alert(db: Session, item: dict):
    from db.models import RiskAlert

    alert = RiskAlert(
        match_id=None,
        match_name=item["match_name"],
        type="data_abnormal",
        level=item.get("level") or "mid",
        description=item.get("description") or "",
        recommended_action=item.get("recommended_action") or "",
        is_processed=False,
    )
    db.add(alert)
    return alert


def _check_miss_streak(db: Session, cfg: dict) -> List[dict]:
    from db.models import CrawlLog
    from services.real_team_crawler import get_priority_leagues

    streak = int(cfg.get("miss_streak") or 3)
    threshold = float(cfg.get("miss_rate_threshold") or 0.5)
    min_found = int(cfg.get("miss_min_found") or 5)
    items = []
    for lid in get_priority_leagues():
        logs = (
            db.query(CrawlLog)
            .filter(
                CrawlLog.crawl_category == "match_player",
                CrawlLog.league_id == lid,
            )
            .order_by(CrawlLog.id.desc())
            .limit(streak)
            .all()
        )
        rates = [miss_rate_from_log(log, min_found=min_found) for log in logs]
        if not miss_streak_triggered(rates, streak=streak, threshold=threshold):
            continue
        rate_txt = ", ".join(f"{r:.0%}" for r in rates if r is not None)
        items.append({
            "match_name": alert_key("stats_miss_streak", lid),
            "level": "high",
            "description": f"{lid} 连续 {streak} 次逐场统计 miss 率>{threshold:.0%}（{rate_txt}）",
            "recommended_action": "检查 ESPN 映射/队名别名，或在数据质量页确认别名后 backfill",
        })
    return items


def _check_stale_finished(db: Session, cfg: dict) -> List[dict]:
    from sqlalchemy import func
    from db.models import Match
    from services.real_team_crawler import get_priority_leagues

    now = datetime.now()
    stale_hours = int(cfg.get("stale_finished_hours") or 24)
    lookback_hours = int(cfg.get("fixture_lookback_hours") or 36)
    end = (now - timedelta(hours=stale_hours)).date()
    start = (now - timedelta(hours=lookback_hours)).date()
    if start > end:
        start = end

    items = []
    for lid in get_priority_leagues():
        due = int(
            db.query(func.count(Match.id))
            .filter(
                Match.league_id == lid,
                Match.match_date >= start,
                Match.match_date <= end,
            )
            .scalar()
            or 0
        )
        if due <= 0:
            continue
        finished_due = int(
            db.query(func.count(Match.id))
            .filter(
                Match.league_id == lid,
                Match.match_date >= start,
                Match.match_date <= end,
                Match.status == "finished",
            )
            .scalar()
            or 0
        )
        if finished_due > 0:
            continue
        items.append({
            "match_name": alert_key("stale_finished", lid),
            "level": "high",
            "description": (
                f"{lid} 近 {lookback_hours}h 有 {due} 场应完赛赛程，"
                f"但尚无完赛回写（窗口 {start}～{end}）"
            ),
            "recommended_action": "检查赛事采集 match_crawl / 源站是否可用，必要时手动跑赛程",
        })
    return items


def _latest_snapshot_before(db: Session, days: int = 6):
    from db.models import CrawlLog

    cutoff = datetime.now() - timedelta(days=max(1, int(days)))
    return (
        db.query(CrawlLog)
        .filter(
            CrawlLog.crawl_category == "quality",
            CrawlLog.league_name == SNAPSHOT_LEAGUE_NAME,
            CrawlLog.started_at <= cutoff,
        )
        .order_by(CrawlLog.id.desc())
        .first()
    )


def _snapshot_mapping_gap(log) -> Optional[int]:
    if log is None:
        return None
    raw = getattr(log, "crawled_data", None)
    if raw:
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(payload, dict) and payload.get("mapping_gap") is not None:
                return int(payload.get("mapping_gap") or 0)
        except Exception:
            pass
    if getattr(log, "found_count", None) is not None:
        return int(log.found_count or 0)
    return None


def _current_mapping_gap(db: Session) -> int:
    from services.data_quality_service import data_quality_service

    payload = data_quality_service.mapping_gaps_summary(db)
    summary = (payload or {}).get("summary") or {}
    return int(summary.get("mapping_gap") or 0)


def _check_mapping_wow(db: Session, cfg: dict, current: int) -> List[dict]:
    old = _latest_snapshot_before(db, days=6)
    previous = _snapshot_mapping_gap(old)
    if previous is None:
        return []
    ratio = float(cfg.get("mapping_gap_wow_ratio") or 1.2)
    min_delta = int(cfg.get("mapping_gap_min_delta") or 10)
    if not mapping_gap_wow_triggered(current, previous, ratio=ratio, min_delta=min_delta):
        return []
    return [{
        "match_name": alert_key("mapping_gap_wow"),
        "level": "mid",
        "description": (
            f"映射难场次一周内从 {previous} 升至 {current}"
            f"（≥{ratio:.0%} 且 +{min_delta}）"
        ),
        "recommended_action": "在数据质量页确认队名别名，或检查 ESPN 缩写是否失效",
    }]


def _save_snapshot(db: Session, *, crawl_type: str, mapping_gap: int, created: int, checks: dict):
    from db.models import CrawlLog

    now = datetime.now()
    log = CrawlLog(
        crawl_type=crawl_type or "scheduled",
        crawl_category="quality",
        league_id=None,
        league_name=SNAPSHOT_LEAGUE_NAME,
        found_count=int(mapping_gap),
        saved_count=int(created),
        updated_count=0,
        status="success",
        crawled_data=json.dumps(
            {
                "mapping_gap": int(mapping_gap),
                "alerts_created": int(created),
                "checks": checks,
            },
            ensure_ascii=False,
        ),
        started_at=now,
        finished_at=now,
        duration_ms=0,
    )
    db.add(log)


def evaluate_and_persist(db: Session, crawl_type: str = "scheduled", full: bool = True) -> dict:
    """跑质量检查。full=True 含映射缺口环比并写 quality 快照；逐场批次后可 full=False。"""
    start = datetime.now()
    cfg = quality_alert_cfg()
    enabled = alerts_enabled(cfg)
    dedup_hours = int(cfg.get("alert_dedup_hours") or 48)

    mapping_gap = 0
    if full:
        try:
            mapping_gap = _current_mapping_gap(db)
        except Exception as e:
            logger.warning("quality mapping_gap snapshot failed: %s", e)

    candidates = {
        "miss_streak": [],
        "stale_finished": [],
        "mapping_gap_wow": [],
    }
    try:
        candidates["miss_streak"] = _check_miss_streak(db, cfg)
    except Exception as e:
        logger.warning("quality miss_streak check failed: %s", e)
    try:
        candidates["stale_finished"] = _check_stale_finished(db, cfg)
    except Exception as e:
        logger.warning("quality stale_finished check failed: %s", e)
    if full:
        try:
            candidates["mapping_gap_wow"] = _check_mapping_wow(db, cfg, mapping_gap)
        except Exception as e:
            logger.warning("quality mapping_gap_wow check failed: %s", e)

    created_objs = []
    skipped = 0
    if enabled:
        for items in candidates.values():
            for item in items:
                if _exists_dedup(db, item["match_name"], dedup_hours):
                    skipped += 1
                    continue
                created_objs.append(_insert_alert(db, item))

    check_counts = {k: len(v) for k, v in candidates.items()}
    try:
        if full:
            _save_snapshot(
                db,
                crawl_type=crawl_type,
                mapping_gap=mapping_gap,
                created=len(created_objs),
                checks=check_counts,
            )
        db.commit()
        for alert in created_objs:
            try:
                db.refresh(alert)
            except Exception:
                pass
    except Exception as e:
        logger.error("quality alert persist failed: %s", e)
        db.rollback()
        return {
            "status": "failed",
            "error": str(e),
            "created": 0,
            "skipped": skipped,
            "mapping_gap": mapping_gap,
            "checks": check_counts,
            "alerts": [],
        }

    elapsed = int((datetime.now() - start).total_seconds() * 1000)
    return {
        "status": "success",
        "created": len(created_objs),
        "skipped": skipped,
        "mapping_gap": mapping_gap,
        "checks": check_counts,
        "alerts": [serialize_alert(a) for a in created_objs],
        "duration_ms": elapsed,
        "enabled": enabled,
        "full": full,
    }
