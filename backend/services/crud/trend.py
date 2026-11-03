from services.crud._common import *

class TrendService:
    @staticmethod
    def get_by_version(db: Session, version: str):
        return db.query(AccuracyTrend).filter(AccuracyTrend.model_version == version).order_by(AccuracyTrend.date).all()

    @staticmethod
    def get_recent(db: Session, days: int = 30):
        from datetime import timedelta
        from db.models import TrainingRecord, ModelVersion

        start_date = date.today() - timedelta(days=days)
        rows = db.query(AccuracyTrend).filter(
            AccuracyTrend.date >= start_date
        ).order_by(AccuracyTrend.date).all()
        if rows:
            return rows

        # 无趋势点时，从训练记录与模型版本历史回填
        records = (
            db.query(TrainingRecord)
            .filter(
                TrainingRecord.status == "success",
                TrainingRecord.accuracy.isnot(None),
                TrainingRecord.finished_at.isnot(None),
            )
            .order_by(TrainingRecord.finished_at)
            .all()
        )
        if records:
            out = []
            for rec in records:
                acc = float(rec.accuracy)
                acc_pct = acc * 100 if acc <= 1 else acc
                d = rec.finished_at.date() if rec.finished_at else date.today()
                if d < start_date:
                    continue
                out.append({
                    "id": rec.id,
                    "model_version": rec.model_version or f"train-{rec.id}",
                    "date": d,
                    "accuracy": round(acc_pct, 2),
                    "total_matches": rec.total_matches or 0,
                    "correct_matches": int((rec.total_matches or 0) * acc) if acc <= 1 else 0,
                })
            if out:
                return out

        versions = (
            db.query(ModelVersion)
            .filter(ModelVersion.accuracy.isnot(None))
            .order_by(ModelVersion.created_at)
            .all()
        )
        out = []
        for mv in versions:
            d = mv.created_at.date() if mv.created_at else date.today()
            if d < start_date:
                continue
            acc = float(mv.accuracy)
            out.append({
                "id": mv.id,
                "model_version": mv.version,
                "date": d,
                "accuracy": acc,
                "total_matches": 0,
                "correct_matches": 0,
            })
        return out

    @staticmethod
    def get_all(db: Session):
        return db.query(AccuracyTrend).order_by(AccuracyTrend.date).all()

    @staticmethod
    def create(db: Session, data: dict):
        trend = AccuracyTrend(**data)
        db.add(trend)
        db.commit()
        db.refresh(trend)
        return trend

    @staticmethod
    def delete(db: Session, trend_id: int):
        trend = db.query(AccuracyTrend).filter(AccuracyTrend.id == trend_id).first()
        if trend:
            db.delete(trend)
            db.commit()
        return trend
