"""积分榜API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from services import StandingService
from pydantic import BaseModel
from datetime import date
from typing import Optional
from api.authz import RequireLeagueRead, RequireLeagueConfig

router = APIRouter()


class StandingCreate(BaseModel):
    league_id: str
    team_id: str
    season: str
    rank: int = 0
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_diff: int = 0
    points: int = 0
    update_date: Optional[date] = None


@router.get("/", dependencies=[RequireLeagueRead])
async def get_standings(db: Session = Depends(get_db)):
    return {"standings": StandingService.get_all(db)}


@router.get("/league/{league_id}", dependencies=[RequireLeagueRead])
async def get_standings_by_league(league_id: str, season: str = None, db: Session = Depends(get_db)):
    return {"standings": StandingService.get_by_league(db, league_id, season)}


@router.post("/", dependencies=[RequireLeagueConfig])
async def create_standing(data: StandingCreate, db: Session = Depends(get_db)):
    return StandingService.create(db, data.model_dump())


@router.put("/{standing_id}", dependencies=[RequireLeagueConfig])
async def update_standing(standing_id: int, data: StandingCreate, db: Session = Depends(get_db)):
    standing = StandingService.update(db, standing_id, data.model_dump())
    if not standing:
        raise HTTPException(status_code=404, detail="Standing not found")
    return standing


@router.delete("/{standing_id}", dependencies=[RequireLeagueConfig])
async def delete_standing(standing_id: int, db: Session = Depends(get_db)):
    standing = StandingService.delete(db, standing_id)
    if not standing:
        raise HTTPException(status_code=404, detail="Standing not found")
    return {"message": "Standing deleted"}
