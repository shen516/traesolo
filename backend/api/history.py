"""历史记录API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import User
from services import HistoryService
from pydantic import BaseModel
from typing import Optional
from api.deps import get_current_user, assert_self_or_permission, assert_self_only
from api.authz import RequireProfile

router = APIRouter()


class HistoryCreate(BaseModel):
    user_id: int
    match_id: str
    match_name: Optional[str] = None
    prediction: Optional[str] = None
    actual: Optional[str] = None
    result: Optional[str] = None


@router.get("/user/{user_id}", dependencies=[RequireProfile])
async def get_user_history(
    user_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    assert_self_or_permission(current, user_id, "user:manage")
    history = HistoryService.get_by_user(db, user_id, limit)
    return {"history": history}


@router.get("/user/{user_id}/accuracy", dependencies=[RequireProfile])
async def get_user_accuracy(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    assert_self_or_permission(current, user_id, "user:manage")
    accuracy = HistoryService.get_user_accuracy(db, user_id)
    return {"user_id": user_id, "accuracy_rate": accuracy}


@router.post("/", dependencies=[RequireProfile])
async def create_history(
    data: HistoryCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    assert_self_only(current, data.user_id)
    return HistoryService.create(db, data.model_dump())


@router.delete("/{history_id}", dependencies=[RequireProfile])
async def delete_history(
    history_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    from db.models import UserHistory
    row = db.query(UserHistory).filter(UserHistory.id == history_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="History not found")
    assert_self_or_permission(current, row.user_id, "user:manage")
    history = HistoryService.delete(db, history_id)
    return {"message": "History deleted"}
