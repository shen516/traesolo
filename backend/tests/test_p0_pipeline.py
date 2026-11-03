"""P0 补齐流水线：射门补采 → 环境 → 训练。"""
import time


def _reset_p0():
    from services.crawler_service import crawler_service

    crawler_service._ensure_p0_state()
    with crawler_service._p0_lock:
        crawler_service._p0_status = crawler_service._empty_p0_status()
    return crawler_service


def test_p0_pipeline_order(monkeypatch):
    crawler_service = _reset_p0()
    calls = []

    monkeypatch.setattr(crawler_service, "_p0_quality_snapshot", lambda: {
        "totals": {"finished_matches": 10, "matches_with_player_stats": 8},
        "training_lag": {"is_stale": True},
        "model": {"version": "v-test", "weights_has_hyperparams": False},
    })
    monkeypatch.setattr(
        crawler_service,
        "backfill_priority_match_player_stats",
        lambda **kw: calls.append(("stats", kw)) or {
            "status": "success",
            "saved_matches": 3,
            "espn_hits": 3,
            "miss_count": 1,
            "saved_stats": 30,
        },
    )
    monkeypatch.setattr(
        crawler_service,
        "crawl_environment",
        lambda **kw: calls.append(("env", kw)) or {
            "status": "success",
            "scanned": 10,
            "updated": 8,
            "coverage": {"env_finished_pct": 40},
        },
    )
    monkeypatch.setattr(crawler_service, "_save_crawl_log", lambda **kw: None)

    class FakeTrain:
        is_training = False

        def run_train_or_skip(self):
            calls.append(("train", None))
            return {"status": "success", "model_version": "v-test", "total_matches": 10}

    monkeypatch.setattr("services.training_service.training_service", FakeTrain())

    result = crawler_service.run_p0_pipeline(
        stats_limit_per_league=500,
        env_limit=1000,
        train=True,
        enable_environment_schedule=False,
    )
    assert [c[0] for c in calls] == ["stats", "env", "train"]
    assert calls[0][1]["prefer_older"] is True
    assert calls[0][1]["limit_per_league"] == 500
    assert calls[1][1]["limit"] == 1000
    assert calls[1][1]["only_missing"] is True
    assert result["status"] == "success"
    assert result["stats"]["saved_matches"] == 3
    st = crawler_service.get_p0_status()
    assert st["running"] is False
    assert st["phase"] == "done"
    assert st["status"] == "success"


def test_p0_rejects_concurrent(monkeypatch):
    crawler_service = _reset_p0()

    def slow_stats(**_kw):
        time.sleep(0.35)
        return {"status": "success", "saved_matches": 0, "espn_hits": 0, "miss_count": 0}

    monkeypatch.setattr(crawler_service, "_p0_quality_snapshot", lambda: {})
    monkeypatch.setattr(crawler_service, "backfill_priority_match_player_stats", slow_stats)
    monkeypatch.setattr(crawler_service, "crawl_environment", lambda **_kw: {"status": "success"})
    monkeypatch.setattr(crawler_service, "_save_crawl_log", lambda **_kw: None)

    first = crawler_service.start_p0_async(train=False, enable_environment_schedule=False)
    assert first["status"] == "started"
    second = crawler_service.start_p0_async(train=False, enable_environment_schedule=False)
    assert second["status"] == "error"
    assert second.get("running") is True
    assert "正在执行" in (second.get("message") or "")
    deadline = time.time() + 3
    while crawler_service.get_p0_status().get("running") and time.time() < deadline:
        time.sleep(0.05)
    assert crawler_service.get_p0_status().get("running") is False
