"""联赛API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from db.database import get_db
from services import LeagueService
from pydantic import BaseModel
from typing import Optional
from api.authz import RequireLeagueRead, RequireLeagueConfig

router = APIRouter()


class LeagueCreate(BaseModel):
    id: str
    name: str
    icon: Optional[str] = None
    logo: Optional[str] = None
    region: Optional[str] = None
    category: str = 'international'
    country: Optional[str] = None
    flag: Optional[str] = None
    level: int = 1
    parent_id: Optional[str] = None
    avg_goals: float = 2.70
    is_active: bool = True
    source_url: Optional[str] = None


class LeagueUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    logo: Optional[str] = None
    region: Optional[str] = None
    category: Optional[str] = None
    country: Optional[str] = None
    flag: Optional[str] = None
    level: Optional[int] = None
    parent_id: Optional[str] = None
    avg_goals: Optional[float] = None
    is_active: Optional[bool] = None
    source_url: Optional[str] = None


@router.get("/", dependencies=[RequireLeagueRead])
async def get_leagues(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=2000, description="每页数量"),
    category: str = Query(None, description="赛事类型: international/europe/america/asia/africa"),
    country: str = Query(None, description="国家名称"),
    region: str = Query(None, description="地区"),
    is_active: bool = Query(None, description="是否启用"),
    keyword: str = Query(None, description="关键词搜索"),
    has_data: bool = Query(None, description="仅返回已有球队或赛事的联赛"),
    hide_duplicates: bool = Query(True, description="隐藏已归并到规范联赛的 500.com 重复项"),
    level: int = Query(None, description="联赛级别 1/2/3"),
    parent_id: str = Query(None, description="上级联赛 ID"),
    roots_only: bool = Query(False, description="仅返回顶级联赛（无 parent_id）"),
    db: Session = Depends(get_db)
):
    kwargs = dict(
        category=category, country=country, region=region, is_active=is_active,
        keyword=keyword, has_data=has_data, hide_duplicates=hide_duplicates,
        level=level, parent_id=parent_id, roots_only=roots_only,
    )
    total = LeagueService.count(db, **kwargs)
    leagues = LeagueService.get_paginated(db, page=page, page_size=page_size, **kwargs)
    return {
        "leagues": leagues,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


@router.get("/active", dependencies=[RequireLeagueRead])
async def get_active_leagues(db: Session = Depends(get_db)):
    return {"leagues": LeagueService.get_active(db)}


@router.get("/categories", dependencies=[RequireLeagueRead])
async def get_league_categories(db: Session = Depends(get_db)):
    categories = LeagueService.get_categories(db)
    return {"categories": categories}


@router.get("/countries", dependencies=[RequireLeagueRead])
async def get_league_countries(
    category: str = Query(None, description="赛事类型"),
    db: Session = Depends(get_db)
):
    countries = LeagueService.get_countries(db, category=category)
    return {"countries": countries}


@router.get("/roots", dependencies=[RequireLeagueRead])
async def get_root_leagues(db: Session = Depends(get_db)):
    """所有顶级联赛，供表单选择上级联赛。"""
    return {"leagues": LeagueService.get_root_options(db)}


@router.post("/backfill-parents", dependencies=[RequireLeagueConfig])
async def backfill_league_parents_api(db: Session = Depends(get_db)):
    """批量推断并补齐联赛 parent_id（幂等）。"""
    from services.league_parent import backfill_league_parents
    updated = backfill_league_parents(db)
    return {"message": "回填完成", "updated": updated}


@router.get("/{league_id}/children", dependencies=[RequireLeagueRead])
async def get_league_children(
    league_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    leagues, total = LeagueService.get_children(db, league_id, page=page, page_size=page_size)
    if leagues is None:
        raise HTTPException(status_code=404, detail="League not found")
    return {
        "leagues": leagues,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if page_size else 0,
        "parent_id": league_id,
    }


@router.get("/{league_id}", dependencies=[RequireLeagueRead])
async def get_league(league_id: str, db: Session = Depends(get_db)):
    league = LeagueService.get_by_id(db, league_id)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    from db.models import League, Match, Team
    teams_count = db.query(Team).filter(Team.league_id == league_id).count()
    matches_count = db.query(Match).filter(Match.league_id == league_id).count()
    children_count = db.query(League).filter(League.parent_id == league_id).count()
    parent_name = None
    if league.parent_id:
        parent = LeagueService.get_by_id(db, league.parent_id)
        parent_name = parent.name if parent else None
    return LeagueService.to_dict(league, teams_count, matches_count, children_count, parent_name)


@router.post("/", dependencies=[RequireLeagueConfig])
async def create_league(data: LeagueCreate, db: Session = Depends(get_db)):
    return LeagueService.create(db, data.model_dump())


@router.put("/{league_id}", dependencies=[RequireLeagueConfig])
async def update_league(league_id: str, data: LeagueUpdate, db: Session = Depends(get_db)):
    league = LeagueService.update(db, league_id, data.model_dump(exclude_unset=True))
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return league


@router.put("/{league_id}/toggle", dependencies=[RequireLeagueConfig])
async def toggle_league_active(league_id: str, db: Session = Depends(get_db)):
    league = LeagueService.toggle_active(db, league_id)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return {"message": "League status updated", "league": league}


@router.delete("/{league_id}", dependencies=[RequireLeagueConfig])
async def delete_league(league_id: str, db: Session = Depends(get_db)):
    league = LeagueService.delete(db, league_id)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return {"message": "League deleted"}
