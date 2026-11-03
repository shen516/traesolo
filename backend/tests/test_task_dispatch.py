"""调度只入队，任务体在执行端同步跑完，同一 task_id 不叠跑。"""

from services.scheduler_service import scheduler
from services.scheduled_tasks import invoke_scheduled_task
from services.task_run_lock import task_run_lock


def _drop(task_id: str):
    token = task_run_lock.current_token(task_id)
    if token:
        task_run_lock.release(task_id, token)
    scheduler._registry.pop(task_id, None)


def test_dispatch_enqueues_without_running_body(monkeypatch):
    task_id = "zz_dispatch_enqueue"
    ran = []
    scheduler.register_task(task_id, lambda: ran.append("body"), 60, name="dispatch")
    monkeypatch.setattr(
        "services.job_queue.enqueue_crawler",
        lambda task_id, lock_token=None: {
            "status": "queued",
            "mode": "test",
            "job_id": "job-1",
            "task_id": task_id,
        },
    )
    try:
        assert scheduler.dispatch_task(task_id) == "queued"
        assert ran == []
        assert task_run_lock.is_locked(task_id) is True
        tasks = scheduler.get_all_tasks()
        assert tasks[task_id]["in_progress"] is True
        assert scheduler.dispatch_task(task_id) == "busy"
    finally:
        _drop(task_id)


def test_schedule_wrapper_returns_without_inline_work(monkeypatch):
    task_id = "zz_wrap_only"
    scheduler.register_task(task_id, lambda: None, 60, name="wrap")
    monkeypatch.setattr(
        "services.job_queue.enqueue_crawler",
        lambda task_id, lock_token=None: {"status": "queued", "mode": "test", "job_id": "job-2"},
    )
    try:
        scheduler._wrap_task(task_id, lambda: (_ for _ in ()).throw(AssertionError("inline")))()
        assert task_run_lock.is_locked(task_id) is True
    finally:
        _drop(task_id)


def test_invoke_runs_until_complete_and_releases_lock():
    task_id = "zz_invoke_done"
    seen = []

    def body():
        seen.append(task_run_lock.is_locked(task_id))
        return {"status": "success", "saved": 4}

    scheduler.register_task(task_id, body, 60, name="invoke")
    try:
        out = invoke_scheduled_task(task_id)
        assert out["success"] is True
        assert out["result"]["saved"] == 4
        assert seen == [True]
        assert task_run_lock.is_locked(task_id) is False
    finally:
        _drop(task_id)


def test_invoke_skips_when_lock_held_and_failure_releases():
    busy_id = "zz_invoke_busy"
    boom_id = "zz_invoke_boom"
    scheduler.register_task(busy_id, lambda: {"status": "success"}, 60, name="busy")
    scheduler.register_task(boom_id, lambda: (_ for _ in ()).throw(RuntimeError("boom")), 60, name="boom")
    token = task_run_lock.acquire(busy_id)
    try:
        skipped = invoke_scheduled_task(busy_id)
        assert skipped["skipped"] is True
        assert task_run_lock.current_token(busy_id) == token
        failed = invoke_scheduled_task(boom_id)
        assert failed["success"] is False
        assert "boom" in failed["error"]
        assert task_run_lock.is_locked(boom_id) is False
    finally:
        task_run_lock.release(busy_id, token)
        _drop(busy_id)
        _drop(boom_id)


def test_enqueue_error_releases_lock(monkeypatch):
    task_id = "zz_enqueue_fail"
    scheduler.register_task(task_id, lambda: None, 60, name="fail")

    def _fail(task_id, lock_token=None):
        raise RuntimeError("queue down")

    monkeypatch.setattr("services.job_queue.enqueue_crawler", _fail)
    try:
        assert scheduler.dispatch_task(task_id) == "error"
        assert task_run_lock.is_locked(task_id) is False
        assert scheduler.dispatch_task("zz_not_registered") == "missing"
    finally:
        _drop(task_id)
