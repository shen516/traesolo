from services.crud._common import *

class TeamService:
    @staticmethod
    def get_all(db: Session):
        return db.query(Team).join(League).filter(League.is_active == True).order_by(Team.name).all()

    @staticmethod
    def get_by_id(db: Session, team_id: str):
        return db.query(Team).filter(Team.id == team_id).first()

    @staticmethod
    def get_by_league(db: Session, league_id: str):
        return db.query(Team).filter(Team.league_id == league_id).order_by(Team.name).all()

    @staticmethod
    def search(db: Session, keyword: str):
        return db.query(Team).join(League).filter(League.is_active == True,
            (Team.name.contains(keyword) | Team.short_name.contains(keyword) | Team.id.contains(keyword))
        ).order_by(Team.name).all()

    @staticmethod
    def create(db: Session, data: dict):
        team = Team(**data)
        db.add(team)
        db.commit()
        db.refresh(team)
        return team

    @staticmethod
    def update(db: Session, team_id: str, data: dict):
        team = db.query(Team).filter(Team.id == team_id).first()
        if team:
            for key, value in data.items():
                if value is not None:
                    setattr(team, key, value)
            db.commit()
            db.refresh(team)
        return team

    @staticmethod
    def update_elo(db: Session, team_id: str, new_elo: int):
        team = db.query(Team).filter(Team.id == team_id).first()
        if team:
            team.elo_rating = new_elo
            db.commit()
            db.refresh(team)
        return team

    @staticmethod
    def update_strength(db: Session, team_id: str, attack: float, defense: float):
        team = db.query(Team).filter(Team.id == team_id).first()
        if team:
            team.attack_strength = attack
            team.defense_strength = defense
            db.commit()
            db.refresh(team)
        return team
