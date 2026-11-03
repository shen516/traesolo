from services.crud._common import *

class PlayerService:
    @staticmethod
    def get_all(db: Session):
        return db.query(Player).order_by(Player.name).all()

    @staticmethod
    def get_by_id(db: Session, player_id: str):
        return db.query(Player).filter(Player.id == player_id).first()

    @staticmethod
    def get_by_team(db: Session, team_id: str):
        return db.query(Player).filter(Player.team_id == team_id).order_by(Player.jersey_number).all()

    @staticmethod
    def get_by_league(db: Session, league_id: str):
        return db.query(Player).join(Team).filter(Team.league_id == league_id).order_by(Team.name, Player.jersey_number).all()

    @staticmethod
    def get_by_position(db: Session, position: str):
        return db.query(Player).filter(Player.position == position).order_by(Player.name).all()

    @staticmethod
    def search(db: Session, keyword: str):
        return db.query(Player).filter(Player.name.contains(keyword) | Player.short_name.contains(keyword)).order_by(Player.name).all()

    @staticmethod
    def create(db: Session, data: dict):
        player = Player(**data)
        db.add(player)
        db.commit()
        db.refresh(player)
        return player

    @staticmethod
    def update(db: Session, player_id: str, data: dict):
        player = db.query(Player).filter(Player.id == player_id).first()
        if player:
            for key, value in data.items():
                setattr(player, key, value)
            db.commit()
            db.refresh(player)
        return player

    @staticmethod
    def delete(db: Session, player_id: str):
        player = db.query(Player).filter(Player.id == player_id).first()
        if player:
            db.delete(player)
            db.commit()
        return player

    @staticmethod
    def get_top_scorers(db: Session, team_id: str = None, limit: int = 10):
        query = db.query(Player)
        if team_id:
            query = query.filter(Player.team_id == team_id)
        return query.order_by(desc(Player.goals)).limit(limit).all()

    @staticmethod
    def team_squad_index(
        db: Session,
        team_id: str,
        *,
        min_apps: int = 1,
        min_players: int = 5,
        assist_weight: float = 0.5,
    ) -> dict | None:
        """阵容进攻指数：有出场球员的 (进球+加权助攻)/出场 合计。

        返回 None 表示样本不足；否则含 index / goals / assists / appearances / players。
        """
        if not team_id:
            return None
        row = (
            db.query(
                func.coalesce(func.sum(Player.goals), 0),
                func.coalesce(func.sum(Player.assists), 0),
                func.coalesce(func.sum(Player.appearances), 0),
                func.count(Player.id),
            )
            .filter(
                Player.team_id == team_id,
                func.coalesce(Player.appearances, 0) >= int(min_apps or 1),
            )
            .first()
        )
        if not row:
            return None
        goals = int(row[0] or 0)
        assists = int(row[1] or 0)
        apps = int(row[2] or 0)
        n_players = int(row[3] or 0)
        if n_players < int(min_players or 1) or apps <= 0:
            return None
        index = (goals + float(assist_weight) * assists) / float(apps)
        return {
            "index": index,
            "goals": goals,
            "assists": assists,
            "appearances": apps,
            "players": n_players,
        }
