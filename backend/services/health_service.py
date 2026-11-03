"""健康检查：数据库 / Redis / 调度器状态。"""
from __future__ import annotations

import os
import time
from typing import Any, Dict

from sqlalchemy import text

from db.database import engine


def check_database() -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as e:
        return {
            "status": "error",
            "detail": str(e),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }


from services.redis_client import redis_status


def check_redis() -> Dict[str, Any]:
    from services import job_queue
    from services import prediction_cache

    started = time.perf_counter()
    info = dict(redis_status())
    info["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
    info["prediction_cache"] = prediction_cache.status()
    info["job_queue"] = job_queue.status()
    return info


def check_scheduler() -> Dict[str, Any]:
    from services.scheduler_service import scheduler

    run_scheduler = os.environ.get("RUN_SCHEDULER", "1").lower() not in ("0", "false", "no")
    if not run_scheduler:
        return {"status": "disabled", "running": False, "enabled_tasks": 0}
    tasks = scheduler.get_all_tasks() or {}
    enabled = sum(1 for t in tasks.values() if t.get("is_enabled"))
    return {
        "status": "ok" if scheduler.is_running() else "stopped",
        "running": scheduler.is_running(),
        "enabled_tasks": enabled,
        "total_tasks": len(tasks),
    }


def aggregate_health() -> Dict[str, Any]:
    db = check_database()
    redis = check_redis()
    scheduler = check_scheduler()

    parts = [db["status"], redis["status"]]
    if scheduler.get("status") not in ("disabled",):
        parts.append(scheduler["status"])

    if any(s == "error" for s in parts):
        overall = "unhealthy"
    elif any(s in ("degraded", "stopped") for s in parts):
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "status": overall,
        "service": "football-quant-analysis",
        "version": "5.0.0",
        "checks": {
            "database": db,
            "redis": redis,
            "scheduler": scheduler,
        },
    }
