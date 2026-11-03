"""球队API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from services import TeamService
from pydantic import BaseModel
from typing import Optional
from api.authz import RequireLeagueRead, RequireMatchWrite

router = APIRouter()


class TeamCreate(BaseModel):
    id: str
    name: str
    short_name: str
    logo: Optional[str] = None
    league_id: Optional[str] = None
    country: Optional[str] = None
    elo_rating: int = 1500
    attack_strength: float = 1.0
    defense_strength: float = 1.0
    home_ground: Optional[str] = None
    founded_year: Optional[int] = None


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    logo: Optional[str] = None
    league_id: Optional[str] = None
    country: Optional[str] = None
    elo_rating: Optional[int] = None
    attack_strength: Optional[float] = None
    defense_strength: Optional[float] = None
    home_ground: Optional[str] = None
    founded_year: Optional[int] = None


@router.get("/", dependencies=[RequireLeagueRead])
async def get_teams(db: Session = Depends(get_db)):
    return {"teams": TeamService.get_all(db)}


@router.get("/{team_id}", dependencies=[RequireLeagueRead])
async def get_team(team_id: str, db: Session = Depends(get_db)):
    team = TeamService.get_by_id(db, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


@router.get("/league/{league_id}", dependencies=[RequireLeagueRead])
async def get_teams_by_league(league_id: str, db: Session = Depends(get_db)):
    return {"teams": TeamService.get_by_league(db, league_id)}


@router.get("/search/{keyword}", dependencies=[RequireLeagueRead])
async def search_teams(keyword: str, db: Session = Depends(get_db)):
    return {"teams": TeamService.search(db, keyword)}


@router.post("/", dependencies=[RequireMatchWrite])
async def create_team(data: TeamCreate, db: Session = Depends(get_db)):
    return TeamService.create(db, data.model_dump())


@router.put("/{team_id}", dependencies=[RequireMatchWrite])
async def update_team(team_id: str, data: TeamUpdate, db: Session = Depends(get_db)):
    team = TeamService.update(db, team_id, data.model_dump(exclude_unset=True))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


@router.put("/{team_id}/elo", dependencies=[RequireMatchWrite])
async def update_team_elo(team_id: str, elo_rating: int, db: Session = Depends(get_db)):
    team = TeamService.update_elo(db, team_id, elo_rating)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return {"message": "ELO updated", "elo_rating": team.elo_rating}


@router.put("/{team_id}/strength", dependencies=[RequireMatchWrite])
async def update_team_strength(team_id: str, attack: float, defense: float, db: Session = Depends(get_db)):
    team = TeamService.update_strength(db, team_id, attack, defense)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return {"message": "Strength updated", "attack": team.attack_strength, "defense": team.defense_strength}
