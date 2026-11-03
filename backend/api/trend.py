"""准确率趋势API

读接口（三个 GET）要求 RequireModelRead = model:manage **或** dashboard:view；
写/删接口要求 RequireModelManage = model:manage。

注意：router 级不能挂 APIRouter(dependencies=[...])。FastAPI 中函数级
dependencies 会与 router 级叠加（两者都需满足），那样读接口会变成"必须
model:manage"，把持有 dashboard:view 的普通用户挡在准确率趋势之外。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from services import TrendService
from pydantic import BaseModel
from datetime import date
from typing import Optional
from api.authz import RequireModelRead, RequireModelManage

router = APIRouter()


class TrendCreate(BaseModel):
    model_version: str
    date: date
    accuracy: Optional[float] = None
    total_matches: int = 0
    correct_matches: int = 0


@router.get("/", dependencies=[RequireModelRead])
async def get_trends(db: Session = Depends(get_db)):
    return {"trends": TrendService.get_all(db)}


@router.get("/version/{version}", dependencies=[RequireModelRead])
async def get_trends_by_version(version: str, db: Session = Depends(get_db)):
    return {"trends": TrendService.get_by_version(db, version)}


@router.get("/recent/{days}", dependencies=[RequireModelRead])
async def get_recent_trends(days: int = 30, db: Session = Depends(get_db)):
    return {"trends": TrendService.get_recent(db, days)}


@router.post("/", dependencies=[RequireModelManage])
async def create_trend(data: TrendCreate, db: Session = Depends(get_db)):
    return TrendService.create(db, data.model_dump())


@router.delete("/{trend_id}", dependencies=[RequireModelManage])
async def delete_trend(trend_id: int, db: Session = Depends(get_db)):
    trend = TrendService.delete(db, trend_id)
    if not trend:
        raise HTTPException(status_code=404, detail="Trend not found")
    return {"message": "Trend deleted"}
