"""第三阶段：预测缓存 / 指标 / 监控测试。"""


def test_prediction_cache_roundtrip():
    from services import prediction_cache

    prediction_cache.invalidate_match("test-match-1")
    payload = {"match_id": "test-match-1", "home_win_prob": 0.5}
    prediction_cache.set("test-match-1", "v-test", payload, ttl=120)
    got = prediction_cache.get("test-match-1", "v-test")
    assert got is not None
    assert got["home_win_prob"] == 0.5
    prediction_cache.invalidate_match("test-match-1")


def test_metrics_endpoint(client):
    res = client.get("/metrics")
    assert res.status_code == 200
    assert b"traesolo_http_requests_total" in res.content


def test_model_monitor_requires_auth(client):
    res = client.get("/api/v1/model/monitor/drift")
    assert res.status_code == 401


def test_model_monitor_admin(client, auth_headers):
    res = client.get("/api/v1/model/monitor/drift", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert "status" in body
    assert "recent_days" in body


def test_job_queue_status():
    from services import job_queue
    st = job_queue.status()
    assert "enabled" in st
    assert "backend" in st
