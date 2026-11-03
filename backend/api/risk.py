"""风控API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import User
from services import RiskService
from services.crud.follow import FollowService
from services.subscription_service import mask_risk_alerts
from pydantic import BaseModel
from typing import Optional, Set
from api.authz import RequireRiskManage
from api.deps import get_current_entitlements, get_current_user

router = APIRouter(dependencies=[RequireRiskManage])


def _parse_league_ids(raw: Optional[str]):
    if raw is None:
        return None
    return [part.strip() for part in raw.split(",") if part.strip()]


def _resolve_risk_league_ids(
    db: Session,
    current: User,
    league_ids: Optional[str],
    followed_only: bool,
    include_children: bool = False,
):
    parsed = _parse_league_ids(league_ids)
    if followed_only:
        followed = FollowService.get_filter_ids(db, current.id, include_children)
        if parsed is None:
            return followed
        allowed = set(followed)
        return [lid for lid in parsed if lid in allowed]
    return parsed


def _is_admin_user(user: User) -> bool:
    roles = {r.get("code") for r in (getattr(user, "_session_roles", []) or []) if isinstance(r, dict)}
    return "super_admin" in roles or "admin" in roles


def _list_alerts(
    db, current, entitlements, league_ids=None, followed_only=False,
    include_children=False, level=None, unprocessed_only=False,
):
    ids = _resolve_risk_league_ids(db, current, league_ids, followed_only, include_children)
    if followed_only and not _is_admin_user(current) and not ids:
        return []
    rows = RiskService.list_filtered(
        db, league_ids=ids, level=level, unprocessed_only=unprocessed_only
    )
    return mask_risk_alerts(RiskService.serialize(db, rows), entitlements)


class RiskCreate(BaseModel):
    match_id: Optional[str] = None
    match_name: Optional[str] = None
    type: str
    level: str
    description: Optional[str] = None
    recommended_action: Optional[str] = None


class RiskProcessUpdate(BaseModel):
    is_processed: bool = True


@router.get("/")
async def get_risk_alerts(
    league_ids: str = Query(None, description="逗号分隔联赛ID"),
    followed_only: bool = Query(False, description="仅当前用户关注的联赛"),
    include_children: bool = Query(False, description="关注过滤时展开下级联赛"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    return {
        "alerts": _list_alerts(
            db, current, entitlements,
            league_ids=league_ids, followed_only=followed_only, include_children=include_children,
        )
    }


@router.get("/match/{match_id}")
async def get_risk_alerts_by_match(
    match_id: str,
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    return {"alerts": mask_risk_alerts(jsonable_encoder(RiskService.get_by_match(db, match_id)), entitlements)}


@router.get("/level/{level}")
async def get_risk_alerts_by_level(
    level: str,
    league_ids: str = Query(None),
    followed_only: bool = Query(False),
    include_children: bool = Query(False),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    return {
        "alerts": _list_alerts(
            db, current, entitlements,
            league_ids=league_ids, followed_only=followed_only,
            include_children=include_children, level=level,
        )
    }


@router.get("/unprocessed")
async def get_unprocessed_alerts(
    league_ids: str = Query(None),
    followed_only: bool = Query(False),
    include_children: bool = Query(False),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    return {
        "alerts": _list_alerts(
            db, current, entitlements,
            league_ids=league_ids, followed_only=followed_only,
            include_children=include_children, unprocessed_only=True,
        )
    }


@router.post("/")
async def create_risk_alert(data: RiskCreate, db: Session = Depends(get_db)):
    return RiskService.create(db, data.model_dump())


@router.put("/{alert_id}/process")
async def mark_alert_processed(
    alert_id: int,
    data: RiskProcessUpdate,
    db: Session = Depends(get_db),
):
    alert = RiskService.set_processed(db, alert_id, data.is_processed)
    if not alert:
        raise HTTPException(status_code=404, detail="预警记录不存在")
    return {
        "id": alert.id,
        "is_processed": alert.is_processed,
        "message": "已处理" if alert.is_processed else "未处理",
    }


@router.delete("/{alert_id}")
async def delete_risk_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = RiskService.delete(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": "Alert deleted"}
