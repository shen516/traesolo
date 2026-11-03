"""收藏API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import User
from services import FavoriteService
from api.deps import get_current_user, assert_self_or_permission, assert_self_only
from api.authz import RequireProfile

router = APIRouter()


@router.get("/user/{user_id}", dependencies=[RequireProfile])
async def get_user_favorites(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    assert_self_or_permission(current, user_id, "user:manage")
    favorites = FavoriteService.get_by_user(db, user_id)
    return {"favorites": favorites}


@router.get("/user/{user_id}/matches", dependencies=[RequireProfile])
async def get_user_match_favorites(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    assert_self_or_permission(current, user_id, "user:manage")
    favorites = FavoriteService.get_by_user_and_type(db, user_id, "match")
    return {"favorites": favorites}


@router.get("/user/{user_id}/teams", dependencies=[RequireProfile])
async def get_user_team_favorites(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    assert_self_or_permission(current, user_id, "user:manage")
    favorites = FavoriteService.get_by_user_and_type(db, user_id, "team")
    return {"favorites": favorites}


@router.post("/user/{user_id}/match/{match_id}", dependencies=[RequireProfile])
async def add_match_favorite(
    user_id: int,
    match_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    assert_self_only(current, user_id)
    favorite = FavoriteService.add_match_favorite(db, user_id, match_id)
    return {"message": "Match added to favorites", "favorite": favorite}


@router.post("/user/{user_id}/team/{team_id}", dependencies=[RequireProfile])
async def add_team_favorite(
    user_id: int,
    team_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    assert_self_only(current, user_id)
    favorite = FavoriteService.add_team_favorite(db, user_id, team_id)
    return {"message": "Team added to favorites", "favorite": favorite}


@router.delete("/user/{user_id}/match/{match_id}", dependencies=[RequireProfile])
async def remove_match_favorite(
    user_id: int,
    match_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    assert_self_only(current, user_id)
    favorite = FavoriteService.remove_match_favorite(db, user_id, match_id)
    if not favorite:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"message": "Match removed from favorites"}


@router.delete("/user/{user_id}/team/{team_id}", dependencies=[RequireProfile])
async def remove_team_favorite(
    user_id: int,
    team_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    assert_self_only(current, user_id)
    favorite = FavoriteService.remove_team_favorite(db, user_id, team_id)
    if not favorite:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"message": "Team removed from favorites"}
