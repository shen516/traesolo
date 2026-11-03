from services.crud._common import *

class ScorerService:
    @staticmethod
    def get_by_league(db: Session, league_id: str, season: str = None):
        query = db.query(TopScorer).filter(TopScorer.league_id == league_id)
        if season:
            query = query.filter(TopScorer.season == season)
        else:
            latest = ScorerService.get_latest_season(db, league_id)
            if latest:
                query = query.filter(TopScorer.season == latest)
        return query.order_by(desc(TopScorer.goals), desc(TopScorer.assists)).all()

    @staticmethod
    def get_latest_season(db: Session, league_id: str) -> str | None:
        row = (
            db.query(TopScorer.season)
            .filter(TopScorer.league_id == league_id)
            .order_by(desc(TopScorer.update_date), desc(TopScorer.season))
            .first()
        )
        return row[0] if row else None

    @staticmethod
    def team_goals_share(db: Session, league_id: str, team_id: str, season: str = None, top_n: int = 20) -> float:
        """球队在射手榜前列的进球占比（0~1），无数据返回 0。"""
        rows = ScorerService.get_by_league(db, league_id, season)[:top_n]
        if not rows:
            return 0.0
        total = sum(int(r.goals or 0) for r in rows) or 1
        team_goals = sum(int(r.goals or 0) for r in rows if r.team_id == team_id)
        return team_goals / total

    @staticmethod
    def get_all(db: Session):
        return db.query(TopScorer).order_by(TopScorer.league_id, desc(TopScorer.goals)).all()

    @staticmethod
    def create(db: Session, data: dict):
        scorer = TopScorer(**data)
        db.add(scorer)
        db.commit()
        db.refresh(scorer)
        return scorer

    @staticmethod
    def update(db: Session, scorer_id: int, data: dict):
        scorer = db.query(TopScorer).filter(TopScorer.id == scorer_id).first()
        if scorer:
            for key, value in data.items():
                if hasattr(scorer, key):
                    setattr(scorer, key, value)
            db.commit()
            db.refresh(scorer)
        return scorer

    @staticmethod
    def delete(db: Session, scorer_id: int):
        scorer = db.query(TopScorer).filter(TopScorer.id == scorer_id).first()
        if scorer:
            db.delete(scorer)
            db.commit()
        return scorer

    @staticmethod
    def replace_for_league_season(db: Session, league_id: str, season: str, rows: list) -> int:
        db.query(TopScorer).filter(
            TopScorer.league_id == league_id,
            TopScorer.season == season,
        ).delete(synchronize_session=False)
        for row in rows:
            db.add(TopScorer(**row))
        db.commit()
        return len(rows)
