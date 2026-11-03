"""订阅API：套餐列表、我的订阅、管理员开通/取消、流水查询"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from db.database import get_db
from db.models import User
from services import subscription_service as sub_svc
from api.deps import get_current_user, get_entitlements, assert_self_or_permission
from api.authz import RequireUserManage

router = APIRouter()


class GrantRequest(BaseModel):
    user_id: int
    plan_code: str
    note: Optional[str] = None


class CancelRequest(BaseModel):
    user_id: int
    note: Optional[str] = None


def _plan_to_dict(plan) -> dict:
    features = sub_svc._parse_features(plan.features_json)
    return {
        "code": plan.code,
        "name": plan.name,
        "tier": plan.tier,
        "duration_days": plan.duration_days,
        "price": float(plan.price) if plan.price is not None else 0,
        "features": features,
        "feature_labels": {c: sub_svc.FEATURE_LABELS.get(c, c) for c in features},
        "description": plan.description,
        "is_active": bool(plan.is_active),
        "sort_order": plan.sort_order,
    }


@router.get("/plans")
async def list_plans(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """套餐列表（登录即可见，供升级页/开通弹窗展示）"""
    plans = sub_svc.list_plans(db, only_active=True)
    return {"plans": [_plan_to_dict(p) for p in plans]}


@router.get("/my")
async def my_subscription(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """当前用户订阅快照：套餐、到期日、剩余天数、权益码"""
    return sub_svc.get_user_subscription(db, current)


@router.post("/grant", dependencies=[RequireUserManage])
async def grant_subscription(
    req: GrantRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """管理员开通/续费/变更套餐。同档续费自动叠加时长。"""
    try:
        record = sub_svc.grant(
            db, req.user_id, req.plan_code, operator_id=current.id, note=req.note
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    user = db.query(User).filter(User.id == req.user_id).first()
    return {
        "message": "订阅已开通",
        "record": sub_svc.record_to_dict(record),
        "subscription": sub_svc.get_user_subscription(db, user),
    }


@router.post("/cancel", dependencies=[RequireUserManage])
async def cancel_subscription(
    req: CancelRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """管理员取消订阅（权益立即回落免费版）。"""
    try:
        sub_svc.cancel(db, req.user_id, operator_id=current.id, note=req.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "订阅已取消"}


@router.get("/records")
async def list_records(
    user_id: int = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """订阅流水：管理员可查全部，普通用户仅查本人。"""
    from api.deps import user_has_any_permission
    if user_id is not None and user_id != current.id:
        assert_self_or_permission(current, user_id, "user:manage")
    elif user_id is None and not user_has_any_permission(current, "user:manage"):
        user_id = current.id
    total, rows = sub_svc.list_records(db, user_id=user_id, page=page, page_size=page_size)
    return {
        "records": [sub_svc.record_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/expire-check", dependencies=[RequireUserManage])
async def run_expire_check(db: Session = Depends(get_db)):
    """手动触发一次到期批量检查（定时任务之外的即时入口）。"""
    return sub_svc.expire_overdue(db)
