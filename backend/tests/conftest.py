"""Pytest configuration — set env before app import."""
import os
import tempfile
from pathlib import Path

os.environ.setdefault("RUN_SCHEDULER", "0")
os.environ.setdefault("TRAESOLO_DISABLE_DOCS", "1")
os.environ.setdefault("TRAESOLO_REDIS_DISABLED", "1")
# 测试与 CI 不启用"强制改密"门控：admin 弱口令是测试夹具，不是生产配置。
os.environ.setdefault("TRAESOLO_SKIP_FORCE_PASSWORD", "1")
_test_db = Path(tempfile.gettempdir()) / "traesolo_pytest.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_test_db.as_posix()}")

import pytest
from fastapi.testclient import TestClient


def _reset_force_password_flag():
    """清空 must_change_password。

    测试库是持久缓存文件，一旦旧版本把 admin 标记成 True 就会一直存在，
    导致后续所有依赖 admin 登录的用例被门控 403 拦掉。
    门控本身的行为由专门的 test_force_password.py 单独验证（自建用户）。
    """
    from db.database import SessionLocal
    from db.models import User
    db = SessionLocal()
    try:
        db.query(User).update({"must_change_password": False}, synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def pytest_configure(config):
    _reset_force_password_flag()



@pytest.fixture(scope="session")
def client():
    from main import app

    with TestClient(app) as test_client:
        yield test_client


def _login(client: TestClient, username: str = "admin", password: str = "admin123") -> str:
    cap = client.get("/api/v1/auth/captcha")
    assert cap.status_code == 200, cap.text
    data = cap.json()
    payload = {
        "username": username,
        "password": password,
        "captcha_id": data["captcha_id"],
        "captcha_code": "SKIP",
    }
    # 测试环境无法读图：直接走内存 captcha_store
    from services.captcha_store import captcha_store
    stored = captcha_store.get(data["captcha_id"])
    if stored:
        payload["captcha_code"] = stored["code"]
    res = client.post("/api/v1/auth/login", json=payload)
    assert res.status_code == 200, res.text
    return res.json()["token"]


@pytest.fixture
def admin_token(client):
    return _login(client)


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
