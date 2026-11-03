"""准确率趋势 API 的权限边界回归。

背景：`api/trend.py` 曾用 `APIRouter(dependencies=[RequireModelManage])`，
把三个 GET 读接口从"只要求登录"升格成"必须 model:manage"，导致只持
`dashboard:view` 的普通用户读不到准确率趋势——原问题本是"元数据可见过宽"，
修方向反了。

期望语义：
- 三个 GET → RequireModelRead = `model:manage` **或** `dashboard:view`
- POST / DELETE → RequireModelManage = `model:manage`

注意：router 级不能挂 `APIRouter(dependencies=[...])`。FastAPI 中函数级
dependencies 会与 router 级叠加（两者都需满足），那样读接口就会被逼成
model:manage。此文件锁死这个契约。
"""

import hashlib
import time

from fastapi.testclient import TestClient


TREND_GETS = ("/api/v1/trend/", "/api/v1/trend/version/v5.0.3", "/api/v1/trend/recent/30")


def _unique(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}_{hashlib.md5(prefix.encode()).hexdigest()[:6]}"


def _seed_role(db, code, perm_codes):
    """按权限码建角色（缺的权限一并建）。返回 role。"""
    from db.models import Role, Permission, RolePermission

    def _perm(pcode):
        p = db.query(Permission).filter(Permission.code == pcode).first()
        if not p:
            p = Permission(name=pcode, code=pcode, type="button", parent_id=0)
            db.add(p)
            db.commit()
            db.refresh(p)
        return p

    r = db.query(Role).filter(Role.code == code).first()
    if r is None:
        r = Role(name=code, code=code, is_system=False)
        db.add(r)
        db.commit()
        db.refresh(r)
    db.query(RolePermission).filter(RolePermission.role_id == r.id).delete(synchronize_session=False)
    for pcode in perm_codes:
        db.add(RolePermission(role_id=r.id, permission_id=_perm(pcode).id))
    db.commit()
    return r


def _mk_user(db, role):
    """建用户并挂会话权限，返回 user。"""
    from api.deps import load_user_auth_payload
    from db.models import User, UserRole

    uname = _unique("trend")
    u = User(username=uname, email=f"{uname}@trend.test", password_hash="x",
             level="free", subscription_plan="free", subscription_status="active",
             is_active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(UserRole(user_id=u.id, role_id=role.id))
    db.commit()

    payload = load_user_auth_payload(db, u)
    u._session_roles = payload["roles"]
    u._session_permissions = payload["permissions"]
    return u


def _headers_for(client, user):
    """注入内存 token，返回 headers。"""
    from api.deps import store_token

    tok = hashlib.md5(f"{user.id}:{user.username}:trend".encode()).hexdigest()
    roles = list(user._session_roles) if getattr(user, "_session_roles", None) else []
    store_token(tok, user.id, user.username, roles, list(user._session_permissions))
    return {"Authorization": f"Bearer {tok}"}


def _drop_user(db, u):
    from db.models import (
        UserRole, UserFavorite, UserHistory, UserPreference,
        OperationLog, SubscriptionRecord, UserFollowedLeague,
    )

    db.query(UserRole).filter(UserRole.user_id == u.id).delete(synchronize_session=False)
    for m in (UserFavorite, UserHistory, UserPreference, OperationLog,
              SubscriptionRecord, UserFollowedLeague):
        db.query(m).filter(m.user_id == u.id).delete(synchronize_session=False)
    db.delete(u)
    db.commit()


def _admin_headers(client):
    """超管走真实登录。不 import conftest（它不是可导入模块），本地复刻登录流程。"""
    from services.captcha_store import captcha_store

    cap = client.get("/api/v1/auth/captcha")
    assert cap.status_code == 200, cap.text
    data = cap.json()
    stored = captcha_store.get(data["captcha_id"])
    res = client.post("/api/v1/auth/login", json={
        "username": "admin",
        "password": "admin123",
        "captcha_id": data["captcha_id"],
        "captcha_code": stored["code"] if stored else "SKIP",
    })
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def test_trend_reads_require_only_dashboard_view(client: TestClient):
    """dashboard:view 用户能读趋势——这是本次回归要锁的核心。"""
    from db.database import SessionLocal

    db = SessionLocal()
    try:
        role = _seed_role(db, "__trend_dashboard_view", ["dashboard:view"])
        user = _mk_user(db, role)
        headers = _headers_for(client, user)

        for url in TREND_GETS:
            r = client.get(url, headers=headers)
            assert r.status_code == 200, f"{url} -> {r.status_code}: {r.text[:200]}"
    finally:
        try:
            _drop_user(db, user)
        except Exception:
            db.rollback()
        db.close()


def test_trend_reads_reject_plain_viewer(client: TestClient):
    """只持 profile:view 的用户仍被拦（可见过宽的原问题不能回退）。"""
    from db.database import SessionLocal

    db = SessionLocal()
    try:
        role = _seed_role(db, "__trend_viewer_only", ["profile:view"])
        user = _mk_user(db, role)
        headers = _headers_for(client, user)

        for url in TREND_GETS:
            r = client.get(url, headers=headers)
            assert r.status_code == 403, f"{url} -> {r.status_code}: {r.text[:200]}"
    finally:
        try:
            _drop_user(db, user)
        except Exception:
            db.rollback()
        db.close()


def test_trend_writes_require_model_manage(client: TestClient):
    """dashboard:view 够读不够写：POST 必须 403。"""
    from db.database import SessionLocal

    db = SessionLocal()
    try:
        role = _seed_role(db, "__trend_dashboard_view", ["dashboard:view"])
        user = _mk_user(db, role)
        headers = _headers_for(client, user)

        r = client.post("/api/v1/trend/", headers=headers,
                        json={"model_version": "v5.0.3", "date": "2026-10-26",
                              "total_matches": 0, "correct_matches": 0})
        assert r.status_code == 403, r.text
    finally:
        try:
            _drop_user(db, user)
        except Exception:
            db.rollback()
        db.close()


def test_trend_delete_requires_model_manage(client: TestClient):
    from db.database import SessionLocal

    db = SessionLocal()
    try:
        role = _seed_role(db, "__trend_viewer_only", ["profile:view"])
        user = _mk_user(db, role)
        headers = _headers_for(client, user)

        r = client.delete("/api/v1/trend/99999999", headers=headers)
        assert r.status_code == 403, r.text
    finally:
        try:
            _drop_user(db, user)
        except Exception:
            db.rollback()
        db.close()


def test_trend_admin_can_read(client: TestClient):
    """超管路径不能被收紧逻辑误伤。"""
    headers = _admin_headers(client)
    for url in TREND_GETS:
        r = client.get(url, headers=headers)
        assert r.status_code == 200, f"{url} -> {r.status_code}: {r.text[:200]}"
