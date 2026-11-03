"""可维护的队名别名：确认后参与 ESPN/500 映射，避免只改 Python 常量。"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_CACHE_TTL = 45
_lock = threading.Lock()
_cache_expires = 0.0
_by_alias: Dict[str, dict] = {}
_espn_by_team: Dict[str, List[str]] = {}


def normalize_alias(value: str) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[\s\-\.·]+", " ", text).strip()


def compact_alias(value: str) -> str:
    return re.sub(r"[\s\-\.·]", "", normalize_alias(value) or "")


def invalidate_alias_cache() -> None:
    global _cache_expires
    with _lock:
        _cache_expires = 0.0


def _row_dict(row) -> dict:
    return {
        "id": row.id,
        "alias": row.alias,
        "team_id": row.team_id,
        "league_id": row.league_id,
        "espn_abbr": row.espn_abbr,
        "status": row.status,
        "source": row.source,
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _reload_unlocked() -> None:
    global _cache_expires, _by_alias, _espn_by_team
    from db.database import SessionLocal
    from db.models import TeamAlias

    by_alias: Dict[str, dict] = {}
    espn_by_team: Dict[str, List[str]] = {}
    db = SessionLocal()
    try:
        rows = (
            db.query(TeamAlias)
            .filter(TeamAlias.status == "confirmed")
            .all()
        )
        for row in rows:
            payload = {
                "team_id": row.team_id,
                "espn_abbr": (row.espn_abbr or "").strip() or None,
            }
            keys = {normalize_alias(row.alias), compact_alias(row.alias)}
            for key in keys:
                if key:
                    by_alias[key] = payload
            abbr = payload["espn_abbr"]
            if abbr:
                espn_by_team.setdefault(row.team_id, [])
                if abbr.upper() not in espn_by_team[row.team_id]:
                    espn_by_team[row.team_id].append(abbr.upper())
    except Exception as e:
        logger.debug("Reload team alias cache skipped: %s", e)
        return
    finally:
        db.close()
    _by_alias = by_alias
    _espn_by_team = espn_by_team
    _cache_expires = time.time() + _CACHE_TTL


def _ensure_cache() -> None:
    with _lock:
        if time.time() >= _cache_expires:
            _reload_unlocked()


def lookup_confirmed_team_id(name: str) -> Optional[str]:
    """已确认别名 → 本库球队 ID。"""
    if not name:
        return None
    _ensure_cache()
    for key in (normalize_alias(name), compact_alias(name), str(name).strip().lower()):
        hit = _by_alias.get(key)
        if hit and hit.get("team_id"):
            return hit["team_id"]
    return None


def lookup_espn_abbrs(team_id: str) -> List[str]:
    if not team_id:
        return []
    _ensure_cache()
    return list(_espn_by_team.get(team_id) or [])


def alias_is_known(name: str) -> bool:
    return bool(lookup_confirmed_team_id(name))


class TeamAliasService:
    @staticmethod
    def list(
        db: Session,
        *,
        status: str = None,
        team_id: str = None,
        q: str = None,
        limit: int = 100,
    ) -> List[dict]:
        from db.models import TeamAlias

        query = db.query(TeamAlias)
        if status:
            query = query.filter(TeamAlias.status == status)
        if team_id:
            query = query.filter(TeamAlias.team_id == team_id)
        if q:
            like = f"%{q.strip()}%"
            query = query.filter(TeamAlias.alias.like(like))
        rows = query.order_by(TeamAlias.updated_at.desc(), TeamAlias.id.desc()).limit(max(1, min(limit, 300))).all()
        return [_row_dict(r) for r in rows]

    @staticmethod
    def create(db: Session, data: dict) -> dict:
        from db.models import Team, TeamAlias
        from fastapi import HTTPException

        alias = normalize_alias(data.get("alias") or "")
        if not alias:
            raise HTTPException(status_code=400, detail="别名不能为空")
        team_id = str(data.get("team_id") or "").strip()
        if not team_id:
            raise HTTPException(status_code=400, detail="球队 ID 不能为空")
        if not db.query(Team).filter(Team.id == team_id).first():
            raise HTTPException(status_code=400, detail=f"球队 {team_id} 不存在")
        status = (data.get("status") or "confirmed").strip()
        if status not in ("pending", "confirmed", "rejected"):
            raise HTTPException(status_code=400, detail="状态无效")
        existing = db.query(TeamAlias).filter(TeamAlias.alias == alias).first()
        payload = {
            "alias": alias,
            "team_id": team_id,
            "league_id": data.get("league_id") or None,
            "espn_abbr": (data.get("espn_abbr") or "").strip().upper() or None,
            "status": status,
            "source": data.get("source") or "manual",
            "note": (data.get("note") or "")[:255] or None,
        }
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            db.commit()
            db.refresh(existing)
            invalidate_alias_cache()
            return _row_dict(existing)
        row = TeamAlias(**payload)
        db.add(row)
        db.commit()
        db.refresh(row)
        invalidate_alias_cache()
        return _row_dict(row)

    @staticmethod
    def update(db: Session, alias_id: int, data: dict) -> dict:
        from db.models import Team, TeamAlias
        from fastapi import HTTPException

        row = db.query(TeamAlias).filter(TeamAlias.id == alias_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="别名不存在")
        if "alias" in data and data["alias"] is not None:
            alias = normalize_alias(data["alias"])
            if not alias:
                raise HTTPException(status_code=400, detail="别名不能为空")
            row.alias = alias
        if data.get("team_id"):
            team_id = str(data["team_id"]).strip()
            if not db.query(Team).filter(Team.id == team_id).first():
                raise HTTPException(status_code=400, detail=f"球队 {team_id} 不存在")
            row.team_id = team_id
        if "league_id" in data:
            row.league_id = data.get("league_id") or None
        if "espn_abbr" in data:
            row.espn_abbr = (data.get("espn_abbr") or "").strip().upper() or None
        if data.get("status"):
            if data["status"] not in ("pending", "confirmed", "rejected"):
                raise HTTPException(status_code=400, detail="状态无效")
            row.status = data["status"]
        if "note" in data:
            row.note = (data.get("note") or "")[:255] or None
        db.commit()
        db.refresh(row)
        invalidate_alias_cache()
        return _row_dict(row)

    @staticmethod
    def delete(db: Session, alias_id: int) -> None:
        from db.models import TeamAlias
        from fastapi import HTTPException

        row = db.query(TeamAlias).filter(TeamAlias.id == alias_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="别名不存在")
        db.delete(row)
        db.commit()
        invalidate_alias_cache()

    @staticmethod
    def suggest_from_weak_teams(db: Session, weak_teams: List[dict]) -> dict:
        """把映射缺口中的难映射队写成 pending，已有别名则跳过。"""
        from db.models import Team, TeamAlias

        created = 0
        skipped = 0
        for item in weak_teams or []:
            team_id = str(item.get("team_id") or "").strip()
            if not team_id or not db.query(Team).filter(Team.id == team_id).first():
                skipped += 1
                continue
            candidates = [
                item.get("name"),
                item.get("short_name"),
                team_id,
            ]
            wrote = False
            for raw in candidates:
                alias = normalize_alias(raw or "")
                if not alias or alias == team_id.lower():
                    continue
                exists = db.query(TeamAlias).filter(TeamAlias.alias == alias).first()
                if exists:
                    skipped += 1
                    continue
                db.add(TeamAlias(
                    alias=alias,
                    team_id=team_id,
                    league_id=item.get("league_id") or None,
                    status="pending",
                    source="mapping_gap",
                    note=f"map_score={item.get('map_score')}",
                ))
                created += 1
                wrote = True
            if not wrote:
                skipped += 1
        db.commit()
        invalidate_alias_cache()
        return {"created": created, "skipped": skipped}
