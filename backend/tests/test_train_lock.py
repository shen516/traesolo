"""训练分布式锁、进度状态与僵死记录清理。"""
import time
from datetime import datetime, timedelta

import pytest

from services.train_lock import train_lock


class _FakeRedis:
    def __init__(self):
        self.kv = {}
        self.expiry = {}

    def _dead(self, key):
        exp = self.expiry.get(key)
        return exp is not None and exp <= time.time()

    def get(self, key):
        if self._dead(key):
            self.kv.pop(key, None)
            self.expiry.pop(key, None)
            return None
        return self.kv.get(key)

    def set(self, key, value, nx=False, ex=None):
        if nx and self.get(key) is not None:
            return None
        self.kv[key] = value
        if ex is not None:
            self.expiry[key] = time.time() + float(ex)
        return True

    def eval(self, script, numkeys, key, token, ttl=None):
        if self.get(key) != token:
            return 0
        if "del" in script:
            self.kv.pop(key, None)
            self.expiry.pop(key, None)
            return 1
        self.expiry[key] = time.time() + float(ttl or 0)
        return 1


@pytest.fixture
def memory_lock(monkeypatch):
    monkeypatch.setattr("services.train_lock.get_redis_client", lambda: None)
    held = train_lock.current_token()
    if held:
        train_lock.release(held)
    train_lock._mem_status = {}
    yield train_lock
    held = train_lock.current_token()
    if held:
        train_lock.release(held)


def test_memory_lock_is_exclusive(memory_lock):
    first = memory_lock.acquire()
    assert first
    assert memory_lock.acquire() is None
    assert memory_lock.is_locked() is True
    assert memory_lock.refresh(first) is True
    assert memory_lock.release(first) is True
    assert memory_lock.is_locked() is False
    second = memory_lock.acquire()
    assert second and second != first
    memory_lock.release(second)


def test_redis_lock_roundtrip(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr("services.train_lock.get_redis_client", lambda: fake)
    token = train_lock.acquire()
    assert token
    assert train_lock.acquire() is None
    train_lock.write_status({
        "is_training": True,
        "progress": 40,
        "message": "worker",
        "current_record_id": 7,
        "phase": "running",
    })
    status = train_lock.read_status()
    assert status["progress"] == 40
    assert status["current_record_id"] == 7
    assert train_lock.refresh(token) is True
    assert train_lock.release("not-the-owner") is False
    assert train_lock.is_locked() is True
    assert train_lock.release(token) is True
    assert train_lock.is_locked() is False


def test_busy_train_is_skipped(memory_lock):
    from services.training_service import training_service

    token = memory_lock.acquire()
    try:
        skipped = training_service.run_train_or_skip()
        assert skipped["status"] == "skipped"
        assert "正在进行中" in skipped["message"]
    finally:
        memory_lock.release(token)


def test_status_reads_shared_snapshot_while_lock_held(memory_lock):
    from services.training_service import training_service

    training_service.is_training = False
    token = memory_lock.acquire()
    try:
        memory_lock.write_status({
            "is_training": True,
            "progress": 55,
            "message": "训练 xG 模型...",
            "current_record_id": 11,
            "phase": "running",
        })
        status = training_service.get_training_status()
        assert status["is_training"] is True
        assert status["progress"] == 55
        assert status["message"] == "训练 xG 模型..."
        assert status["current_record_id"] == 11
    finally:
        memory_lock.release(token)
        training_service.is_training = False


def test_fail_abandoned_running_records_when_lock_free(memory_lock):
    from db.database import SessionLocal, engine
    from db.models import Base, TrainingRecord
    from services.training_service import training_service

    Base.metadata.create_all(bind=engine)
    training_service.is_training = False
    training_service.current_record_id = None
    db = SessionLocal()
    old_id = fresh_id = None
    try:
        old = TrainingRecord(
            status="running",
            message="训练进行中",
            started_at=datetime.now() - timedelta(hours=4),
        )
        fresh = TrainingRecord(
            status="running",
            message="训练进行中",
            started_at=datetime.now(),
        )
        db.add(old)
        db.add(fresh)
        db.commit()
        old_id, fresh_id = old.id, fresh.id
    finally:
        db.close()

    changed = training_service.fail_abandoned_running_records(force=True)
    assert changed >= 1

    db = SessionLocal()
    try:
        old_row = db.query(TrainingRecord).filter(TrainingRecord.id == old_id).first()
        fresh_row = db.query(TrainingRecord).filter(TrainingRecord.id == fresh_id).first()
        assert old_row.status == "failed"
        assert fresh_row.status == "running"
        db.delete(old_row)
        db.delete(fresh_row)
        db.commit()
    finally:
        db.close()
