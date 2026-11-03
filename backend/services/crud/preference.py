from services.crud._common import *

class PreferenceService:
    @staticmethod
    def get_by_user(db: Session, user_id: int):
        return db.query(UserPreference).filter(UserPreference.user_id == user_id).first()

    @staticmethod
    def create_or_update(db: Session, user_id: int, data: dict):
        preference = PreferenceService.get_by_user(db, user_id)
        if preference:
            for key, value in data.items():
                setattr(preference, key, value)
            db.commit()
            db.refresh(preference)
            return preference
        data['user_id'] = user_id
        preference = UserPreference(**data)
        db.add(preference)
        db.commit()
        db.refresh(preference)
        return preference
