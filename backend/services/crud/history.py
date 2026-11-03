from services.crud._common import *

class HistoryService:
    @staticmethod
    def get_by_user(db: Session, user_id: int, limit: int = 20):
        return db.query(UserHistory).filter(UserHistory.user_id == user_id).order_by(desc(UserHistory.created_at)).limit(limit).all()

    @staticmethod
    def get_by_user_and_match(db: Session, user_id: int, match_id: str):
        return db.query(UserHistory).filter(
            and_(UserHistory.user_id == user_id, UserHistory.match_id == match_id)
        ).first()

    @staticmethod
    def create(db: Session, data: dict):
        history = UserHistory(**data)
        db.add(history)
        db.commit()
        db.refresh(history)
        return history

    @staticmethod
    def get_user_accuracy(db: Session, user_id: int):
        histories = db.query(UserHistory).filter(UserHistory.user_id == user_id).all()
        if not histories:
            return 0.0
        total = len(histories)
        correct = sum(1 for h in histories if h.result == 'correct')
        partial = sum(0.5 for h in histories if h.result == 'partial')
        return round(((correct + partial) / total) * 100, 2)

    @staticmethod
    def delete(db: Session, history_id: int):
        history = db.query(UserHistory).filter(UserHistory.id == history_id).first()
        if history:
            db.delete(history)
            db.commit()
        return history
