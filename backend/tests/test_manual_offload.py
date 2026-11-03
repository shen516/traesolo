"""手动采集入队立即返回；批量预测在线程池函数里并受整批超时约束。"""
import inspect
import sys
import threading
import time
from datetime import date


def test_manual_enqueue_returns_while_body_runs(monkeypatch):
    monkeypatch.setenv("TRAESOLO_JOB_QUEUE_DISABLED", "1")
    from services import job_queue

    crawler = sys.modules["services.crawler_service"].crawler_service

    started = threading.Event()
    release = threading.Event()

    def slow(limit=None, only_missing=True, finished_only=False, crawl_type="manual", **kwargs):
        started.set()
        assert release.wait(3)
        return {"scanned": 2, "updated": 1}

    monkeypatch.setattr(crawler, "crawl_environment", slow)
    out = job_queue.enqueue_crawler_method(
        "crawl_environment",
        {"limit": 1, "only_missing": True},
        kind="crawl_environment",
    )
    assert out["job_id"]
    assert out["status"] == "started"
    assert started.wait(2)
    assert job_queue.get_job_status(out["job_id"])["status"] == "started"
    release.set()
    status = "started"
    result = None
    for _ in range(40):
        snap = job_queue.get_job_status(out["job_id"])
        status = snap["status"]
        result = snap.get("result")
        if status in ("finished", "failed"):
            break
        time.sleep(0.05)
    assert status == "finished"
    assert result["ok"] is True
    assert result["result"]["scanned"] == 2


def test_crawler_method_coerces_date(monkeypatch):
    from services.jobs.tasks import run_crawler_method

    crawler = sys.modules["services.crawler_service"].crawler_service

    seen = {}

    def fake(days_back: int = 7, match_date: date = None, crawl_type: str = "manual"):
        seen["match_date"] = match_date
        seen["crawl_type"] = crawl_type
        return {"saved": 0}

    monkeypatch.setattr(crawler, "crawl_jingcai_scores", fake)
    out = run_crawler_method(
        "crawl_jingcai_scores",
        {"days_back": 3, "match_date": "2026-10-01", "crawl_type": "manual"},
    )
    assert out["ok"] is True
    assert seen["match_date"] == date(2026, 10, 1)
    assert seen["crawl_type"] == "manual"


def test_batch_and_predict_are_sync_def():
    from api.matches import get_match_prediction
    from api.predictions import batch_calculate, calculate_prediction, recalculate_predictions
    from main import predict

    for fn in (
        batch_calculate,
        recalculate_predictions,
        calculate_prediction,
        get_match_prediction,
        predict,
    ):
        assert not inspect.iscoroutinefunction(fn)


def test_batch_stops_when_deadline_already_passed(monkeypatch):
    import api.predictions as pred

    monkeypatch.setattr(pred, "_BATCH_DEADLINE_SECONDS", 0)
    called = {"n": 0}

    def boom(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("predict should not run after deadline")

    monkeypatch.setattr(pred, "_run_predict_and_save", boom)
    res = pred.batch_calculate(
        pred.BatchPredictRequest(match_ids=["m1", "m2"], recalculate=True),
        db=object(),
        entitlements=set(),
    )
    assert called["n"] == 0
    assert res["calculated"] == 0
    assert [item["code"] for item in res["failed"]] == ["TIMEOUT", "TIMEOUT"]
