"""认证与 RBAC 集成测试。"""


def test_captcha_public(client):
    res = client.get("/api/v1/auth/captcha")
    assert res.status_code == 200
    assert "captcha_id" in res.json()


def test_protected_route_requires_token(client):
    res = client.get("/api/v1/matches/upcoming")
    assert res.status_code == 401


def test_admin_can_list_matches(client, auth_headers):
    res = client.get("/api/v1/matches/upcoming", headers=auth_headers)
    assert res.status_code == 200
    assert "matches" in res.json()


def test_admin_can_access_crawler(client, auth_headers):
    res = client.get("/api/v1/crawler/status", headers=auth_headers)
    assert res.status_code == 200


def test_users_login_removed(client):
    """旧 /users/login 已下线；未带 Token 时由鉴权中间件返回 401。"""
    res = client.post("/api/v1/users/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 401
    assert res.json().get("token") != "mock-jwt-token"


def test_ensemble_registry_singleton():
    from services.ensemble_registry import get_ensemble

    a = get_ensemble()
    b = get_ensemble()
    assert a is b
