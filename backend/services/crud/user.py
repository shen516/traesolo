from services.crud._common import *

class UserService:
    @staticmethod
    def get_all(db: Session):
        return db.query(User).all()

    @staticmethod
    def get_by_id(db: Session, user_id: int):
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def get_by_username(db: Session, username: str):
        return db.query(User).filter(User.username == username).first()

    @staticmethod
    def get_by_email(db: Session, email: str):
        return db.query(User).filter(User.email == email).first()

    @staticmethod
    def create(db: Session, data: dict):
        user = User(**data)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def update(db: Session, user_id: int, data: dict):
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            for key, value in data.items():
                setattr(user, key, value)
            db.commit()
            db.refresh(user)
        return user

    @staticmethod
    def update_last_login(db: Session, user_id: int):
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.last_login_at = datetime.now()
            db.commit()
            db.refresh(user)
        return user

    @staticmethod
    def increment_analysis_count(db: Session, user_id: int):
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.total_analysis = (user.total_analysis or 0) + 1
            db.commit()
            db.refresh(user)
        return user
