"""RQ 任务队列封装；Redis 不可用时回退线程执行。"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from typing import Any, Dict, Optional

from services.redis_client import get_redis_client, load_redis_config

logger = logging.getLogger(__name__)

_mem_jobs: Dict[str, dict] = {}


def _queue_enabled() -> bool:
    cfg = load_redis_config()
    jq = dict(cfg.get("job_queue") or {})
    if os.environ.get("TRAESOLO_JOB_QUEUE_DISABLED", "").lower() in ("1", "true", "yes"):
        return False
    if os.environ.get("TRAESOLO_JOB_QUEUE_ENABLED", "").lower() in ("1", "true", "yes"):
        return get_redis_client() is not None
    return bool(jq.get("enabled", True)) and get_redis_client() is not None


def _timeout() -> int:
    cfg = load_redis_config()
    jq = dict(cfg.get("job_queue") or {})
    return int(jq.get("default_timeout") or 7200)


def _queue_wait_timeout() -> int:
    """排队等待超时（秒）：等待 worker 接手的上限，独立于任务执行超时。

    worker 未消费队列时，排队心跳超过该时长即判 failed 并释放锁，
    避免用执行超时（默认 7200s）把任务锁死太久。上限不超过执行超时。
    """
    cfg = load_redis_config()
    jq = dict(cfg.get("job_queue") or {})
    wait = int(jq.get("queue_wait_timeout") or 1200)
    return max(1, min(wait, _timeout()))


def _get_queue(name: str = "default"):
    from rq import Queue

    conn = get_redis_client()
    if conn is None:
        return None
    return Queue(name, connection=conn, default_timeout=_timeout())


def enqueue_training(start_date=None, end_date=None, user_id: int = None) -> dict:
    sd = start_date.isoformat() if start_date else None
    ed = end_date.isoformat() if end_date else None
    if _queue_enabled():
        from services.jobs.tasks import run_training_job
        from services.train_lock import train_lock

        token = train_lock.acquire()
        if not token:
            return {"status": "error", "code": "TRAIN_BUSY", "message": "训练正在进行中"}
        train_lock.write_status({
            "is_training": True,
            "progress": 0,
            "message": "训练已入队，等待 worker 执行",
            "current_record_id": None,
            "phase": "queued",
        })
        if user_id:
            # 训练循环里靠这个校验提交者账号是否仍有效（被禁用即中止）
            train_lock.set_queued_user(int(user_id))
        train_lock.start_heartbeat(
            token,
            stop_when_phase_not="queued",
            max_seconds=_timeout(),
        )
        try:
            q = _get_queue("train")
            job = q.enqueue(run_training_job, sd, ed, token, job_timeout=_timeout())
        except Exception:
            train_lock.write_status({
                "is_training": False,
                "progress": 0,
                "message": "训练入队失败",
                "current_record_id": None,
                "phase": "failed",
            })
            train_lock.release(token)
            raise
        return {"mode": "rq", "job_id": job.id, "status": "queued", "queue": "train"}
    # 线程模式：API 进程直接跑训练，同样要记录提交者供循环内校验
    if user_id:
        from services.train_lock import train_lock
        train_lock.set_queued_user(int(user_id))
    return _enqueue_thread(
        "train",
        lambda: __import__("services.jobs.tasks", fromlist=["run_training_job"]).run_training_job(sd, ed),
    )


def enqueue_crawler_method(method_name: str, kwargs: dict = None, kind: str = "manual") -> dict:
    """手动采集入队。RQ 不可用时用守护线程，HTTP 调用方不等待采集结束。"""
    from services.jobs.tasks import run_crawler_method

    payload = dict(kwargs or {})
    if _queue_enabled():
        q = _get_queue("crawl")
        if q is not None:
            job = q.enqueue(
                run_crawler_method,
                method_name,
                payload,
                job_timeout=_timeout(),
                result_ttl=86400,
                failure_ttl=86400,
            )
            return {"mode": "rq", "job_id": job.id, "status": "queued", "queue": "crawl", "kind": kind}
    return _enqueue_thread(
        kind,
        lambda: run_crawler_method(method_name, payload),
        {"kind": kind, "method": method_name},
    )


def enqueue_crawler(task_id: str, lock_token: str = None) -> dict:
    if _queue_enabled():
        from services.jobs.tasks import run_crawler_task
        from services.task_run_lock import task_run_lock

        if lock_token:
            task_run_lock.start_heartbeat(
                task_id,
                lock_token,
                stop_when_phase_not="queued",
                max_seconds=_queue_wait_timeout(),
            )
        try:
            q = _get_queue("crawl")
            job = q.enqueue(run_crawler_task, task_id, lock_token, job_timeout=_timeout())
        except Exception:
            if lock_token:
                task_run_lock.stop_heartbeat(task_id)
            raise
        return {"mode": "rq", "job_id": job.id, "status": "queued", "queue": "crawl", "task_id": task_id}
    return _enqueue_thread(
        "crawl",
        lambda: __import__("services.jobs.tasks", fromlist=["run_crawler_task"]).run_crawler_task(
            task_id, lock_token
        ),
        meta={"task_id": task_id},
    )


def enqueue_p0(
    stats_limit_per_league: int = 500,
    env_limit: int = 1000,
    train: bool = True,
    enable_environment_schedule: bool = True,
) -> dict:
    """长耗时 P0 流水线入队（RQ 或线程）。"""
    args = (int(stats_limit_per_league), int(env_limit), bool(train), bool(enable_environment_schedule))
    if _queue_enabled():
        from services.jobs.tasks import run_p0_pipeline_job

        q = _get_queue("crawl")
        job = q.enqueue(run_p0_pipeline_job, *args, job_timeout=_timeout())
        return {"mode": "rq", "job_id": job.id, "status": "queued", "queue": "crawl", "kind": "p0"}
    return _enqueue_thread(
        "p0",
        lambda: __import__("services.jobs.tasks", fromlist=["run_p0_pipeline_job"]).run_p0_pipeline_job(*args),
        meta={"kind": "p0"},
    )


def enqueue_stats_backfill(limit_per_league: int = 250, prefer_older: bool = True) -> dict:
    if _queue_enabled():
        from services.jobs.tasks import run_stats_backfill_job

        q = _get_queue("crawl")
        job = q.enqueue(
            run_stats_backfill_job,
            int(limit_per_league),
            bool(prefer_older),
            job_timeout=_timeout(),
        )
        return {"mode": "rq", "job_id": job.id, "status": "queued", "queue": "crawl", "kind": "stats_backfill"}
    return _enqueue_thread(
        "stats_backfill",
        lambda: __import__("services.jobs.tasks", fromlist=["run_stats_backfill_job"]).run_stats_backfill_job(
            int(limit_per_league), bool(prefer_older)
        ),
        meta={"kind": "stats_backfill"},
    )


def enqueue_enrich_priority(include_history: bool = True, seasons_back: int = 2) -> dict:
    if _queue_enabled():
        from services.jobs.tasks import run_enrich_priority_job

        q = _get_queue("crawl")
        job = q.enqueue(
            run_enrich_priority_job,
            bool(include_history),
            int(seasons_back),
            job_timeout=_timeout(),
        )
        return {"mode": "rq", "job_id": job.id, "status": "queued", "queue": "crawl", "kind": "enrich"}
    return _enqueue_thread(
        "enrich",
        lambda: __import__("services.jobs.tasks", fromlist=["run_enrich_priority_job"]).run_enrich_priority_job(
            bool(include_history), int(seasons_back)
        ),
        meta={"kind": "enrich"},
    )


def enqueue_uel_catchup(
    include_history: bool = True,
    seasons_back: int = 2,
    stats_limit: int = 250,
    train: bool = True,
) -> dict:
    args = (bool(include_history), int(seasons_back), int(stats_limit), bool(train))
    if _queue_enabled():
        from services.jobs.tasks import run_uel_catchup_job

        q = _get_queue("crawl")
        job = q.enqueue(run_uel_catchup_job, *args, job_timeout=_timeout())
        return {"mode": "rq", "job_id": job.id, "status": "queued", "queue": "crawl", "kind": "uel"}
    return _enqueue_thread(
        "uel",
        lambda: __import__("services.jobs.tasks", fromlist=["run_uel_catchup_job"]).run_uel_catchup_job(*args),
        meta={"kind": "uel"},
    )


def enqueue_extended_catchup(
    include_history: bool = True,
    seasons_back: int = 1,
    stats_limit: int = 80,
    train: bool = False,
    league_ids: Optional[list] = None,
) -> dict:
    lids = list(league_ids) if league_ids else None
    args = (bool(include_history), int(seasons_back), int(stats_limit), bool(train), lids)
    if _queue_enabled():
        from services.jobs.tasks import run_extended_catchup_job

        q = _get_queue("crawl")
        job = q.enqueue(run_extended_catchup_job, *args, job_timeout=_timeout())
        return {"mode": "rq", "job_id": job.id, "status": "queued", "queue": "crawl", "kind": "extended"}
    return _enqueue_thread(
        "extended",
        lambda: __import__("services.jobs.tasks", fromlist=["run_extended_catchup_job"]).run_extended_catchup_job(
            *args
        ),
        meta={"kind": "extended"},
    )


def get_job_status(job_id: str) -> dict:
    if _queue_enabled():
        try:
            from rq.job import Job

            job = Job.fetch(job_id, connection=get_redis_client())
            return {
                "job_id": job_id,
                "mode": "rq",
                "status": job.get_status(),
                "result": job.result if job.is_finished else None,
                # exc_info 是 RQ 存的 traceback 文本，含堆栈/内部类名，不回给客户端；
                # 完整错误在服务端日志里，前端如需诊断走 /logs。
                "exc_info": None,
            }
        except Exception as e:
            logger.warning("get_job_status(%s) failed: %s", job_id, e)
            return {"job_id": job_id, "mode": "rq", "status": "unknown",
                    "detail": "作业状态查询失败"}
    mem = _mem_jobs.get(job_id)
    if not mem:
        return {"job_id": job_id, "mode": "thread", "status": "unknown"}
    return mem


def _enqueue_thread(kind: str, func, meta: Optional[dict] = None) -> dict:
    job_id = f"local-{kind}-{uuid.uuid4().hex[:12]}"
    _mem_jobs[job_id] = {"job_id": job_id, "mode": "thread", "status": "started", **(meta or {})}

    def _runner():
        try:
            result = func()
            _mem_jobs[job_id]["status"] = "finished"
            _mem_jobs[job_id]["result"] = result
        except Exception as e:
            logger.exception("Thread job %s failed: %s", job_id, e)
            _mem_jobs[job_id]["status"] = "failed"
            _mem_jobs[job_id]["exc_info"] = str(e)

    threading.Thread(target=_runner, name=f"traesolo-job-{kind}", daemon=True).start()
    return {"mode": "thread", "job_id": job_id, "status": "started"}


def status() -> Dict[str, Any]:
    return {
        "enabled": _queue_enabled(),
        "backend": "rq" if _queue_enabled() else "thread",
        "timeout_seconds": _timeout(),
    }
