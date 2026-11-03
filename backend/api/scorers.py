"""射手榜API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from services import ScorerService
from pydantic import BaseModel
from datetime import date
from typing import Optional
from api.authz import RequireLeagueRead, RequireLeagueConfig

router = APIRouter()


class ScorerCreate(BaseModel):
    player_name: str
    team_id: Optional[str] = None
    league_id: str
    season: str
    goals: int = 0
    assists: int = 0
    games_played: int = 0
    rank: int = 0
    update_date: Optional[date] = None


@router.get("/", dependencies=[RequireLeagueRead])
async def get_top_scorers(db: Session = Depends(get_db)):
    return {"scorers": ScorerService.get_all(db)}


@router.get("/league/{league_id}", dependencies=[RequireLeagueRead])
async def get_scorers_by_league(league_id: str, season: str = None, db: Session = Depends(get_db)):
    return {"scorers": ScorerService.get_by_league(db, league_id, season)}


@router.post("/", dependencies=[RequireLeagueConfig])
async def create_scorer(data: ScorerCreate, db: Session = Depends(get_db)):
    return ScorerService.create(db, data.model_dump())


@router.put("/{scorer_id}", dependencies=[RequireLeagueConfig])
async def update_scorer(scorer_id: int, data: ScorerCreate, db: Session = Depends(get_db)):
    scorer = ScorerService.update(db, scorer_id, data.model_dump())
    if not scorer:
        raise HTTPException(status_code=404, detail="Scorer not found")
    return scorer


@router.delete("/{scorer_id}", dependencies=[RequireLeagueConfig])
async def delete_scorer(scorer_id: int, db: Session = Depends(get_db)):
    scorer = ScorerService.delete(db, scorer_id)
    if not scorer:
        raise HTTPException(status_code=404, detail="Scorer not found")
    return {"message": "Scorer deleted"}
