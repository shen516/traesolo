from services.crud._common import *

class StandingService:
    @staticmethod
    def get_by_league(db: Session, league_id: str, season: str = None):
        query = db.query(Standing).filter(Standing.league_id == league_id)
        if season:
            query = query.filter(Standing.season == season)
        else:
            latest = StandingService.get_latest_season(db, league_id)
            if latest:
                query = query.filter(Standing.season == latest)
        return query.order_by(Standing.rank).all()

    @staticmethod
    def get_latest_season(db: Session, league_id: str) -> str | None:
        row = (
            db.query(Standing.season)
            .filter(Standing.league_id == league_id)
            .order_by(desc(Standing.update_date), desc(Standing.season))
            .first()
        )
        return row[0] if row else None

    @staticmethod
    def get_team_row(db: Session, league_id: str, team_id: str, season: str = None):
        query = db.query(Standing).filter(
            Standing.league_id == league_id,
            Standing.team_id == team_id,
        )
        if season:
            query = query.filter(Standing.season == season)
        else:
            latest = StandingService.get_latest_season(db, league_id)
            if latest:
                query = query.filter(Standing.season == latest)
        return query.first()

    @staticmethod
    def get_all(db: Session):
        return db.query(Standing).order_by(Standing.league_id, Standing.season, Standing.rank).all()

    @staticmethod
    def create(db: Session, data: dict):
        standing = Standing(**data)
        db.add(standing)
        db.commit()
        db.refresh(standing)
        return standing

    @staticmethod
    def update(db: Session, standing_id: int, data: dict):
        standing = db.query(Standing).filter(Standing.id == standing_id).first()
        if standing:
            for key, value in data.items():
                setattr(standing, key, value)
            db.commit()
            db.refresh(standing)
        return standing

    @staticmethod
    def replace_for_league_season(db: Session, league_id: str, season: str, rows: list) -> int:
        db.query(Standing).filter(
            Standing.league_id == league_id,
            Standing.season == season,
        ).delete(synchronize_session=False)
        for row in rows:
            db.add(Standing(**row))
        db.commit()
        return len(rows)

    @staticmethod
    def delete(db: Session, standing_id: int):
        standing = db.query(Standing).filter(Standing.id == standing_id).first()
        if standing:
            db.delete(standing)
            db.commit()
        return standing
