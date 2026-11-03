"""关注联赛 API：列表 / 关注 / 取消 / 批量覆盖 / 首页聚合。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.authz import RequireProfile
from api.deps import get_current_entitlements, get_current_user, user_has_any_permission
from db.database import get_db
from db.models import User
from services.crud.follow import FollowService

router = APIRouter()


class ReplaceFollowsRequest(BaseModel):
    league_ids: Optional[List[str]] = None


@router.get("/leagues", dependencies=[RequireProfile])
async def list_followed_leagues(
    include_children: bool = Query(False, description="过滤 id 是否展开下级联赛"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return FollowService.serialize_state(db, current.id, include_children)


@router.get("/leagues/ids", dependencies=[RequireProfile])
async def list_followed_league_ids(
    include_children: bool = Query(False, description="过滤 id 是否展开下级联赛"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    state = FollowService.serialize_state(db, current.id, include_children)
    return {
        "ids": state["ids"],
        "filter_ids": state["filter_ids"],
        "child_map": state["child_map"],
        "include_children": state["include_children"],
    }


@router.get("/summary", dependencies=[RequireProfile])
async def followed_summary(
    match_limit: int = Query(8, ge=1, le=40),
    per_league_matches: int = Query(0, ge=0, le=10, description=">0 时按联赛各取 N 场未赛"),
    standings_limit: int = Query(8, ge=1, le=20),
    scorers_limit: int = Query(5, ge=1, le=15),
    include_children: bool = Query(False, description="未赛/风控是否含下级联赛"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    entitlements=Depends(get_current_entitlements),
):
    """关注联赛聚合：未赛、积分榜、射手榜、有权限时含风控。"""
    include_alerts = user_has_any_permission(current, "risk:manage")
    return FollowService.build_summary(
        db,
        current.id,
        entitlements=entitlements,
        match_limit=match_limit,
        per_league_matches=per_league_matches,
        standings_limit=standings_limit,
        scorers_limit=scorers_limit,
        include_alerts=include_alerts,
        include_children=include_children,
    )


@router.post("/leagues/{league_id}", dependencies=[RequireProfile])
async def follow_league(
    league_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    try:
        _, league = FollowService.follow(db, current.id, league_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "已关注", "league": league}


@router.delete("/leagues/{league_id}", dependencies=[RequireProfile])
async def unfollow_league(
    league_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    row = FollowService.unfollow(db, current.id, league_id)
    if not row:
        raise HTTPException(status_code=404, detail="未关注该联赛")
    return {"message": "已取消关注"}


@router.put("/leagues", dependencies=[RequireProfile])
async def replace_followed_leagues(
    body: ReplaceFollowsRequest,
    include_children: bool = Query(False),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    try:
        FollowService.replace(db, current.id, body.league_ids or [])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return FollowService.serialize_state(db, current.id, include_children)
