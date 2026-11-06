"""训练提交者被禁用时：RQ 入口取消、训练循环中止且不落新权重。"""

from __future__ import annotations

import bcrypt

import pytest
from fastapi.testclient import TestClient


def _mk_active_user(db, username: str = "train_user_dis"):
    from db.models import User, Role, UserRole

    existing = db.query(User).filter(User.username == username).first()
    if existing:
        for model in ("UserFavorite", "UserHistory", "UserPreference", "OperationLog", "UserRole", "SubscriptionRecord"):
            try:
                cls = getattr(__import__("db.models", fromlist=[model]), model)
                db.query(cls).filter(cls.user_id == existing.id).delete(synchronize_session=False)
            except Exception:
                pass
        db.delete(existing)
        db.commit()

    pwd = bcrypt.hashpw(b"TrainUser1!", bcrypt.gensalt()).decode("utf-8")
    u = User(
        username=username,
        email=f"{username}@test.local",
        password_hash=pwd,
        level="professional",
        subscription_plan="free",
        subscription_status="active",
        is_active=True,
        must_change_password=False,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    role = db.query(Role).filter(Role.code == "super_admin").first()
    if role:
        db.add(UserRole(user_id=u.id, role_id=role.id))
        db.commit()
    return u


def test_run_training_job_cancels_when_user_disabled(client: TestClient, admin_token):
    from db.database import SessionLocal
    from db.models import User
    from services.jobs.tasks import run_training_job
    from services.train_lock import train_lock

    db = SessionLocal()
    try:
        u = _mk_active_user(db)
        uid = u.id
        train_lock.set_queued_user(uid)
        u.is_active = False
        db.commit()
    finally:
        db.close()

    out = run_training_job()
    assert out["status"] == "cancelled"
    assert out["code"] == "TRAINING_USER_DISABLED"

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == uid).first()
        if u:
            for model in ("UserRole", "UserPreference", "UserFavorite", "UserHistory", "OperationLog", "SubscriptionRecord"):
                try:
                    cls = getattr(__import__("db.models", fromlist=[model]), model)
                    db.query(cls).filter(cls.user_id == u.id).delete(synchronize_session=False)
                except Exception:
                    pass
            db.delete(u)
            db.commit()
    finally:
        db.close()


def test_assert_runner_allowed_raises_training_user_disabled(client: TestClient):
    from db.database import SessionLocal
    from db.models import User
    from services.train_lock import train_lock
    from services.training_service import TrainingUserDisabled, training_service

    db = SessionLocal()
    try:
        u = _mk_active_user(db, username="train_assert_dis")
        train_lock.set_queued_user(u.id)
        u.is_active = False
        db.commit()
        with pytest.raises(TrainingUserDisabled):
            training_service._assert_runner_allowed(db)
    finally:
        u = db.query(User).filter(User.username == "train_assert_dis").first()
        if u:
            for model in ("UserRole", "UserPreference", "UserFavorite", "UserHistory", "OperationLog", "SubscriptionRecord"):
                try:
                    cls = getattr(__import__("db.models", fromlist=[model]), model)
                    db.query(cls).filter(cls.user_id == u.id).delete(synchronize_session=False)
                except Exception:
                    pass
            db.delete(u)
            db.commit()
        db.close()
