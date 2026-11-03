"""健康检查接口测试。"""


def test_liveness(client):
    res = client.get("/api/v1/health/live")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_health_ready(client):
    res = client.get("/api/v1/health/ready")
    assert res.status_code in (200, 503)
    body = res.json()
    assert "checks" in body
    assert body["checks"]["database"]["status"] == "ok"


def test_health_aggregate(client):
    res = client.get("/api/v1/health")
    assert res.status_code in (200, 503)
    assert res.json()["service"] == "football-quant-analysis"
