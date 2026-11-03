from services.crud._common import *

class MatchPlayerStatService:
    @staticmethod
    def get_all(db: Session):
        return db.query(MatchPlayerStat).order_by(desc(MatchPlayerStat.created_at)).all()

    @staticmethod
    def get_by_id(db: Session, stat_id: int):
        return db.query(MatchPlayerStat).filter(MatchPlayerStat.id == stat_id).first()

    @staticmethod
    def get_by_match(db: Session, match_id: str):
        return db.query(MatchPlayerStat).filter(MatchPlayerStat.match_id == match_id).order_by(MatchPlayerStat.is_home.desc(), MatchPlayerStat.position).all()

    @staticmethod
    def get_by_player(db: Session, player_id: str, limit: int = 20):
        return db.query(MatchPlayerStat).filter(MatchPlayerStat.player_id == player_id).order_by(desc(MatchPlayerStat.created_at)).limit(limit).all()

    @staticmethod
    def get_by_team(db: Session, team_id: str, limit: int = 50):
        return db.query(MatchPlayerStat).filter(MatchPlayerStat.team_id == team_id).order_by(desc(MatchPlayerStat.created_at)).limit(limit).all()

    @staticmethod
    def create(db: Session, data: dict):
        stat = MatchPlayerStat(**data)
        db.add(stat)
        db.commit()
        db.refresh(stat)
        return stat

    @staticmethod
    def batch_create(db: Session, stats_data: list):
        stats = [MatchPlayerStat(**data) for data in stats_data]
        db.add_all(stats)
        db.commit()
        return len(stats)

    @staticmethod
    def update(db: Session, stat_id: int, data: dict):
        stat = db.query(MatchPlayerStat).filter(MatchPlayerStat.id == stat_id).first()
        if stat:
            for key, value in data.items():
                setattr(stat, key, value)
            db.commit()
            db.refresh(stat)
        return stat

    @staticmethod
    def delete_by_match(db: Session, match_id: str):
        db.query(MatchPlayerStat).filter(MatchPlayerStat.match_id == match_id).delete()
        db.commit()
