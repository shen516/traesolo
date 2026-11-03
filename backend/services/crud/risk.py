from fastapi.encoders import jsonable_encoder
from services.crud._common import *

class RiskService:
    @staticmethod
    def _active_match_clause():
        """未过期赛事：仍为未赛，且开赛日期/时间尚未到达。"""
        now = datetime.now()
        return and_(
            Match.status == "upcoming",
            or_(
                Match.match_date > now.date(),
                and_(
                    Match.match_date == now.date(),
                    or_(
                        Match.match_time.is_(None),
                        Match.match_time > now.time(),
                    ),
                ),
            ),
        )

    @staticmethod
    def get_all(db: Session):
        return db.query(RiskAlert).order_by(desc(RiskAlert.created_at)).all()

    @staticmethod
    def list_filtered(
        db: Session, league_ids=None, level=None, unprocessed_only=False, upcoming_only=True,
    ):
        """league_ids=None 不过滤；[] 返回空。按赛事所属联赛过滤。

        默认只返回未过期场次预警（已开赛/已完赛不进列表）；无 match_id 的质量告警仍保留。
        """
        if league_ids is not None and not league_ids:
            return []
        query = db.query(RiskAlert)
        joined_match = False
        if league_ids:
            query = query.join(Match, RiskAlert.match_id == Match.id).filter(
                Match.league_id.in_(league_ids)
            )
            joined_match = True
        if upcoming_only:
            if not joined_match:
                query = query.outerjoin(Match, RiskAlert.match_id == Match.id)
            query = query.filter(
                or_(
                    RiskAlert.match_id.is_(None),
                    RiskService._active_match_clause(),
                )
            )
        if level:
            query = query.filter(RiskAlert.level == level)
        if unprocessed_only:
            query = query.filter(RiskAlert.is_processed == False)
        return query.order_by(desc(RiskAlert.created_at)).all()

    @staticmethod
    def serialize(db: Session, alerts: list):
        if not alerts:
            return []
        match_ids = [a.match_id for a in alerts if a.match_id]
        league_map = {}
        if match_ids:
            rows = db.query(Match.id, Match.league_id).filter(Match.id.in_(match_ids)).all()
            league_map = {row[0]: row[1] for row in rows}
        out = []
        for alert in alerts:
            item = jsonable_encoder(alert)
            item["league_id"] = league_map.get(alert.match_id)
            out.append(item)
        return out

    @staticmethod
    def get_by_match(db: Session, match_id: str):
        return db.query(RiskAlert).filter(RiskAlert.match_id == match_id).order_by(desc(RiskAlert.created_at)).all()

    @staticmethod
    def get_by_level(db: Session, level: str):
        return db.query(RiskAlert).filter(RiskAlert.level == level).order_by(desc(RiskAlert.created_at)).all()

    @staticmethod
    def get_unprocessed(db: Session):
        return db.query(RiskAlert).filter(RiskAlert.is_processed == False).order_by(desc(RiskAlert.created_at)).all()

    @staticmethod
    def create(db: Session, data: dict):
        alert = RiskAlert(**data)
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert

    @staticmethod
    def set_processed(db: Session, alert_id: int, is_processed: bool = True):
        alert = db.query(RiskAlert).filter(RiskAlert.id == alert_id).first()
        if alert:
            alert.is_processed = bool(is_processed)
            db.commit()
            db.refresh(alert)
        return alert

    @staticmethod
    def mark_processed(db: Session, alert_id: int):
        return RiskService.set_processed(db, alert_id, True)

    @staticmethod
    def delete(db: Session, alert_id: int):
        alert = db.query(RiskAlert).filter(RiskAlert.id == alert_id).first()
        if alert:
            db.delete(alert)
            db.commit()
        return alert
