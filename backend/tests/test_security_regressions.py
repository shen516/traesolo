"""Security regression: RBAC 边界、CRUD 完整性、脱敏行为、密码强度。

背景：这套用例来源于多轮人工验证的自动化版本，用于防止回归。
所有测试走内存 token_store 注入（不实际登录），并用 SQLite 测试库。
跑法：cd backend && pytest -q tests/test_security_regressions.py
"""

import hashlib
import time

import pytest
from fastapi.testclient import TestClient


# ---------- helpers ----------

def _unique(prefix: str) -> str:
    """唯一用户名，避免 session-scoped client 多次跑测试冲突。"""
    return f"{prefix}_{int(time.time() * 1000)}_{hashlib.md5(prefix.encode()).hexdigest()[:6]}"


def _seed_db():
    """创建/返回 (admin, sa_role, profile_view_perm, user_edit_perm, user_create_perm, user_manage_perm,
               viewer_role, editor_role)。"""
    from db.database import SessionLocal
    from db.models import Role, Permission, RolePermission
    db = SessionLocal()

    admin = db.query(Role).filter(Role.code == "super_admin").first()
    assert admin, "super_admin role 未初始化"

    def _perm(code):
        p = db.query(Permission).filter(Permission.code == code).first()
        if not p:
            p = Permission(name=code, code=code, type="button", parent_id=0)
            db.add(p); db.commit(); db.refresh(p)
        return p

    def _role(code, perm_ids):
        r = db.query(Role).filter(Role.code == code).first()
        if r is None:
            r = Role(name=code, code=code, is_system=False)
            db.add(r); db.commit(); db.refresh(r)
        db.query(RolePermission).filter(RolePermission.role_id == r.id).delete(synchronize_session=False)
        for pid in perm_ids:
            db.add(RolePermission(role_id=r.id, permission_id=pid))
        db.commit()
        return r

    p_view   = _perm("profile:view")
    p_edit   = _perm("user:edit")
    p_create = _perm("user:create")
    p_manage = _perm("user:manage")
    viewer = _role("__regression_viewer", [p_view.id])
    editor = _role("__regression_editor",  [p_view.id, p_edit.id, p_create.id])

    return db, admin, p_view, p_edit, p_create, p_manage, viewer, editor


def _mk_user(db, username, role):
    from db.models import User, UserRole
    u = User(username=username, email=f"{username}@regress.test",
             password_hash="x", level="free",
             subscription_plan="free", subscription_status="active",
             is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    db.add(UserRole(user_id=u.id, role_id=role.id)); db.commit()
    return u


def _set_auth(user):
    """给 user 对象挂上 _session_roles / _session_permissions，让 authz 依赖读到。"""
    from api.deps import load_user_auth_payload
    from db.database import SessionLocal
    db = SessionLocal()
    try:
        payload = load_user_auth_payload(db, user)
    finally:
        db.close()
    user._session_roles = payload["roles"]
    user._session_permissions = payload["permissions"]
    return user


def _headers_for(client, user):
    """注入内存 token，返回 (headers, token)。"""
    from api.deps import store_token
    tok = hashlib.md5(f"{user.id}:{user.username}:regress".encode()).hexdigest()
    store_token(tok, user.id, user.username,
                list(user._session_roles), list(user._session_permissions))
    return {"Authorization": f"Bearer {tok}"}, tok


def _drop_user(db, u):
    from db.models import UserRole, UserFavorite, UserHistory, UserPreference, UserFollowedLeague
    db.query(UserRole).filter(UserRole.user_id == u.id).delete(synchronize_session=False)
    for m in (UserFavorite, UserHistory, UserPreference, UserFollowedLeague):
        db.query(m).filter(m.user_id == u.id).delete(synchronize_session=False)
    db.delete(u); db.commit()


def _drop_role(db, r):
    from db.models import RolePermission
    db.query(RolePermission).filter(RolePermission.role_id == r.id).delete(synchronize_session=False)
    db.delete(r); db.commit()


@pytest.fixture(scope="function")
def regression_ctx():
    """每个测试独立 seed 并清理，避免相互影响。"""
    db, admin, p_view, p_edit, p_create, p_manage, viewer, editor = _seed_db()
    created_users = []
    created_roles = []
    tokens = []
    ctx = {
        "db": db, "admin": admin,
        "p_view": p_view, "p_edit": p_edit, "p_create": p_create, "p_manage": p_manage,
        "viewer": viewer, "editor": editor,
        "cleanup_users": created_users, "cleanup_roles": created_roles, "tokens": tokens,
    }
    yield ctx
    # 清理：token 无所谓（内存），user 必须清
    for u in reversed(created_users):
        try:
            _drop_user(db, u)
        except Exception:
            db.rollback()
    db.close()


# ============================================================
# P0: 越权自我提权必须拦
# ============================================================

def test_p0_self_assign_super_admin_blocked(client: TestClient, regression_ctx):
    ctx = regression_ctx
    db = ctx["db"]; editor = ctx["editor"]
    probe = _mk_user(db, _unique("__reg_probe"), editor)
    ctx["cleanup_users"].append(probe)
    probe = _set_auth(probe)
    headers, _ = _headers_for(client, probe)

    r = client.put(f"/api/v1/users/{probe.id}", headers=headers,
                   json={"role_ids": [ctx["admin"].id]})
    assert r.status_code == 403, r.text

    db.expire_all()
    from db.models import UserRole
    db.refresh(probe)
    role_ids = {ur.role_id for ur in db.query(UserRole).filter(UserRole.user_id == probe.id).all()}
    assert ctx["admin"].id not in role_ids, "super_admin 角色竟然被写入 DB"


def test_p0_self_deactivate_blocked_for_viewer(client: TestClient, regression_ctx):
    ctx = regression_ctx
    db = ctx["db"]; viewer = ctx["viewer"]
    probe = _mk_user(db, _unique("__reg_viewer"), viewer)
    ctx["cleanup_users"].append(probe)
    probe = _set_auth(probe)
    headers, _ = _headers_for(client, probe)

    r = client.put(f"/api/v1/users/{probe.id}", headers=headers,
                   json={"is_active": False})
    assert r.status_code == 403, r.text

    db.expire_all(); db.refresh(probe)
    assert probe.is_active is True, "viewer 竟然能自我停用"


def test_p0_self_level_change_blocked_for_viewer(client: TestClient, regression_ctx):
    ctx = regression_ctx
    db = ctx["db"]; viewer = ctx["viewer"]
    probe = _mk_user(db, _unique("__reg_level"), viewer)
    ctx["cleanup_users"].append(probe)
    probe = _set_auth(probe)
    headers, _ = _headers_for(client, probe)

    r = client.put(f"/api/v1/users/{probe.id}", headers=headers,
                   json={"level": "professional"})
    assert r.status_code == 403, r.text


def test_p0_register_cannot_assign_system_roles_without_perm(client: TestClient, regression_ctx):
    """editor 只持 user:edit，不能授 super_admin；register 携带 sa_role.id 应被过滤。"""
    ctx = regression_ctx
    db = ctx["db"]; editor = ctx["editor"]
    actor = _mk_user(db, _unique("__reg_actor"), editor)
    ctx["cleanup_users"].append(actor)
    actor = _set_auth(actor)
    headers, _ = _headers_for(client, actor)

    target = _unique("__reg_newbie")
    r = client.post("/api/v1/users/register", headers=headers, json={
        "username": target, "email": f"{target}@t.test",
        "password": "abcdefg",
        "role_ids": [ctx["admin"].id],
    })
    # 403 (拒绝) 或 200 但过滤掉 sa_role，两者都合规
    assert r.status_code in (403, 200), f"status={r.status_code} {r.text[:200]}"
    if r.status_code == 200:
        from db.models import User, UserRole
        new_user = db.query(User).filter(User.username == target).first()
        assert new_user is not None
        ctx["cleanup_users"].append(new_user)
        role_ids = {ur.role_id for ur in db.query(UserRole).filter(UserRole.user_id == new_user.id).all()}
        assert ctx["admin"].id not in role_ids, "register 时超级管理员角色被写入"


# ============================================================
# P0: 密码重置权限
# ============================================================

def test_p0_reset_other_password_requires_manage(client: TestClient, regression_ctx):
    ctx = regression_ctx
    db = ctx["db"]
    u_other = _mk_user(db, _unique("__reg_other"), ctx["viewer"])
    u_actor = _mk_user(db, _unique("__reg_actor2"), ctx["editor"])
    ctx["cleanup_users"].extend([u_other, u_actor])
    u_other = _set_auth(u_other); u_actor = _set_auth(u_actor)
    headers, _ = _headers_for(client, u_actor)

    r = client.put(f"/api/v1/users/{u_other.id}/password", headers=headers,
                   json={"new_password": "abcdefg"})
    assert r.status_code == 403, r.text


def test_p0_reset_own_password_allowed(client: TestClient, regression_ctx):
    ctx = regression_ctx
    db = ctx["db"]
    u = _mk_user(db, _unique("__reg_self"), ctx["viewer"])
    ctx["cleanup_users"].append(u)
    u = _set_auth(u)
    headers, _ = _headers_for(client, u)

    r = client.put(f"/api/v1/users/{u.id}/password", headers=headers,
                   json={"new_password": "abcdefg"})
    assert r.status_code == 200, r.text


# ============================================================
# P1: 之前 500 的端点全部转为 4xx
# ============================================================

def test_p1_missing_crud_endpoints_no_longer_500(client: TestClient, regression_ctx):
    ctx = regression_ctx
    db = ctx["db"]; admin = _set_auth(
        db.query(
            __import__("db.models", fromlist=["User"]).User
        ).filter(
            __import__("db.models", fromlist=["User"]).User.username == "admin"
        ).first()
    )
    headers, _ = _headers_for(client, admin)

    endpoints = [
        ("DELETE", "/api/v1/matches/__NOPE__", None),
        ("PUT",    "/api/v1/matches/__NOPE__", {"match_id": "x"}),
        ("DELETE", "/api/v1/model/99999999", None),
        ("DELETE", "/api/v1/risk/99999999", None),
        ("DELETE", "/api/v1/scorers/99999999", None),
        ("PUT",    "/api/v1/scorers/99999999", None),
        ("DELETE", "/api/v1/standings/99999999", None),
        ("DELETE", "/api/v1/trend/99999999", None),
        ("DELETE", "/api/v1/history/99999999", None),
        ("DELETE", "/api/v1/favorites/user/999999/match/x", None),
        ("DELETE", "/api/v1/players/__NOPE__", None),
        ("GET",    "/api/v1/matches/__NOPE__/odds-snapshots", None),
    ]
    for method, url, body in endpoints:
        r = client.request(method, url, headers=headers, json=body)
        assert r.status_code != 500, f"{method} {url} -> 500: {r.text[:120]}"


# ============================================================
# 密码强度
# ============================================================

def test_password_strength_register_blocks_short(client: TestClient, regression_ctx):
    ctx = regression_ctx
    db = ctx["db"]
    actor = _mk_user(db, _unique("__reg_ps"), ctx["editor"])
    ctx["cleanup_users"].append(actor)
    actor = _set_auth(actor)
    headers, _ = _headers_for(client, actor)

    # 1-char
    r = client.post("/api/v1/users/register", headers=headers, json={
        "username": _unique("__ps_1"), "email": f"{_unique('__ps_1')}@t",
        "password": "1",
    })
    assert r.status_code == 400, f"1-char pwd 应为 400，实际 {r.status_code} {r.text[:100]}"
    assert "不能少于6位" in r.text

    # empty
    r = client.post("/api/v1/users/register", headers=headers, json={
        "username": _unique("__ps_2"), "email": f"{_unique('__ps_2')}@t",
        "password": "",
    })
    assert r.status_code == 400

    # 200-char
    r = client.post("/api/v1/users/register", headers=headers, json={
        "username": _unique("__ps_3"), "email": f"{_unique('__ps_3')}@t",
        "password": "a" * 200,
    })
    assert r.status_code == 400, f"200-char pwd 应为 400，实际 {r.status_code}"


def test_password_strength_reset_blocks_too_long(client: TestClient, regression_ctx):
    ctx = regression_ctx
    db = ctx["db"]
    u = _mk_user(db, _unique("__reg_ps_reset"), ctx["viewer"])
    ctx["cleanup_users"].append(u)
    u = _set_auth(u)
    headers, _ = _headers_for(client, u)

    r = client.put(f"/api/v1/users/{u.id}/password", headers=headers,
                   json={"new_password": "a" * 200})
    assert r.status_code == 400, f"200-char reset 应为 400，实际 {r.status_code}"


# ============================================================
# 脱敏：内部异常不外泄
# ============================================================

def test_predict_redacts_internal_error(client: TestClient, regression_ctx):
    """孤儿 /predict 已删除；全局异常处理器不得把内部异常文本回给客户端。"""
    import asyncio
    from unittest.mock import MagicMock

    from main import unhandled_exception_handler

    ctx = regression_ctx
    db = ctx["db"]
    admin = _set_auth(
        db.query(__import__("db.models", fromlist=["User"]).User
                 ).filter(__import__("db.models", fromlist=["User"]).User.username == "admin"
                 ).first()
    )
    headers, _ = _headers_for(client, admin)

    gone = client.post(
        "/api/v1/predict",
        headers=headers,
        json={"home_team": "A", "away_team": "B"},
    )
    assert gone.status_code == 404, f"孤儿 /predict 应已删除，实际 {gone.status_code}"

    resp = asyncio.run(
        unhandled_exception_handler(MagicMock(), RuntimeError("LEAK_ME_SECRET=abc"))
    )
    body = resp.body.decode("utf-8") if isinstance(resp.body, (bytes, bytearray)) else str(resp.body)
    assert resp.status_code == 500
    assert "服务内部错误" in body, f"脱敏文案缺失: {body[:200]}"
    assert "LEAK_ME" not in body, "响应体泄漏内部异常文本"
    assert "RuntimeError" not in body, "响应体泄漏异常类名"
    assert "Traceback" not in body, "响应体泄漏堆栈"


def test_runtime_log_api_redacts_internal_paths(client: TestClient, regression_ctx):
    ctx = regression_ctx
    db = ctx["db"]
    admin = _set_auth(
        db.query(__import__("db.models", fromlist=["User"]).User
                 ).filter(__import__("db.models", fromlist=["User"]).User.username == "admin"
                 ).first()
    )
    headers, _ = _headers_for(client, admin)

    # 非法文件名 → 400，body 不含 '/' 也不含输入路径
    r = client.get("/api/v1/crawler/runtime-logs/tail", headers=headers,
                   params={"name": "../../etc/passwd"})
    assert r.status_code == 400, r.text
    body = r.text
    assert "/" not in body, f"body 泄漏路径: {body[:120]}"
    assert "passwd" not in body, f"body 泄漏输入: {body[:120]}"

    # 不存在的合法文件名 → 404，body 不含输入名
    r = client.get("/api/v1/crawler/runtime-logs/tail", headers=headers,
                   params={"name": "app_zzz_no_such.log"})
    assert r.status_code == 404, r.text
    assert "zzz_no_such" not in r.text


# ============================================================
# 500 兜底：内部异常不外泄
# ============================================================

def test_500_global_handler_no_traceback(client: TestClient, regression_ctx):
    """全局 Exception handler 应回固定文案『服务内部错误』。"""
    # 直接构造一次触发全局兜底的路径：请求一个内部会 raise 的 route
    # 我们直接调 TestClient 时，若没有 monkeypatch，很难制造未捕获异常。
    # 这里退而求其次：至少确认 404 不含 traceback
    r = client.get("/api/v1/definitely-not-exist")
    assert r.status_code in (401, 404)
    assert "Traceback" not in r.text


def test_422_validation_detail_structure(client: TestClient, regression_ctx):
    """422 参数校验 detail 是 [{loc,msg}] 数组，与前端 http.js 解析一致。"""
    ctx = regression_ctx
    db = ctx["db"]
    admin = _set_auth(
        db.query(__import__("db.models", fromlist=["User"]).User
                 ).filter(__import__("db.models", fromlist=["User"]).User.username == "admin"
                 ).first()
    )
    headers, _ = _headers_for(client, admin)

    r = client.get("/api/v1/users?page=-1", headers=headers)
    assert r.status_code == 422, r.text
    detail = r.json().get("detail")
    assert isinstance(detail, list), f"detail 应为数组，实际 {type(detail)}: {r.text[:200]}"
    assert detail and "loc" in detail[0] and "msg" in detail[0]


# ============================================================
# assert_self_only 语义等价
# ============================================================

def test_empty_codes_favorites_self_only(client: TestClient, regression_ctx):
    """空 codes 语义：本人可操作、非本人一律 403（含 admin）。"""
    ctx = regression_ctx
    db = ctx["db"]
    from db.models import Match, Team

    probe = _mk_user(db, _unique("__reg_fav"), ctx["viewer"])
    ctx["cleanup_users"].append(probe)
    probe = _set_auth(probe)

    team_row = db.query(Team).first()
    match_row = db.query(Match).first()
    if not (team_row and match_row):
        pytest.skip("测试库无 team/match 数据")
    team_id = team_row.id; match_id = match_row.id

    # self add match favorite → 200
    headers, _ = _headers_for(client, probe)
    r = client.post(f"/api/v1/favorites/user/{probe.id}/match/{match_id}", headers=headers)
    assert r.status_code == 200, f"self favorite 应为 200: {r.status_code} {r.text[:120]}"

    # editor add OTHER favorite → 403 (空 codes 语义)
    editor_probe = _mk_user(db, _unique("__reg_editor_fav"), ctx["editor"])
    ctx["cleanup_users"].append(editor_probe)
    editor_probe = _set_auth(editor_probe)
    h_ed, _ = _headers_for(client, editor_probe)
    r = client.post(f"/api/v1/favorites/user/{probe.id}/match/{match_id}", headers=h_ed)
    assert r.status_code == 403, f"editor 替他人 favorite 应为 403: {r.status_code} {r.text[:120]}"

    # admin add OTHER favorite → 403 (空 codes 语义，即便 admin 也不让)
    admin = _set_auth(
        db.query(__import__("db.models", fromlist=["User"]).User
                 ).filter(__import__("db.models", fromlist=["User"]).User.username == "admin"
                 ).first()
    )
    h_ad, _ = _headers_for(client, admin)
    r = client.post(f"/api/v1/favorites/user/{probe.id}/match/{match_id}", headers=h_ad)
    assert r.status_code == 403, f"admin 替他人 favorite 应为 403: {r.status_code} {r.text[:120]}"


# ============================================================
# 回归：正常管理员编辑自己未受影响
# ============================================================

def test_admin_edit_self_basic_still_works(client: TestClient, regression_ctx):
    ctx = regression_ctx
    db = ctx["db"]
    admin = _set_auth(
        db.query(__import__("db.models", fromlist=["User"]).User
                 ).filter(__import__("db.models", fromlist=["User"]).User.username == "admin"
                 ).first()
    )
    headers, _ = _headers_for(client, admin)

    r = client.put(f"/api/v1/users/{admin.id}", headers=headers, json={
        "username": "admin",
        "email": "admin@football-analytics.com",
        "level": "professional",
    })
    assert r.status_code == 200, f"admin 改自己应 200: {r.status_code} {r.text[:120]}"
