"""RQ 异步任务函数（在 worker 进程中执行）。"""

from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)


def run_training_job(start_date: str = None, end_date: str = None, lock_token: str = None) -> dict:
    from db.database import SessionLocal
    from db.models import User
    from services.train_lock import train_lock
    from services.training_service import (
        TrainingAborted,
        TrainingUserDisabled,
        training_service,
    )

    uid = train_lock.get_queued_user()
    if uid is not None:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == int(uid)).first()
            if user is None:
                msg = "训练提交者账号已删除"
                logger.warning("RQ training cancelled: %s (user=%s)", msg, uid)
                return {"status": "cancelled", "code": "TRAINING_ABORTED", "message": msg}
            if not user.is_active:
                msg = "训练提交者账号已禁用"
                logger.warning("RQ training cancelled: %s (user=%s)", msg, uid)
                return {
                    "status": "cancelled",
                    "code": "TRAINING_USER_DISABLED",
                    "message": msg,
                }
        finally:
            db.close()

    sd = date.fromisoformat(start_date) if start_date else None
    ed = date.fromisoformat(end_date) if end_date else None
    logger.info("RQ training job started: %s .. %s", start_date, end_date)
    try:
        return training_service.train_all(start_date=sd, end_date=ed, lock_token=lock_token)
    except TrainingUserDisabled as e:
        logger.warning("RQ training cancelled (user disabled): %s", e)
        return {"status": "cancelled", "code": "TRAINING_USER_DISABLED", "message": str(e)}
    except TrainingAborted as e:
        logger.info("RQ training aborted: %s", e)
        return {"status": "cancelled", "code": "TRAINING_ABORTED", "message": str(e)}


def run_crawler_method(method_name: str, kwargs: dict = None) -> dict:
    """手动采集入口：在 worker/线程里调用 CrawlerService 方法，调用方只拿 job_id。"""
    import inspect

    from services.crawler_service import crawler_service

    fn = getattr(crawler_service, method_name, None)
    if fn is None or not callable(fn):
        raise ValueError(f"unknown crawler method: {method_name}")
    clean = dict(kwargs or {})
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        params = {}
    for key, value in list(clean.items()):
        param = params.get(key)
        if param is None or not isinstance(value, str):
            continue
        anno = param.annotation
        args = getattr(anno, "__args__", ())
        if anno is date or date in args:
            clean[key] = date.fromisoformat(value)
    logger.info("Crawler method job started: %s", method_name)
    return {"ok": True, "result": fn(**clean)}


def run_crawler_task(task_id: str, lock_token: str = None) -> dict:
    """同步执行定时任务并等待结束。任务表由本进程注册，不依赖调度线程是否在跑。"""
    from services.scheduled_tasks import invoke_scheduled_task

    logger.info("Crawler job started: %s", task_id)
    return invoke_scheduled_task(task_id, lock_token=lock_token)


def run_p0_pipeline_job(
    stats_limit_per_league: int = 500,
    env_limit: int = 1000,
    train: bool = True,
    enable_environment_schedule: bool = True,
) -> dict:
    from services.crawler_service import crawler_service

    logger.info(
        "RQ P0 job started: stats=%s env=%s train=%s",
        stats_limit_per_league, env_limit, train,
    )
    return crawler_service.run_p0_pipeline(
        stats_limit_per_league=stats_limit_per_league,
        env_limit=env_limit,
        train=train,
        enable_environment_schedule=enable_environment_schedule,
        crawl_type="manual",
    )


def run_stats_backfill_job(limit_per_league: int = 250, prefer_older: bool = True) -> dict:
    from services.crawler_service import crawler_service

    logger.info("RQ stats backfill started: limit=%s prefer_older=%s", limit_per_league, prefer_older)
    return crawler_service.backfill_priority_match_player_stats(
        limit_per_league=limit_per_league,
        crawl_type="manual",
        prefer_older=prefer_older,
    )


def run_enrich_priority_job(include_history: bool = True, seasons_back: int = 2) -> dict:
    from services.crawler_service import crawler_service

    logger.info("RQ enrich priority started: history=%s seasons=%s", include_history, seasons_back)
    results = crawler_service.enrich_priority_leagues(
        include_history=include_history,
        seasons_back=seasons_back,
    )
    return {"results": results, "count": len(results or [])}


def run_uel_catchup_job(
    include_history: bool = True,
    seasons_back: int = 2,
    stats_limit: int = 250,
    train: bool = True,
) -> dict:
    from services.crawler_service import crawler_service

    logger.info(
        "RQ UEL catchup started: history=%s seasons=%s stats=%s train=%s",
        include_history, seasons_back, stats_limit, train,
    )
    return crawler_service.run_uel_catchup(
        include_history=include_history,
        seasons_back=seasons_back,
        stats_limit=stats_limit,
        train=train,
        crawl_type="manual",
    )


def run_extended_catchup_job(
    include_history: bool = True,
    seasons_back: int = 1,
    stats_limit: int = 80,
    train: bool = False,
    league_ids=None,
) -> dict:
    from services.crawler_service import crawler_service

    logger.info(
        "RQ extended catchup started: history=%s seasons=%s stats=%s train=%s leagues=%s",
        include_history, seasons_back, stats_limit, train, league_ids,
    )
    return crawler_service.run_extended_catchup(
        include_history=include_history,
        seasons_back=seasons_back,
        stats_limit=stats_limit,
        train=train,
        crawl_type="manual",
        league_ids=league_ids,
    )
