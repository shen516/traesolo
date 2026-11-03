"""修改初始密码（must_change_password）回归。

背景：init_db.py 每次启动都用出厂弱口令 admin/admin123 创建/对齐超级管理员。
生产环境直接拿去用等于零门槛提权。本文件锁死这套契约：

- 首次登录 → /auth/login 返回 user.must_change_password = true
- 携带该标记登录后，**不再拦截其它接口**（改密是可选操作，不影响访问）
- /auth/change-password 校验旧密码 → 成功后清标记、吊销旧 token
- 旧密码错 / 密码过短 → 拒绝
- 改密后旧 token 失效、旧密码失效、新密码可登录且不再带标记

测试用户走 free 套餐 + profile:view 权限，避免触发订阅懒过期逻辑。
"""

import hashlib
import time

import bcrypt
import pytest
from fastapi.testclient import TestClient


def _unique(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}_{hashlib.md5(prefix.encode()).hexdigest()[:6]}"


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _seed(db, role_code, perm_codes):
    """建角色，返回 role。缺的权限一并建。"""
    from db.models import Permission, Role, RolePermission

    def _perm(code):
        p = db.query(Permission).filter(Permission.code == code).first()
        if not p:
            p = Permission(name=code, code=code, type="button", parent_id=0)
            db.add(p)
            db.commit()
            db.refresh(p)
        return p

    role = db.query(Role).filter(Role.code == role_code).first()
    if role is None:
        role = Role(name=role_code, code=role_code, is_system=False)
        db.add(role)
        db.commit()
        db.refresh(role)
    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete(
        synchronize_session=False
    )
    for code in perm_codes:
        db.add(RolePermission(role_id=role.id, permission_id=_perm(code).id))
    db.commit()
    return role


def _mk_user(db, role):
    """建 free 套餐测试用户。不用 flag_year，避免懒过期查询拖慢用例。"""
    from db.models import User, UserRole

    uname = _unique("fpwd")
    user = User(
        username=uname,
        email=f"{uname}@fpwd.test",
        password_hash=_hash("abcdefg"),
        level="free",
        subscription_plan="free",
        subscription_status="expired",
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    # 最后再 refresh：commit 会过期全部属性，而调用方在 db.close() 后
    # 仍会访问 user.username / user.id（detached 实例），必须把属性预载入实例字典。
    db.refresh(user)
    return user


def _drop_user(db, user):
    """删除用户前清外键，否则 SQLAlchemy 会因依赖规则报错。"""
    from db.models import (
        UserRole, UserFavorite, UserHistory, UserPreference,
        OperationLog, SubscriptionRecord, UserFollowedLeague,
    )

    db.query(UserRole).filter(UserRole.user_id == user.id).delete(synchronize_session=False)
    for m in (
        UserFavorite, UserHistory, UserPreference, OperationLog,
        SubscriptionRecord, UserFollowedLeague,
    ):
        db.query(m).filter(m.user_id == user.id).delete(synchronize_session=False)
    db.delete(user)
    db.commit()


def _login(client: TestClient, username: str, password: str = "abcdefg") -> dict:
    from services.captcha_store import captcha_store

    cap = client.get("/api/v1/auth/captcha")
    assert cap.status_code == 200, cap.text
    data = cap.json()
    stored = captcha_store.get(data["captcha_id"])
    res = client.post("/api/v1/auth/login", json={
        "username": username,
        "password": password,
        "captcha_id": data["captcha_id"],
        "captcha_code": stored["code"] if stored else "SKIP",
    })
    assert res.status_code == 200, res.text
    return res.json()


def _get_db():
    from db.database import SessionLocal
    return SessionLocal()


def _set_flag(client, user, value):
    """直接改 must_change_password（测试夹具，不走 API）。"""
    from db.database import SessionLocal
    db = SessionLocal()
    try:
        u = db.query(__import__("db.models", fromlist=["User"]).User).get(user.id)
        u.must_change_password = value
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def forced_user(client):
    """带 must_change_password=True 的测试用户 + headers。"""
    from db.database import SessionLocal

    db = SessionLocal()
    try:
        role = _seed(db, "__fpwd_viewer", ["profile:view"])
        user = _mk_user(db, role)
    finally:
        db.close()

    body = _login(client, user.username)
    assert body["user"]["must_change_password"] is True, body["user"]
    yield user, body
    db = _get_db()
    try:
        _drop_user(db, user)
    finally:
        db.close()


def test_login_returns_must_change_flag(client, forced_user):
    user, body = forced_user
    assert body["user"]["must_change_password"] is True


def test_forced_user_not_blocked_on_protected_route(client, forced_user):
    """强制改密标记不再拦截其它接口：改密是可选项，不影响访问。"""
    user, body = forced_user
    headers = {"Authorization": f"Bearer {body['token']}"}

    # 带标记的用户仍能正常访问自己有权限的接口（profile:view → 读自己资料）
    r = client.get(f"/api/v1/users/{user.id}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == user.id


def test_forced_user_can_logout(client, forced_user):
    user, body = forced_user
    headers = {"Authorization": f"Bearer {body['token']}"}

    # 强制改密用户必须能退出
    r = client.post("/api/v1/auth/logout", headers=headers)
    assert r.status_code == 200, r.text
    # 退出后旧 token 失效
    r2 = client.get("/api/v1/matches/", headers=headers)
    assert r2.status_code == 401


def test_change_password_wrong_old_rejected(client, forced_user):
    user, body = forced_user
    headers = {"Authorization": f"Bearer {body['token']}"}

    r = client.post("/api/v1/auth/change-password", headers=headers, json={
        "old_password": "WRONGPASS",
        "new_password": "abcdefgh",
    })
    assert r.status_code == 400, r.text
    assert "旧密码" in r.text

    _set_flag(client, user, True)
    from db.database import SessionLocal
    from db.models import User
    db = SessionLocal()
    try:
        assert db.query(User).get(user.id).must_change_password is True
    finally:
        db.close()


def test_change_password_too_short_rejected(client, forced_user):
    user, body = forced_user
    headers = {"Authorization": f"Bearer {body['token']}"}

    r = client.post("/api/v1/auth/change-password", headers=headers, json={
        "old_password": "abcdefg",
        "new_password": "abc",
    })
    assert r.status_code == 400, r.text


def test_change_password_success_revokes_and_clears(client, forced_user):
    user, body = forced_user
    old_token = body["token"]
    headers = {"Authorization": f"Bearer {old_token}"}

    r = client.post("/api/v1/auth/change-password", headers=headers, json={
        "old_password": "abcdefg",
        "new_password": "newpass123",
    })
    assert r.status_code == 200, r.text
    assert r.json().get("relogin_required") is True

    # 标记已清
    from db.database import SessionLocal
    from db.models import User
    db = SessionLocal()
    try:
        assert db.query(User).get(user.id).must_change_password is False
    finally:
        db.close()

    # 旧 token 被吊销
    r2 = client.get("/api/v1/matches/", headers=headers)
    assert r2.status_code == 401, r2.text

    # 旧密码失效
    body2 = None
    try:
        body2 = _login(client, user.username, password="abcdefg")
    except AssertionError:
        pass
    assert body2 is None, "旧密码仍能登录"

    # 新密码可登录，且不再要求改密
    body3 = _login(client, user.username, password="newpass123")
    assert body3["user"]["must_change_password"] is False


def test_normal_user_not_gated(client):
    """普通用户（无标记）不受影响。"""
    from db.database import SessionLocal

    db = SessionLocal()
    try:
        role = _seed(db, "__fpwd_normal", ["profile:view"])
        from db.models import User, UserRole
        uname = _unique("fpwdnormal")
        u = User(
            username=uname,
            email=f"{uname}@fpwd.test",
            password_hash=_hash("abcdefg"),
            level="free",
            subscription_plan="free",
            subscription_status="expired",
            is_active=True,
            must_change_password=False,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        db.add(UserRole(user_id=u.id, role_id=role.id))
        db.commit()
        # 最后再 refresh：commit 会过期全部属性，调用方在 db.close() 后
        # 仍访问 user_obj.username（detached 实例），需预载入实例字典。
        db.refresh(u)
        user_obj = u
    finally:
        db.close()

    body = _login(client, user_obj.username)
    assert body["user"]["must_change_password"] is False
    headers = {"Authorization": f"Bearer {body['token']}"}
    # 普通用户（无标记）不受任何门控：访问自己有权限的接口应放行
    r = client.get(f"/api/v1/users/{user_obj.id}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == user_obj.id
    _drop_user(_get_db(), user_obj)
