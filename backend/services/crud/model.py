from services.crud._common import *

class ModelService:
    @staticmethod
    def get_all(db: Session):
        return db.query(ModelVersion).order_by(desc(ModelVersion.created_at)).all()

    @staticmethod
    def get_current(db: Session):
        return db.query(ModelVersion).filter(ModelVersion.status == 'current').first()

    @staticmethod
    def get_by_version(db: Session, version: str):
        return db.query(ModelVersion).filter(ModelVersion.version == version).first()

    @staticmethod
    def create(db: Session, data: dict):
        model = ModelVersion(**data)
        db.add(model)
        db.commit()
        db.refresh(model)
        return model

    @staticmethod
    def set_current(db: Session, version_id: int):
        db.query(ModelVersion).update({'status': 'archived'})
        model = db.query(ModelVersion).filter(ModelVersion.id == version_id).first()
        if model:
            model.status = 'current'
            db.commit()
            db.refresh(model)
        return model

    @staticmethod
    def set_current_by_version(db: Session, version: str):
        db.query(ModelVersion).update({'status': 'archived'})
        model = db.query(ModelVersion).filter(ModelVersion.version == version).first()
        if model:
            model.status = 'current'
            db.commit()
            db.refresh(model)
        return model

    @staticmethod
    def delete(db: Session, model_id: int):
        """删除模型版本；当前使用中的版本不可删，避免预测引用落空。"""
        model = db.query(ModelVersion).filter(ModelVersion.id == model_id).first()
        if not model:
            return None
        if model.status == 'current':
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="当前使用中的模型版本不可删除，请先切换到其他版本")
        db.delete(model)
        db.commit()
        return model
