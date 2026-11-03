"""球员API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from db.database import get_db
from services import PlayerService
from pydantic import BaseModel
from datetime import date
from typing import Optional
from api.authz import RequireLeagueRead, RequireMatchWrite

router = APIRouter()


class PlayerCreate(BaseModel):
    id: str
    name: str
    short_name: Optional[str] = None
    jersey_number: Optional[int] = None
    position: Optional[str] = None
    team_id: Optional[str] = None
    nationality: Optional[str] = None
    birth_date: Optional[date] = None
    height: Optional[int] = None
    weight: Optional[int] = None
    foot: Optional[str] = None
    market_value: Optional[float] = None
    goals: int = 0
    assists: int = 0
    appearances: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    photo: Optional[str] = None


class PlayerUpdate(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    jersey_number: Optional[int] = None
    position: Optional[str] = None
    team_id: Optional[str] = None
    nationality: Optional[str] = None
    birth_date: Optional[date] = None
    height: Optional[int] = None
    weight: Optional[int] = None
    foot: Optional[str] = None
    market_value: Optional[float] = None
    goals: Optional[int] = None
    assists: Optional[int] = None
    appearances: Optional[int] = None
    yellow_cards: Optional[int] = None
    red_cards: Optional[int] = None
    photo: Optional[str] = None


@router.get("/", dependencies=[RequireLeagueRead])
async def get_players(
    team_id: str = Query(None, description="球队ID"),
    league_id: str = Query(None, description="联赛ID"),
    position: str = Query(None, description="位置: GK/CB/RB/LB/DM/CM/AM/RM/LM/RW/LW/ST"),
    keyword: str = Query(None, description="搜索关键词"),
    db: Session = Depends(get_db)
):
    if team_id:
        return {"players": PlayerService.get_by_team(db, team_id)}
    elif league_id:
        return {"players": PlayerService.get_by_league(db, league_id)}
    elif position:
        return {"players": PlayerService.get_by_position(db, position)}
    elif keyword:
        return {"players": PlayerService.search(db, keyword)}
    else:
        return {"players": PlayerService.get_all(db)}


@router.get("/{player_id}", dependencies=[RequireLeagueRead])
async def get_player(player_id: str, db: Session = Depends(get_db)):
    player = PlayerService.get_by_id(db, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


@router.get("/top-scorers", dependencies=[RequireLeagueRead])
async def get_top_scorers(
    team_id: str = Query(None, description="球队ID"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    return {"players": PlayerService.get_top_scorers(db, team_id, limit)}


@router.post("/", dependencies=[RequireMatchWrite])
async def create_player(data: PlayerCreate, db: Session = Depends(get_db)):
    return PlayerService.create(db, data.model_dump())


@router.put("/{player_id}", dependencies=[RequireMatchWrite])
async def update_player(player_id: str, data: PlayerUpdate, db: Session = Depends(get_db)):
    player = PlayerService.update(db, player_id, data.model_dump(exclude_unset=True))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


@router.delete("/{player_id}", dependencies=[RequireMatchWrite])
async def delete_player(player_id: str, db: Session = Depends(get_db)):
    player = PlayerService.delete(db, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return {"message": "Player deleted"}