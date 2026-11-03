from services.crud._common import *

class FavoriteService:
    @staticmethod
    def get_by_user(db: Session, user_id: int):
        return db.query(UserFavorite).filter(UserFavorite.user_id == user_id).all()

    @staticmethod
    def get_by_user_and_type(db: Session, user_id: int, fav_type: str):
        return db.query(UserFavorite).filter(
            and_(UserFavorite.user_id == user_id, UserFavorite.type == fav_type)
        ).all()

    @staticmethod
    def get_by_user_and_match(db: Session, user_id: int, match_id: str):
        return db.query(UserFavorite).filter(
            and_(UserFavorite.user_id == user_id, UserFavorite.match_id == match_id)
        ).first()

    @staticmethod
    def get_by_user_and_team(db: Session, user_id: int, team_id: str):
        return db.query(UserFavorite).filter(
            and_(UserFavorite.user_id == user_id, UserFavorite.team_id == team_id)
        ).first()

    @staticmethod
    def add_match_favorite(db: Session, user_id: int, match_id: str):
        existing = FavoriteService.get_by_user_and_match(db, user_id, match_id)
        if existing:
            return existing
        favorite = UserFavorite(user_id=user_id, match_id=match_id, type='match')
        db.add(favorite)
        db.commit()
        db.refresh(favorite)
        return favorite

    @staticmethod
    def add_team_favorite(db: Session, user_id: int, team_id: str):
        existing = FavoriteService.get_by_user_and_team(db, user_id, team_id)
        if existing:
            return existing
        favorite = UserFavorite(user_id=user_id, team_id=team_id, type='team')
        db.add(favorite)
        db.commit()
        db.refresh(favorite)
        return favorite

    @staticmethod
    def remove_match_favorite(db: Session, user_id: int, match_id: str):
        favorite = FavoriteService.get_by_user_and_match(db, user_id, match_id)
        if favorite:
            db.delete(favorite)
            db.commit()
        return favorite

    @staticmethod
    def remove_team_favorite(db: Session, user_id: int, team_id: str):
        favorite = FavoriteService.get_by_user_and_team(db, user_id, team_id)
        if favorite:
            db.delete(favorite)
            db.commit()
        return favorite
