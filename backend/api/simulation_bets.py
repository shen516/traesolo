"""模拟投注单 API（创建 / 列表 / 详情 / 统计 / 手动结算）。

仅供学习、研究、数据分析，不构成投注建议，不接入真实资金。
权限：读取/创建用 simulation:view（RequireSimulation），手动结算用 model:manage。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.authz import RequireModelManage, RequireSimulation
from api.deps import get_db
from db.models import User
from services import simulation_bet_service as sbs

# 注意：不要给 router 设自身 prefix。api/__init__.py 已用 include_router(..., prefix="/simulation")，
# FastAPI 0.139+ 的 _IncludedRouter 惰性匹配会把两者简单叠加；若此处再带 "/simulation/bets"
# 会拼成 /simulation/simulation/bets 导致 404。故把 "/bets" 前缀写在各装饰器路径上。
router = APIRouter(tags=["simulation bets"])


class BetCreate(BaseModel):
    match_id: str
    play_type: str = Field(..., pattern="^(spf|nspf|bf|tg|hspf)$")
    selection: str
    sp: float = Field(..., gt=0)
    sp_source: str = Field(..., pattern="^(snapshot|real|synthetic|manual)$")
    stake: float = Field(2.0, ge=2.0)
    multiple: int = Field(1, ge=1)


class ParlayLeg(BaseModel):
    """串关单腿：一场赛事 + 一个玩法选项。"""

    match_id: str
    play_type: str = Field(..., pattern="^(spf|nspf|bf|tg|hspf)$")
    selection: str
    sp: float = Field(..., gt=0)
    sp_source: str = Field(..., pattern="^(snapshot|real|synthetic|manual)$")


class ParlayCreate(BaseModel):
    """串关落单请求：2~8 腿，单注 2 元 × 倍数，组合整体结算。"""

    legs: list[ParlayLeg] = Field(..., min_length=2, max_length=8)
    stake: float = Field(2.0, ge=2.0)
    multiple: int = Field(1, ge=1)


@router.get("/bets")
def list_bets(
    db: Session = Depends(get_db),
    user: User = RequireSimulation,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    play_type: Optional[str] = Query(None),
    match_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="创建日期起（YYYY-MM-DD，含当天）"),
    date_to: Optional[str] = Query(None, description="创建日期止（YYYY-MM-DD，含当天）"),
):
    return sbs.list_bets(
        db, user,
        page=page, page_size=page_size,
        status=status, play_type=play_type, match_id=match_id,
        date_from=date_from, date_to=date_to,
    )


@router.post("/bets", status_code=201)
def create_bet(
    body: BetCreate,
    db: Session = Depends(get_db),
    _user: User = RequireModelManage,
):
    """创建模拟投注单（仅管理角色：model:manage）。普通用户只读。"""
    user = _user
    try:
        bet = sbs.create_bet(
            db, user,
            match_id=body.match_id,
            play_type=body.play_type,
            selection=body.selection,
            sp=body.sp,
            sp_source=body.sp_source,
            stake=body.stake,
            multiple=body.multiple,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return sbs.bet_to_dict(bet)


@router.post("/bets/parlay", status_code=201)
def create_parlay(
    body: ParlayCreate,
    db: Session = Depends(get_db),
    _user: User = RequireModelManage,
):
    """创建串关模拟投注单（仅管理角色：model:manage）。

    2~8 腿同一 combination_id，组合整体结算（任一腿未中 → 整组 lost；
    全部命中 → 2 × ∏sp × 倍数，封顶 PAYOUT_CAP_PARLAY）。
    """
    user = _user
    try:
        bets = sbs.create_parlay(
            db, user,
            legs=[
                {
                    "match_id": leg.match_id,
                    "play_type": leg.play_type,
                    "selection": leg.selection,
                    "sp": leg.sp,
                    "sp_source": leg.sp_source,
                }
                for leg in body.legs
            ],
            stake=body.stake,
            multiple=body.multiple,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "combination_id": bets[0].combination_id,
        "legs": [sbs.bet_to_dict(b) for b in bets],
    }


@router.get("/bets/stats")
def bet_stats(db: Session = Depends(get_db), user: User = RequireSimulation):
    return sbs.stats_for_user(db, user)


@router.post("/bets/settle-all", status_code=200)
def manual_settle(
    db: Session = Depends(get_db),
    _user: User = RequireModelManage,
):
    """管理端手动触发结算（与定时任务行为一致，幂等）。"""
    return sbs.settle_pending(db)


@router.get("/bets/{bet_id}")
def get_bet(
    bet_id: int,
    db: Session = Depends(get_db),
    user: User = RequireSimulation,
):
    bet = sbs.get_bet(db, user, bet_id)
    if not bet:
        raise HTTPException(status_code=404, detail="投注单不存在")
    return sbs.bet_to_dict(bet)


@router.post("/bets/{bet_id}/void", status_code=200)
def void_bet(
    bet_id: int,
    db: Session = Depends(get_db),
    _user: User = RequireModelManage,
):
    """开赛前整单作废（仅管理角色：model:manage；仅 pending 且赛事未开赛，作废后可重新提交）。"""
    user = _user
    try:
        bet = sbs.void_bet(db, user, bet_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not bet:
        raise HTTPException(status_code=404, detail="投注单不存在")
    return sbs.bet_to_dict(bet)
