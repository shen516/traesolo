"""赔率快照：采集覆盖写 matches.odds_* 前保留时序（仅分析/展示，非投注建议）。

比分 SP 一并写入 odds_bf_json。matches.odds_bf_json 会被赛果回写覆盖成收盘价，
因此赛前比分只认 captured_at 不晚于开赛的最后一帧。没有这一帧时，后续融合权重为 0。
本模块只积累和读取，不参与比分 Top3。
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any, Dict, Optional, Sequence

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_ODDS_KEYS = (
    "handicap",
    "odds_nspf_win",
    "odds_nspf_draw",
    "odds_nspf_lose",
    "odds_spf_win",
    "odds_spf_draw",
    "odds_spf_lose",
)


def _to_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def odds_tuple_from_obj(obj) -> tuple:
    return tuple(_to_float(getattr(obj, k, None) if not isinstance(obj, dict) else obj.get(k)) for k in _ODDS_KEYS)


def has_any_odds(values: tuple) -> bool:
    return any(v is not None for v in values)


def normalize_bf_json(value: Any) -> Optional[str]:
    """比分 SP → 稳定 JSON。空、非正数、无法解析都视为没有。"""
    if value is None or value == "" or value == "{}":
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return None
    if not isinstance(value, dict) or not value:
        return None
    cleaned: Dict[str, float] = {}
    for key, raw in value.items():
        num = _to_float(raw)
        if num is None or num <= 0:
            continue
        cleaned[str(key)] = num
    if not cleaned:
        return None
    return json.dumps(cleaned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _obj_get(obj, key):
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _kickoff(match) -> Optional[datetime]:
    match_date = _obj_get(match, "match_date")
    if isinstance(match_date, datetime):
        match_date = match_date.date()
    if not isinstance(match_date, date):
        return None
    match_time = _obj_get(match, "match_time")
    if isinstance(match_time, timedelta):
        match_time = (datetime.min + match_time).time()
    if not isinstance(match_time, dt_time):
        match_time = dt_time(23, 59, 59)
    return datetime.combine(match_date, match_time)


def _before_kickoff(match, now: Optional[datetime] = None) -> bool:
    kickoff = _kickoff(match)
    if kickoff is None:
        return False
    return (now or datetime.now()) <= kickoff


def _has_bf_snapshot(db: Session, match_id: str) -> bool:
    """已有非空比分快照则不再补第一帧。查询失败时视为已有，避免每轮采集重复写入。"""
    from db.models import OddsSnapshot

    try:
        row = (
            db.query(OddsSnapshot.id)
            .filter(
                OddsSnapshot.match_id == match_id,
                OddsSnapshot.odds_bf_json.isnot(None),
                OddsSnapshot.odds_bf_json != "",
                OddsSnapshot.odds_bf_json != "{}",
            )
            .limit(1)
            .first()
        )
        return row is not None
    except Exception as e:
        logger.debug("bf snapshot lookup skipped for %s: %s", match_id, e)
        return True


def _write_snapshot(db: Session, match, new_data: dict, bf_text: Optional[str], source: str) -> bool:
    from db.models import OddsSnapshot

    def field(key):
        if isinstance(new_data, dict) and new_data.get(key) is not None:
            return new_data.get(key)
        return getattr(match, key, None)

    snap = OddsSnapshot(
        match_id=match.id,
        fixture_id=getattr(match, "fixture_id", None) or (new_data.get("fixture_id") if isinstance(new_data, dict) else None),
        source=(source or "500_trade")[:20],
        captured_at=datetime.now(),
        handicap=field("handicap"),
        odds_nspf_win=field("odds_nspf_win"),
        odds_nspf_draw=field("odds_nspf_draw"),
        odds_nspf_lose=field("odds_nspf_lose"),
        odds_spf_win=field("odds_spf_win"),
        odds_spf_draw=field("odds_spf_draw"),
        odds_spf_lose=field("odds_spf_lose"),
        odds_bf_json=bf_text,
    )
    db.add(snap)
    return True


def maybe_snapshot_odds(
    db: Session,
    match,
    new_data: dict,
    *,
    source: str = "500_trade",
    now: Optional[datetime] = None,
) -> bool:
    """胜平负、让球或比分 SP 相对当前行有变化时写一帧。

    开赛前若已有比分 SP、但还没有任何比分快照，补一帧作为赛前起点。
    开赛后不补这一帧，避免把收盘比分 SP 记成赛前价。
    """
    new_vals = odds_tuple_from_obj(new_data)
    new_bf = normalize_bf_json(_obj_get(new_data, "odds_bf_json"))
    if not has_any_odds(new_vals) and new_bf is None:
        return False
    old_vals = odds_tuple_from_obj(match)
    old_bf = normalize_bf_json(getattr(match, "odds_bf_json", None))
    odds_changed = has_any_odds(new_vals) and old_vals != new_vals
    bf_changed = new_bf is not None and new_bf != old_bf
    if not odds_changed and not bf_changed:
        if new_bf is None or not _before_kickoff(match, now) or _has_bf_snapshot(db, getattr(match, "id", None)):
            return False
    stored_bf = new_bf if new_bf is not None else old_bf
    try:
        return _write_snapshot(db, match, new_data, stored_bf, source)
    except Exception as e:
        logger.debug("odds snapshot skipped for %s: %s", getattr(match, "id", None), e)
        return False


def pick_pre_match_bf(rows: Sequence[Any], kickoffs: Dict[str, datetime]) -> Dict[str, str]:
    """按 captured_at 升序的快照里，保留每场开赛前最后一帧非空比分 SP。"""
    out: Dict[str, str] = {}
    for row in rows:
        match_id = _obj_get(row, "match_id")
        captured_at = _obj_get(row, "captured_at")
        kickoff = kickoffs.get(match_id)
        if kickoff is None or captured_at is None or captured_at > kickoff:
            continue
        text = normalize_bf_json(_obj_get(row, "odds_bf_json"))
        if text is None:
            continue
        out[match_id] = text
    return out


def load_pre_match_bf(db: Session, kickoffs: Dict[str, datetime]) -> Dict[str, str]:
    """每场取开赛前最后一帧比分 SP。没有这一帧的场次不在结果里，融合权重按 0。

    只读取，不参与比分 Top3。
    """
    from db.models import OddsSnapshot

    out: Dict[str, str] = {}
    ids = list(kickoffs)
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        if not chunk:
            continue
        rows = (
            db.query(OddsSnapshot.match_id, OddsSnapshot.captured_at, OddsSnapshot.odds_bf_json)
            .filter(OddsSnapshot.match_id.in_(chunk), OddsSnapshot.captured_at.isnot(None))
            .order_by(OddsSnapshot.captured_at.asc())
            .all()
        )
        out.update(pick_pre_match_bf(rows, kickoffs))
    return out


def list_snapshots(db: Session, match_id: str, limit: int = 50) -> list:
    from db.models import OddsSnapshot

    rows = (
        db.query(OddsSnapshot)
        .filter(OddsSnapshot.match_id == match_id)
        .order_by(OddsSnapshot.captured_at.desc())
        .limit(max(1, min(int(limit), 200)))
        .all()
    )
    out = []
    for r in rows:
        bf_text = normalize_bf_json(r.odds_bf_json)
        out.append({
            "id": r.id,
            "match_id": r.match_id,
            "fixture_id": r.fixture_id,
            "source": r.source,
            "captured_at": r.captured_at.isoformat() if r.captured_at else None,
            "handicap": int(r.handicap) if r.handicap is not None else None,
            "odds_nspf_win": float(r.odds_nspf_win) if r.odds_nspf_win is not None else None,
            "odds_nspf_draw": float(r.odds_nspf_draw) if r.odds_nspf_draw is not None else None,
            "odds_nspf_lose": float(r.odds_nspf_lose) if r.odds_nspf_lose is not None else None,
            "odds_spf_win": float(r.odds_spf_win) if r.odds_spf_win is not None else None,
            "odds_spf_draw": float(r.odds_spf_draw) if r.odds_spf_draw is not None else None,
            "odds_spf_lose": float(r.odds_spf_lose) if r.odds_spf_lose is not None else None,
            "odds_bf": json.loads(bf_text) if bf_text else None,
        })
    return out
