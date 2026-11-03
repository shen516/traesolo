from services.crud._common import *

class CrawlLogService:
    @staticmethod
    def get_all(db: Session):
        return db.query(CrawlLog).order_by(desc(CrawlLog.started_at)).all()

    @staticmethod
    def get_by_id(db: Session, log_id: int):
        return db.query(CrawlLog).filter(CrawlLog.id == log_id).first()

    @staticmethod
    def get_by_type(db: Session, crawl_type: str):
        return db.query(CrawlLog).filter(CrawlLog.crawl_type == crawl_type).order_by(desc(CrawlLog.started_at)).all()

    @staticmethod
    def get_by_league(db: Session, league_id: str):
        return db.query(CrawlLog).filter(CrawlLog.league_id == league_id).order_by(desc(CrawlLog.started_at)).all()

    @staticmethod
    def get_by_status(db: Session, status: str):
        return db.query(CrawlLog).filter(CrawlLog.status == status).order_by(desc(CrawlLog.started_at)).all()

    @staticmethod
    def get_recent(db: Session, hours: int = 24):
        from datetime import timedelta
        start_time = datetime.now() - timedelta(hours=hours)
        return db.query(CrawlLog).filter(CrawlLog.started_at >= start_time).order_by(desc(CrawlLog.started_at)).all()

    @staticmethod
    def create(db: Session, data: dict):
        log = CrawlLog(**data)
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def delete(db: Session, log_id: int):
        log = db.query(CrawlLog).filter(CrawlLog.id == log_id).first()
        if log:
            db.delete(log)
            db.commit()
        return log

    @staticmethod
    def delete_old(db: Session, days: int = 30):
        from datetime import timedelta
        cutoff_time = datetime.now() - timedelta(days=days)
        db.query(CrawlLog).filter(CrawlLog.started_at < cutoff_time).delete()
        db.commit()
