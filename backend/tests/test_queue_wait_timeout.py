"""排队等待超时与队列健康探针。

背景：RQ worker 未消费队列时，排队心跳曾用执行超时（7200s）续期，
导致定时任务锁死 2 小时、tick 反复 skip。修复点：
1. enqueue_crawler 的排队心跳 max_seconds 用 queue_wait_timeout（独立配置）；
2. 到点 busy 且 phase=queued 时日志升级 WARNING；
3. /crawler/status 返回 queue 健康探针；
4. get_all_tasks 暴露 phase / status_age_seconds。
"""
import time

from services.task_run_lock import task_run_lock


def _drop(task_id: str):
    token = task_run_lock.current_token(task_id)
    if token:
        task_run_lock.release(task_id, token)


def test_queue_wait_timeout_config(monkeypatch):
    from services import job_queue

    # 默认值 1200，且不超过执行超时
    monkeypatch.setattr(
        job_queue, "load_redis_config",
        lambda: {"job_queue": {"enabled": False}},
    )
    assert job_queue._queue_wait_timeout() == 1200

    # 显式配置生效
    monkeypatch.setattr(
        job_queue, "load_redis_config",
        lambda: {"job_queue": {"enabled": False, "queue_wait_timeout": 300, "default_timeout": 7200}},
    )
    assert job_queue._queue_wait_timeout() == 300

    # 大于执行超时时被压到执行超时
    monkeypatch.setattr(
        job_queue, "load_redis_config",
        lambda: {"job_queue": {"enabled": False, "queue_wait_timeout": 99999, "default_timeout": 600}},
    )
    assert job_queue._queue_wait_timeout() == 600


def test_enqueue_crawler_heartbeat_uses_queue_wait(monkeypatch):
    """排队心跳 max_seconds 必须来自 queue_wait_timeout，而非执行超时。"""
    from services import job_queue

    monkeypatch.setattr(
        job_queue, "load_redis_config",
        lambda: {"job_queue": {"enabled": True, "queue_wait_timeout": 777, "default_timeout": 7200}},
    )
    monkeypatch.setattr(job_queue, "_queue_enabled", lambda: True)
    captured = {}
    real_heartbeat = task_run_lock.start_heartbeat

    def spy(task_id, token, **kwargs):
        captured.update(kwargs)
        return real_heartbeat(task_id, token, **kwargs)

    monkeypatch.setattr(task_run_lock, "start_heartbeat", spy)
    monkeypatch.setattr(
        "services.task_run_lock.task_run_lock.start_heartbeat", spy, raising=False,
    )

    monkeypatch.setattr(
        "services.job_queue._get_queue",
        lambda name="crawl": _FakeQueue(),
    )
    out = job_queue.enqueue_crawler("zz_wait_heartbeat", lock_token="tok-1")
    assert out["mode"] == "rq"
    assert captured["max_seconds"] == 777
    assert captured["stop_when_phase_not"] == "queued"


class _FakeQueue:
    def enqueue(self, *args, **kwargs):
        class _J:
            id = "fake-job"
        return _J()


def test_queued_lock_expires_after_wait_timeout(monkeypatch):
    """排队锁在 max_seconds 后应被标 failed 并释放（内存锁路径）。"""
    from services.task_run_lock import lock_settings, task_run_lock as lock

    task_id = "zz_wait_expire"

    # 缩短心跳间隔，让 deadline 分支尽快触发（interval 原为 ttl//3=40s，等不起）
    monkeypatch.setattr(
        "services.task_run_lock.lock_settings",
        lambda: {"ttl_seconds": 30, "heartbeat_seconds": 1},
    )
    token = lock.acquire(task_id)
    assert token
    try:
        lock.write_status(task_id, {
            "phase": "queued",
            "in_progress": True,
            "message": "已入队",
        })
        # max_seconds=2：两个心跳周期后 deadline 分支应释放锁并写 failed
        lock.start_heartbeat(task_id, token, stop_when_phase_not="queued", max_seconds=2)
        deadline_at = time.time() + 8
        released = False
        while time.time() < deadline_at:
            if not lock.is_locked(task_id):
                released = True
                break
            time.sleep(0.1)
        assert released, "排队心跳到期后锁应释放"
    finally:
        _drop(task_id)


def test_busy_skip_logs_warning_for_stale_queued(monkeypatch):
    """busy 且 phase=queued 时应打 WARNING；phase=running 仍是 INFO。"""
    from services.scheduler_service import scheduler

    task_id = "zz_busy_log"
    scheduler.register_task(task_id, lambda: None, 60, name="busy-log")
    try:
        token = task_run_lock.acquire(task_id)
        assert token

        # queued 停滞 → WARNING
        task_run_lock.write_status(task_id, {
            "phase": "queued", "in_progress": True, "message": "已入队",
        })
        warnings = []
        monkeypatch.setattr(
            "services.scheduler_service.logger.warning",
            lambda msg, *a, **k: warnings.append(msg),
        )
        scheduler._log_busy_skip(task_id)
        assert any("worker" in w or "queued" in w for w in warnings)

        # running → 不打 WARNING（INFO 路径）
        warnings.clear()
        task_run_lock.write_status(task_id, {
            "phase": "running", "in_progress": True, "message": "执行中",
        })
        scheduler._log_busy_skip(task_id)
        assert warnings == []
    finally:
        _drop(task_id)
        scheduler._registry.pop(task_id, None)


def test_get_all_tasks_exposes_phase(monkeypatch):
    from services.scheduler_service import scheduler

    task_id = "zz_phase_expose"
    scheduler.register_task(task_id, lambda: None, 60, name="phase")
    try:
        token = task_run_lock.acquire(task_id)
        assert token
        task_run_lock.write_status(task_id, {
            "phase": "queued", "in_progress": True, "message": "已入队",
        })
        tasks = scheduler.get_all_tasks()
        assert tasks[task_id]["in_progress"] is True
        assert tasks[task_id]["phase"] == "queued"
        assert "status_age_seconds" in tasks[task_id]
    finally:
        _drop(task_id)
        scheduler._registry.pop(task_id, None)


def test_crawler_status_has_queue_probe(client, admin_token):
    """/crawler/status 应包含 queue 探针；线程模式下 healthy=True。"""
    resp = client.get(
        "/api/v1/crawler/status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["queue"]["backend"] == "thread"
    assert body["queue"]["healthy"] is True
