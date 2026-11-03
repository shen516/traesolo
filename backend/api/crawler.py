"""采集与定时任务API"""
import logging
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from db.database import get_db
from db.models import CrawlLog
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from datetime import date, datetime, timedelta
from services.scheduler_service import scheduler
from services.crawler_service import crawler_service
from services.crud_service import CrawlLogService
from services.app_log_service import (
    list_runtime_logs,
    read_log_tail,
    resolve_log_path,
    get_current_log_path,
)
from api.authz import RequireScheduleManage

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[RequireScheduleManage])


def _dispatch_scheduled(task_id: str, started_message: str):
    """入队一次定时任务。正在执行返回 409，未注册或入队失败返回 404。"""
    outcome = scheduler.dispatch_task(task_id)
    if outcome == "busy":
        raise HTTPException(status_code=409, detail="任务正在执行，本次未重复触发")
    if outcome != "queued":
        detail = "任务未注册" if outcome == "missing" else "任务入队失败"
        raise HTTPException(status_code=404, detail=detail)
    return {"message": started_message}


def _enqueue_manual(message: str, method: str, **kwargs) -> dict:
    """手动采集入队后立即返回，避免同步 HTTP/写库占住 API 事件循环。"""
    from services import job_queue

    clean = {}
    for key, value in kwargs.items():
        if value is None:
            continue
        if isinstance(value, date):
            value = value.isoformat()
        clean[key] = value
    queued = job_queue.enqueue_crawler_method(method, clean, kind=method)
    return {"message": message, "async": True, **queued}


class TeamAliasIn(BaseModel):
    alias: str = Field(..., min_length=1, max_length=120)
    team_id: str = Field(..., min_length=1, max_length=20)
    espn_abbr: Optional[str] = Field(None, max_length=20)
    league_id: Optional[str] = Field(None, max_length=20)
    status: str = "confirmed"
    note: Optional[str] = Field(None, max_length=255)


# ===== 定时任务管理 =====

@router.get("/status")
async def get_crawler_status():
    """获取调度器和所有定时任务状态

    任务状态来源：
    - is_enabled / last_run_at / interval_minutes：来自数据库 scheduled_task_status 表（持久化）
    - running：任务已挂进调度循环（不等于正在采集）
    - in_progress：该 task_id 的执行锁被持有，任务体正在跑
    - phase / status_age_seconds：执行锁状态与该状态已持续秒数（queued 停滞过久说明 worker 未消费队列）
    - next_run：来自内存中 schedule 库的下次到点时间
    - queue：RQ 队列健康探针（队列模式才有；worker 数为 0 且有积压时 healthy=false）
    """
    tasks = scheduler.get_all_tasks()
    return {
        "scheduler_running": scheduler.is_running(),
        "queue": _queue_health(),
        "tasks": tasks
    }


def _queue_health() -> dict:
    """RQ 队列健康探针：worker 是否在消费 crawl 队列。

    Redis / RQ 不可用（线程模式）时返回 backend=thread 且 healthy=True。
    """
    from services.job_queue import _queue_enabled

    if not _queue_enabled():
        return {"backend": "thread", "healthy": True, "detail": "线程模式（无 RQ 队列）"}
    try:
        from services.redis_client import get_redis_client
        from services.job_queue import _get_queue

        client = get_redis_client()
        queue = _get_queue("crawl")
        if client is None or queue is None:
            return {"backend": "rq", "healthy": True, "detail": "队列暂不可查"}
        pending = queue.count
        workers = len(queue.worker_registry.all())
        oldest = queue.job_ids[0] if pending else None
        healthy = workers > 0 or pending == 0
        health = {
            "backend": "rq",
            "queue": "crawl",
            "pending_jobs": pending,
            "workers": workers,
            "healthy": healthy,
        }
        if oldest:
            # 最老积压作业的等待时长，用于判断积压是否异常
            from rq.job import Job

            try:
                job = Job.fetch(oldest, connection=client)
                enqueued = getattr(job, "enqueued_at", None)
                if enqueued is not None:
                    from datetime import datetime, timezone

                    health["oldest_wait_seconds"] = max(
                        0, int((datetime.now(timezone.utc) - enqueued).total_seconds())
                    )
            except Exception:
                pass
        if not healthy:
            from logging import WARNING as _WARN
            from services.app_log_service import log_event

            log_event(
                _WARN,
                "RQ crawl 队列积压 %s 个作业且无 worker 消费，定时任务将排队超时",
                event="queue_unhealthy",
                queue="crawl",
                pending=pending,
                workers=workers,
            )
        return health
    except Exception as e:
        # 探针失败不影响状态接口
        return {"backend": "rq", "healthy": True, "detail": f"探针查询失败: {e}"}


@router.post("/schedule/enable")
async def enable_schedule(interval_minutes: int = Query(60, ge=5, description="采集间隔（分钟），默认60分钟")):
    """启用赛事定时采集"""
    scheduler.add_interval_task("match_crawl", crawler_service.crawl_all_leagues, interval_minutes)
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"赛事定时采集已启用，每{interval_minutes}分钟执行一次"}


@router.post("/schedule/disable")
async def disable_schedule():
    """禁用赛事定时采集"""
    scheduler.remove_task("match_crawl")
    return {"message": "赛事定时采集已禁用"}


@router.post("/schedule/run-now")
async def run_schedule_now():
    """手动触发赛事定时采集任务"""
    return _dispatch_scheduled("match_crawl", "手动触发赛事采集成功，任务已入队")


@router.post("/players/schedule/enable")
async def enable_player_schedule(interval_minutes: int = Query(60, ge=5, description="已废弃")):
    """已退役：player_crawl 不再注册。阵容请手动/enrich；赛季统计用 players/stats 定时任务。"""
    raise HTTPException(
        status_code=410,
        detail="player_crawl 已退役；阵容请用 /players/squad/schedule 或手动 /players/run、联赛 enrich",
    )


@router.post("/players/schedule/disable")
async def disable_player_schedule():
    """已退役：清理可能残留的 player_crawl 调度状态。"""
    scheduler.remove_task("player_crawl")
    return {"message": "player_crawl 已退役；若有残留调度已清除"}


@router.post("/players/schedule/run-now")
async def run_player_schedule_now():
    """已退役：不再支持 player_crawl 定时触发。"""
    raise HTTPException(
        status_code=410,
        detail="player_crawl 已退役；请用 POST /crawler/players/squad/schedule/run-now 或 /players/run",
    )


@router.post("/players/use-real")
async def use_real_player_crawler(enable: bool = Query(True, description="已废弃：仅真实爬虫")):
    """已移除模拟球员爬虫；始终使用真实源。"""
    if not enable:
        raise HTTPException(status_code=400, detail="模拟球员爬虫已移除，无法关闭真实采集")
    crawler_service.use_real_player_crawler(True)
    return {"message": "已使用真实球员爬虫（模拟模式已移除）"}


# ===== 手动采集 =====

@router.post("/run")
async def run_crawl(league_id: str = Query(None, description="联赛ID，不指定则采集所有联赛")):
    """手动触发数据采集（入队后立即返回，结果见 /crawler/jobs/{job_id}）"""
    if league_id:
        return _enqueue_manual(
            "联赛数据采集已入队",
            "crawl_league",
            league_id=league_id,
            crawl_type="manual",
        )
    return _enqueue_manual("所有联赛数据采集已入队", "crawl_all_leagues", crawl_type="manual")


@router.post("/cleanup-dirty-teams")
async def cleanup_dirty_teams():
    """清理竞彩脏球队 ID（中文/数字前缀）及其赛事，合并到规范 ID。"""
    return _enqueue_manual("脏球队/脏赛事清理已入队", "cleanup_dirty_teams_and_matches")


@router.post("/players/run")
async def run_player_crawl(
    league_id: str = Query(None, description="联赛ID，不指定则采集所有联赛"),
    team_id: str = Query(None, description="球队ID，指定则只采集该球队球员")
):
    """手动触发球员数据采集（入队后立即返回）"""
    if team_id:
        return _enqueue_manual("球员数据采集已入队", "crawl_players", team_id=team_id)
    if league_id:
        return _enqueue_manual("球员数据采集已入队", "crawl_players", league_id=league_id)
    return _enqueue_manual("球员数据采集已入队", "crawl_all_players", crawl_type="manual")


@router.post("/live500/run")
async def run_live500_crawl():
    """手动触发 Live500 实时数据采集（入队后立即返回）"""
    return _enqueue_manual("Live500实时数据采集已入队", "crawl_live500", crawl_type="manual")


@router.post("/live500/schedule/enable")
async def enable_live500_schedule(interval_minutes: int = Query(30, ge=5, description="采集间隔（分钟），默认30分钟")):
    """启用 Live500 定时采集"""
    scheduler.add_interval_task("live500_crawl", crawler_service.crawl_live500, interval_minutes)
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"Live500定时采集已启用，每{interval_minutes}分钟执行一次"}


@router.post("/live500/schedule/disable")
async def disable_live500_schedule():
    """禁用 Live500 定时采集"""
    scheduler.remove_task("live500_crawl")
    return {"message": "Live500定时采集已禁用"}


@router.post("/live500/schedule/run-now")
async def run_live500_schedule_now():
    """手动触发 Live500 定时采集任务"""
    return _dispatch_scheduled("live500_crawl", "手动触发Live500采集成功，任务已入队")


@router.post("/injuries/run")
async def run_injury_crawl():
    """手动触发伤病采集（写入临场 injury 风控预警，仅分析用；入队后立即返回）"""
    return _enqueue_manual("伤病采集已入队", "crawl_injuries", crawl_type="manual")


@router.post("/injuries/schedule/enable")
async def enable_injury_schedule(
    interval_minutes: int = Query(120, ge=30, description="采集间隔（分钟），默认2小时"),
):
    scheduler.add_interval_task("injury_crawl", crawler_service.crawl_injuries, interval_minutes)
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"伤病定时采集已启用，每{interval_minutes}分钟执行一次"}


@router.post("/injuries/schedule/disable")
async def disable_injury_schedule():
    scheduler.remove_task("injury_crawl")
    return {"message": "伤病定时采集已禁用"}


@router.post("/injuries/schedule/run-now")
async def run_injury_schedule_now():
    return _dispatch_scheduled("injury_crawl", "伤病采集已入队")


@router.post("/jingcai-odds/run")
async def run_jingcai_odds_crawl(
    days_ahead: int = Query(7, ge=1, le=14, description="向前采集天数"),
):
    """手动触发竞彩胜平负/让球采集（分析用，非投注建议；入队后立即返回）"""
    return _enqueue_manual(
        "胜平负/让球采集已入队",
        "crawl_jingcai_odds",
        days_ahead=days_ahead,
        crawl_type="manual",
    )


@router.post("/jingcai-odds/schedule/enable")
async def enable_jingcai_odds_schedule(
    interval_minutes: int = Query(30, ge=5, description="采集间隔（分钟），默认30分钟"),
):
    scheduler.add_interval_task(
        "jingcai_odds_crawl", crawler_service.crawl_jingcai_odds, interval_minutes
    )
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"胜平负/让球定时采集已启用，每{interval_minutes}分钟执行一次"}


@router.post("/jingcai-odds/schedule/disable")
async def disable_jingcai_odds_schedule():
    scheduler.remove_task("jingcai_odds_crawl")
    return {"message": "胜平负/让球定时采集已禁用"}


@router.post("/jingcai-odds/schedule/run-now")
async def run_jingcai_odds_schedule_now():
    return _dispatch_scheduled("jingcai_odds_crawl", "胜平负/让球采集已入队")


@router.post("/jingcai-bf/run")
async def run_jingcai_bf_crawl(
    days_ahead: int = Query(7, ge=1, le=14, description="向前采集天数"),
):
    """手动触发竞彩比分页投注区采集（分析用，非投注建议；入队后立即返回）"""
    return _enqueue_manual(
        "竞彩比分采集已入队",
        "crawl_jingcai_bf_odds",
        days_ahead=days_ahead,
        crawl_type="manual",
    )


@router.post("/jingcai-bf/schedule/enable")
async def enable_jingcai_bf_schedule(
    interval_minutes: int = Query(30, ge=5, description="采集间隔（分钟），默认30分钟"),
):
    scheduler.add_interval_task(
        "jingcai_bf_crawl", crawler_service.crawl_jingcai_bf_odds, interval_minutes
    )
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"竞彩比分定时采集已启用，每{interval_minutes}分钟执行一次"}


@router.post("/jingcai-bf/schedule/disable")
async def disable_jingcai_bf_schedule():
    scheduler.remove_task("jingcai_bf_crawl")
    return {"message": "竞彩比分定时采集已禁用"}


@router.post("/jingcai-bf/schedule/run-now")
async def run_jingcai_bf_schedule_now():
    return _dispatch_scheduled("jingcai_bf_crawl", "竞彩比分采集已入队")


# ===== 竞彩分析历史比分回补（playid=271 历史日期） =====

@router.post("/jingcai-bf-history/run")
async def run_jingcai_bf_history_crawl(
    days_back: int = Query(30, ge=1, le=90, description="回补最近 N 天历史比分投注区"),
):
    """手动触发竞彩分析历史比分回补（trade.500.com/jczq?playid=271 历史日期；分析用，入队后立即返回）"""
    return _enqueue_manual(
        "竞彩分析历史比分回补已入队",
        "crawl_jingcai_bf_history",
        days_back=days_back,
        crawl_type="manual",
    )


@router.post("/jingcai-bf-history/schedule/enable")
async def enable_jingcai_bf_history_schedule(
    interval_minutes: int = Query(360, ge=30, description="采集间隔（分钟），默认6小时"),
):
    scheduler.add_interval_task(
        "jingcai_bf_history_crawl",
        crawler_service.crawl_jingcai_bf_history,
        interval_minutes,
    )
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"竞彩分析历史比分回补已启用，每{interval_minutes}分钟执行一次"}


@router.post("/jingcai-bf-history/schedule/disable")
async def disable_jingcai_bf_history_schedule():
    scheduler.remove_task("jingcai_bf_history_crawl")
    return {"message": "竞彩分析历史比分回补已禁用"}


@router.post("/jingcai-bf-history/schedule/run-now")
async def run_jingcai_bf_history_schedule_now():
    return _dispatch_scheduled("jingcai_bf_history_crawl", "竞彩分析历史比分回补已入队")


@router.post("/jingcai-scores/run")
async def run_jingcai_scores_crawl(
    days_back: int = Query(7, ge=1, le=30, description="回查最近 N 天赛果"),
    match_date: date = Query(None, description="只回写指定日期 YYYY-MM-DD"),
):
    """手动触发竞彩胜平负赛果回查（playid=269&date=，分析用；入队后立即返回）"""
    return _enqueue_manual(
        "竞彩赛果回写已入队",
        "crawl_jingcai_scores",
        days_back=days_back,
        match_date=match_date,
        crawl_type="manual",
    )


@router.post("/jingcai-scores/schedule/enable")
async def enable_jingcai_scores_schedule(
    interval_minutes: int = Query(60, ge=5, description="采集间隔（分钟），默认60分钟"),
):
    scheduler.add_interval_task(
        "jingcai_score_crawl", crawler_service.crawl_jingcai_scores, interval_minutes
    )
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"竞彩赛果回写定时任务已启用，每{interval_minutes}分钟执行一次"}


@router.post("/jingcai-scores/schedule/disable")
async def disable_jingcai_scores_schedule():
    scheduler.remove_task("jingcai_score_crawl")
    return {"message": "竞彩赛果回写定时任务已禁用"}


@router.post("/jingcai-scores/schedule/run-now")
async def run_jingcai_scores_schedule_now():
    return _dispatch_scheduled("jingcai_score_crawl", "竞彩赛果回写已入队")


@router.post("/live-jingcai/run")
async def run_live_jingcai_crawl(
    days_ahead: int = Query(1, ge=1, le=7, description="向前采集天数"),
):
    """手动触发竞彩比分列表采集（live.500.com/jczq.php；分析用，非投注建议；入队后立即返回）"""
    return _enqueue_manual(
        "竞彩比分列表采集已入队",
        "crawl_live_jingcai",
        days_ahead=days_ahead,
        crawl_type="manual",
    )


@router.post("/live-jingcai/schedule/enable")
async def enable_live_jingcai_schedule(
    interval_minutes: int = Query(30, ge=5, description="采集间隔（分钟），默认30分钟"),
):
    scheduler.add_interval_task(
        "live_jingcai_crawl", crawler_service.crawl_live_jingcai, interval_minutes
    )
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"竞彩比分定时采集已启用，每{interval_minutes}分钟执行一次"}


@router.post("/live-jingcai/schedule/disable")
async def disable_live_jingcai_schedule():
    scheduler.remove_task("live_jingcai_crawl")
    return {"message": "竞彩比分定时采集已禁用"}


@router.post("/live-jingcai/schedule/run-now")
async def run_live_jingcai_schedule_now():
    return _dispatch_scheduled("live_jingcai_crawl", "竞彩比分采集已入队")


@router.post("/leagues/run")
async def run_league_crawl():
    """手动触发联赛数据采集（入队后立即返回）"""
    return _enqueue_manual("联赛数据采集已入队", "crawl_leagues", crawl_type="manual")


@router.post("/leagues/schedule/enable")
async def enable_league_schedule(interval_minutes: int = Query(1440, ge=60, description="采集间隔（分钟），默认1440分钟(24小时)")):
    """启用联赛定时采集"""
    scheduler.add_interval_task("league_crawl", crawler_service.crawl_leagues, interval_minutes)
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"联赛定时采集已启用，每{interval_minutes}分钟执行一次"}


@router.post("/leagues/schedule/disable")
async def disable_league_schedule():
    """禁用联赛定时采集"""
    scheduler.remove_task("league_crawl")
    return {"message": "联赛定时采集已禁用"}


@router.post("/leagues/schedule/run-now")
async def run_league_schedule_now():
    """手动触发联赛定时采集任务"""
    return _dispatch_scheduled("league_crawl", "手动触发联赛采集成功，任务已入队")


@router.post("/teams/run")
async def run_team_crawl(
    league_id: str = Query(None, description="联赛ID，不指定则采集 ESPN 覆盖的规范联赛"),
    include_500: bool = Query(False, description="是否同时采集 500.com 无 ESPN 覆盖的联赛")
):
    """手动触发真实球队名单采集（入队后立即返回）"""
    return _enqueue_manual(
        "球队名单采集已入队",
        "crawl_teams",
        league_id=league_id,
        include_500=include_500,
        crawl_type="manual",
    )


@router.post("/leagues/enrich")
async def enrich_league_data(
    league_id: str = Query(..., description="联赛ID"),
    include_history: bool = Query(False, description="是否同时采集历史赛季赛果"),
    seasons_back: int = Query(0, ge=0, le=5, description="回溯赛季数，include_history=true 时默认 2"),
):
    """为指定联赛补齐真实球队名单、赛程/赛果、阵容、积分榜、射手榜与图片（入队后立即返回）"""
    return _enqueue_manual(
        "联赛数据补齐已入队",
        "enrich_league",
        league_id=league_id,
        include_history=include_history,
        seasons_back=seasons_back,
    )


@router.post("/leagues/enrich-all")
async def enrich_all_priority_leagues(
    include_history: bool = Query(True, description="是否采集历史赛季"),
    seasons_back: int = Query(2, ge=0, le=5, description="回溯赛季数"),
    use_queue: bool = Query(True, description="长任务入队（RQ/线程），避免阻塞 API"),
):
    """批量补齐重点联赛真实数据（默认异步入队）。"""
    if use_queue:
        from services import job_queue

        queued = job_queue.enqueue_enrich_priority(include_history=include_history, seasons_back=seasons_back)
        return {
            "message": "重点联赛富化已入队，请轮询 /crawler/jobs/{job_id}",
            "async": True,
            **queued,
        }
    results = crawler_service.enrich_priority_leagues(
        include_history=include_history,
        seasons_back=seasons_back,
    )
    return {"message": "重点联赛数据补齐完成", "results": results, "async": False}


@router.post("/standings/run")
async def run_standings_crawl(
    league_id: str = Query(None, description="联赛ID，不指定则采集五大联赛+欧冠"),
):
    """采集积分榜（入队后立即返回）"""
    return _enqueue_manual("积分榜采集已入队", "crawl_standings", league_id=league_id)


@router.post("/scorers/run")
async def run_scorers_crawl(
    league_id: str = Query(None, description="联赛ID，不指定则采集五大联赛+欧冠"),
):
    """采集射手榜（入队后立即返回）"""
    return _enqueue_manual("射手榜采集已入队", "crawl_scorers", league_id=league_id)


@router.post("/standings/schedule/enable")
async def enable_standings_schedule(interval_minutes: int = Query(360, ge=60, description="采集间隔（分钟），默认6小时")):
    scheduler.add_interval_task("standings_crawl", crawler_service.crawl_standings, interval_minutes)
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"积分榜定时采集已启用，每{interval_minutes}分钟执行一次"}


@router.post("/standings/schedule/disable")
async def disable_standings_schedule():
    scheduler.remove_task("standings_crawl")
    return {"message": "积分榜定时采集已禁用"}


@router.post("/standings/schedule/run-now")
async def run_standings_schedule_now():
    return _dispatch_scheduled("standings_crawl", "手动触发积分榜采集成功，任务已入队")


@router.post("/scorers/schedule/enable")
async def enable_scorers_schedule(interval_minutes: int = Query(360, ge=60, description="采集间隔（分钟），默认6小时")):
    scheduler.add_interval_task("scorers_crawl", crawler_service.crawl_scorers, interval_minutes)
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"射手榜定时采集已启用，每{interval_minutes}分钟执行一次"}


@router.post("/scorers/schedule/disable")
async def disable_scorers_schedule():
    scheduler.remove_task("scorers_crawl")
    return {"message": "射手榜定时采集已禁用"}


@router.post("/scorers/schedule/run-now")
async def run_scorers_schedule_now():
    return _dispatch_scheduled("scorers_crawl", "手动触发射手榜采集成功，任务已入队")


@router.post("/teams/schedule/enable")
async def enable_team_schedule(interval_minutes: int = Query(1440, ge=60, description="采集间隔（分钟），默认每天一次")):
    """启用球队名单定时采集"""
    scheduler.add_interval_task("team_crawl", crawler_service.crawl_all_teams, interval_minutes)
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"球队名单定时采集已启用，每{interval_minutes}分钟执行一次"}


@router.post("/teams/schedule/disable")
async def disable_team_schedule():
    """禁用球队名单定时采集"""
    scheduler.remove_task("team_crawl")
    return {"message": "球队名单定时采集已禁用"}


@router.post("/teams/schedule/run-now")
async def run_team_schedule_now():
    """手动触发球队名单定时采集任务"""
    return _dispatch_scheduled("team_crawl", "手动触发球队名单采集成功，任务已入队")


@router.post("/players/squad/schedule/enable")
async def enable_squad_schedule(
    interval_minutes: int = Query(1440, ge=60, description="采集间隔（分钟），默认每天一次"),
):
    """启用球队阵容定时采集（规范联赛 ESPN/500 名单）"""
    scheduler.add_interval_task("squad_crawl", crawler_service.crawl_all_players, interval_minutes)
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"球队阵容定时采集已启用，每{interval_minutes}分钟执行一次"}


@router.post("/players/squad/schedule/disable")
async def disable_squad_schedule():
    """禁用球队阵容定时采集"""
    scheduler.remove_task("squad_crawl")
    return {"message": "球队阵容定时采集已禁用"}


@router.post("/players/squad/schedule/run-now")
async def run_squad_schedule_now():
    """手动触发球队阵容定时采集任务"""
    return _dispatch_scheduled("squad_crawl", "手动触发球队阵容采集成功，任务已入队")


@router.post("/players/stats/run")
async def run_player_stats_crawl(
    league_id: str = Query(None, description="联赛ID"),
    team_id: str = Query(None, description="球队ID，指定则只采集该队"),
):
    """手动采集球员进球/助攻/出场数据（入队后立即返回）"""
    if team_id:
        return _enqueue_manual("球员进球统计采集已入队", "crawl_player_stats", team_id=team_id)
    if league_id:
        return _enqueue_manual("球员进球统计采集已入队", "crawl_player_stats", league_id=league_id)
    return _enqueue_manual("球员进球统计采集已入队", "crawl_all_player_stats", crawl_type="manual")


@router.post("/players/stats/schedule/enable")
async def enable_player_stats_schedule(interval_minutes: int = Query(360, ge=30, description="采集间隔（分钟），默认6小时")):
    scheduler.add_interval_task("player_stats_crawl", crawler_service.crawl_all_player_stats, interval_minutes)
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"球员进球统计定时采集已启用，每{interval_minutes}分钟执行一次"}


@router.post("/players/stats/schedule/disable")
async def disable_player_stats_schedule():
    scheduler.remove_task("player_stats_crawl")
    return {"message": "球员进球统计定时采集已禁用"}


@router.post("/players/stats/schedule/run-now")
async def run_player_stats_schedule_now():
    return _dispatch_scheduled("player_stats_crawl", "手动触发球员进球统计采集成功，任务已入队")


@router.post("/matches/player-stats/run")
async def run_match_player_stats_crawl(
    match_id: str = Query(None, description="指定赛事ID，不指定则批量补全"),
    league_id: str = Query(None, description="联赛ID"),
    limit: int = Query(50, ge=1, le=300, description="单次最多处理场次数"),
    prioritize_mappable: bool = Query(True, description="优先补采队名可映射到 ESPN 的场次"),
):
    """采集逐场球员统计（射门、传球、评分等；无 mock 兜底；入队后立即返回）"""
    return _enqueue_manual(
        "逐场球员统计采集已入队",
        "crawl_match_player_stats",
        match_id=match_id,
        league_id=league_id,
        limit=limit,
        crawl_type="manual",
        prioritize_mappable=prioritize_mappable,
    )


@router.post("/matches/player-stats/backfill")
async def backfill_priority_match_player_stats(
    limit_per_league: int = Query(250, ge=10, le=500, description="每联赛最多补采场次"),
    prefer_older: bool = Query(True, description="优先补更早的缺场（挖历史缺口）"),
    use_queue: bool = Query(True, description="长任务优先入队（RQ/线程）"),
):
    """重点联赛 ESPN 逐场统计缺场补采（默认入队异步执行）"""
    if use_queue:
        from services import job_queue

        queued = job_queue.enqueue_stats_backfill(
            limit_per_league=limit_per_league,
            prefer_older=prefer_older,
        )
        return {
            "message": "重点联赛逐场统计补采已入队，请轮询 /crawler/jobs/{job_id}",
            **queued,
        }
    result = crawler_service.backfill_priority_match_player_stats(
        limit_per_league=limit_per_league,
        crawl_type="manual",
        prefer_older=prefer_older,
    )
    return {"message": "重点联赛逐场统计补采完成", "result": result}


@router.post("/matches/player-stats/schedule/enable")
async def enable_match_player_stats_schedule(
    interval_minutes: int = Query(360, ge=30, description="采集间隔（分钟），默认6小时"),
):
    scheduler.add_interval_task(
        "match_player_stats_crawl",
        crawler_service.crawl_all_match_player_stats,
        interval_minutes,
    )
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"逐场球员统计定时采集已启用，每{interval_minutes}分钟执行一次"}


@router.post("/matches/player-stats/schedule/disable")
async def disable_match_player_stats_schedule():
    scheduler.remove_task("match_player_stats_crawl")
    return {"message": "逐场球员统计定时采集已禁用"}


@router.post("/matches/player-stats/schedule/run-now")
async def run_match_player_stats_schedule_now():
    return _dispatch_scheduled("match_player_stats_crawl", "手动触发逐场球员统计采集成功，任务已入队")


@router.post("/images/run")
async def run_image_crawl(
    league_id: str = Query(None, description="联赛ID，不指定则采集规范联赛"),
    include_players: bool = Query(True, description="是否同时采集球员头像")
):
    """采集联赛徽标、球队队徽和球员头像（仅当远程存在真实图片；入队后立即返回）"""
    return _enqueue_manual(
        "图片采集已入队",
        "crawl_images",
        league_id=league_id,
        include_players=include_players,
    )


@router.post("/images/schedule/enable")
async def enable_image_schedule(interval_minutes: int = Query(1440, ge=60, description="采集间隔（分钟），默认每天一次")):
    scheduler.add_interval_task("image_crawl", crawler_service.crawl_images, interval_minutes)
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"图片定时采集已启用，每{interval_minutes}分钟执行一次"}


@router.post("/images/schedule/disable")
async def disable_image_schedule():
    scheduler.remove_task("image_crawl")
    return {"message": "图片定时采集已禁用"}


@router.post("/images/schedule/run-now")
async def run_image_schedule_now():
    return _dispatch_scheduled("image_crawl", "手动触发图片采集成功，任务已入队")


# ===== 重点联赛增量采集 + 自动训练 =====

@router.post("/priority-train/schedule/enable")
async def enable_priority_train_schedule(
    interval_minutes: int = Query(720, ge=30, le=10080, description="间隔分钟，默认 12 小时"),
):
    scheduler.add_interval_task(
        "priority_train",
        crawler_service.crawl_priority_and_train,
        interval_minutes,
    )
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"已启用重点联赛采集+训练，间隔 {interval_minutes} 分钟"}


@router.post("/priority-train/schedule/disable")
async def disable_priority_train_schedule():
    scheduler.remove_task("priority_train")
    return {"message": "已停止重点联赛采集+训练"}


@router.post("/priority-train/schedule/run-now")
async def run_priority_train_schedule_now():
    return _dispatch_scheduled("priority_train", "已将重点联赛采集+训练入队，请稍后查看训练记录与采集日志")


@router.post("/priority-train/run")
async def run_priority_train_sync():
    """入队执行一次（定时请用 run-now；结果见 /crawler/jobs/{job_id}）。"""
    return _enqueue_manual(
        "重点联赛增量采集与训练已入队",
        "crawl_priority_and_train",
        crawl_type="manual",
    )


@router.post("/environment/backfill")
async def backfill_environment(
    limit: int = Query(1000, ge=1, le=2000, description="最多处理场次"),
    only_missing: bool = Query(True, description="仅补缺环境字段的场次"),
    upcoming_only: bool = Query(False, description="仅未开赛/进行中"),
    finished_only: bool = Query(False, description="仅完赛场次（优先有球场名）"),
    league_id: str = Query(None, description="限定联赛 ID"),
):
    """用 Open-Meteo 补全赛事天气/气温/草坪，并生成环境类风控预警（写采集日志）。

    默认优先重点联赛；完赛配额高于未赛，有 venue 的完赛优先。
    """
    return _enqueue_manual(
        "环境补全已入队",
        "crawl_environment",
        limit=limit,
        only_missing=only_missing,
        upcoming_only=upcoming_only,
        finished_only=finished_only,
        league_id=league_id,
        crawl_type="manual",
    )


@router.post("/p0/run")
async def run_p0_pipeline(
    stats_limit_per_league: int = Query(500, ge=10, le=500, description="每联赛最多补采射门统计场次"),
    env_limit: int = Query(1000, ge=50, le=2000, description="环境补全最多场次"),
    train: bool = Query(True, description="补采后是否全量训练"),
    enable_environment_schedule: bool = Query(True, description="完成后启用气象定时任务"),
    use_queue: bool = Query(True, description="优先入队（RQ/线程）；false 时用进程内 start_p0_async"),
):
    """P0 一键补齐：重点联赛历史射门 → 环境字段 → 全量训练（后台/队列执行）。"""
    if crawler_service.get_p0_status().get("running"):
        raise HTTPException(status_code=409, detail="P0 正在执行中")

    if use_queue:
        from services import job_queue

        queued = job_queue.enqueue_p0(
            stats_limit_per_league=stats_limit_per_league,
            env_limit=env_limit,
            train=train,
            enable_environment_schedule=enable_environment_schedule,
        )
        crawler_service.mark_p0_queued(
            job_id=queued.get("job_id"),
            job_mode=queued.get("mode"),
        )
        return {
            "message": "P0 已入队（射门补采 → 环境补全 → 全量训练），请轮询 /crawler/p0/status 或 /crawler/jobs/{job_id}",
            **queued,
            **crawler_service.get_p0_status(),
        }

    result = crawler_service.start_p0_async(
        stats_limit_per_league=stats_limit_per_league,
        env_limit=env_limit,
        train=train,
        enable_environment_schedule=enable_environment_schedule,
        crawl_type="manual",
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=409, detail=result.get("message") or "P0 正在执行中")
    return {
        "message": "P0 已在后台启动（射门补采 → 环境补全 → 全量训练），请轮询 /crawler/p0/status",
        **result,
        **crawler_service.get_p0_status(),
    }


@router.get("/p0/status")
async def get_p0_status():
    """P0 流水线当前阶段与最近一次结果摘要。"""
    return crawler_service.get_p0_status()


@router.get("/jobs/{job_id}")
async def get_crawler_job_status(job_id: str):
    """异步采集任务状态（P0 / backfill / enrich 等）。"""
    from services import job_queue

    return job_queue.get_job_status(job_id)


@router.post("/uel/catchup")
async def run_uel_catchup(
    include_history: bool = Query(True, description="采集历史赛季"),
    seasons_back: int = Query(2, ge=0, le=5, description="回溯赛季数"),
    stats_limit: int = Query(250, ge=10, le=500, description="UEL 射门补采场次上限"),
    train: bool = Query(True, description="补采后是否全量训练"),
    use_queue: bool = Query(True, description="默认入队异步执行"),
):
    """欧联杯专项补齐：富化 → 射门统计 → 可选全量训练。"""
    if use_queue:
        from services import job_queue

        queued = job_queue.enqueue_uel_catchup(
            include_history=include_history,
            seasons_back=seasons_back,
            stats_limit=stats_limit,
            train=train,
        )
        return {
            "message": "UEL 补齐已入队，请轮询 /crawler/jobs/{job_id}",
            **queued,
        }
    result = crawler_service.run_uel_catchup(
        include_history=include_history,
        seasons_back=seasons_back,
        stats_limit=stats_limit,
        train=train,
        crawl_type="manual",
    )
    return {"message": "UEL 补齐完成", "result": result}


@router.post("/extended/catchup")
async def run_extended_catchup(
    include_history: bool = Query(True, description="采集历史赛季"),
    seasons_back: int = Query(1, ge=0, le=5, description="回溯赛季数（扩展联赛默认 1）"),
    stats_limit: int = Query(80, ge=10, le=400, description="每联赛射门补采场次上限"),
    train: bool = Query(False, description="补采后是否全量训练（默认否，避免抢核心配额）"),
    include_p3: bool = Query(True, description="同时补齐 P3 双源 NOR/K1"),
    use_queue: bool = Query(True, description="默认入队异步执行"),
    leagues: Optional[str] = Query(None, description="逗号分隔联赛 ID，覆盖默认列表"),
):
    """P2 扩展联赛补齐：MLS/BRA/SWE/FIN（+ 可选 NOR/K1）富化 → 射门 → 可选训练。"""
    from services.real_team_crawler import get_extended_leagues, get_p3_dual_leagues

    league_ids = None
    if leagues and leagues.strip():
        league_ids = [x.strip().upper() for x in leagues.split(",") if x.strip()]
    elif include_p3:
        league_ids = list(dict.fromkeys([*get_extended_leagues(), *get_p3_dual_leagues()]))

    if use_queue:
        from services import job_queue

        queued = job_queue.enqueue_extended_catchup(
            include_history=include_history,
            seasons_back=seasons_back,
            stats_limit=stats_limit,
            train=train,
            league_ids=league_ids,
        )
        return {
            "message": "扩展联赛补齐已入队，请轮询 /crawler/jobs/{job_id}",
            "leagues": league_ids or list(get_extended_leagues()),
            **queued,
        }
    result = crawler_service.run_extended_catchup(
        include_history=include_history,
        seasons_back=seasons_back,
        stats_limit=stats_limit,
        train=train,
        crawl_type="manual",
        league_ids=league_ids,
    )
    return {"message": "扩展联赛补齐完成", "result": result}


@router.get("/data-quality/summary")
async def get_data_quality_summary(db: Session = Depends(get_db)):
    """数据质量 KPI 与建议（不含分联赛明细）。"""
    from services.data_quality_service import data_quality_service
    return data_quality_service.summary(db)


@router.get("/data-quality/by-league")
async def get_data_quality_by_league(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """分联赛覆盖明细，分页返回。"""
    from services.data_quality_service import data_quality_service
    return data_quality_service.by_league(db, page=page, page_size=page_size)


@router.get("/data-quality")
async def get_data_quality(db: Session = Depends(get_db)):
    """覆盖率、训练滞后、模型超参落库状态与建议动作（P1 看板，完整数据）。"""
    from services.data_quality_service import data_quality_service
    return data_quality_service.overview(db)


@router.get("/mapping-gaps/summary")
async def get_mapping_gaps_summary(db: Session = Depends(get_db)):
    """映射缺口 KPI + 难映射球队（不含场次明细）。"""
    from services.data_quality_service import data_quality_service
    return data_quality_service.mapping_gaps_summary(db)


@router.get("/mapping-gaps/rows")
async def get_mapping_gaps_rows(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=100),
    league_id: str | None = Query(None, description="按联赛筛选"),
    reason: str | None = Query(None, description="no_source | mapping_gap | pending_crawl"),
    limit_per_league: int = Query(50, ge=5, le=100, description="每联赛最多扫描条数"),
    db: Session = Depends(get_db),
):
    """映射缺口场次明细分页。"""
    from services.data_quality_service import data_quality_service
    return data_quality_service.mapping_gaps_rows(
        db,
        page=page,
        page_size=page_size,
        league_id=league_id,
        reason=reason,
        limit_per_league=limit_per_league,
    )


@router.get("/mapping-gaps")
async def get_mapping_gaps(
    limit_per_league: int = Query(40, ge=5, le=100, description="每联赛最多列出缺场数"),
    db: Session = Depends(get_db),
):
    """UCL 无源阶段 + ESPN 队名难映射导致的缺统计清单。"""
    from services.data_quality_service import data_quality_service
    return data_quality_service.mapping_gaps(db, limit_per_league=limit_per_league)


@router.get("/team-aliases")
async def list_team_aliases(
    status: Optional[str] = Query(None, description="pending | confirmed | rejected"),
    team_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="别名关键字"),
    limit: int = Query(100, ge=1, le=300),
    db: Session = Depends(get_db),
):
    from services.team_alias_service import TeamAliasService
    return {"items": TeamAliasService.list(db, status=status, team_id=team_id, q=q, limit=limit)}


@router.post("/team-aliases")
async def create_team_alias(payload: TeamAliasIn, db: Session = Depends(get_db)):
    from services.team_alias_service import TeamAliasService
    item = TeamAliasService.create(db, payload.model_dump())
    return {"message": "别名已保存", "item": item}


@router.put("/team-aliases/{alias_id}")
async def update_team_alias(alias_id: int, payload: TeamAliasIn, db: Session = Depends(get_db)):
    from services.team_alias_service import TeamAliasService
    item = TeamAliasService.update(db, alias_id, payload.model_dump(exclude_unset=True))
    return {"message": "别名已更新", "item": item}


@router.delete("/team-aliases/{alias_id}")
async def delete_team_alias(alias_id: int, db: Session = Depends(get_db)):
    from services.team_alias_service import TeamAliasService
    TeamAliasService.delete(db, alias_id)
    return {"message": "别名已删除"}


@router.post("/team-aliases/suggest")
async def suggest_team_aliases(db: Session = Depends(get_db)):
    """把当前映射缺口中的难映射队写成 pending 别名，供人工确认。"""
    from services.data_quality_service import data_quality_service
    from services.team_alias_service import TeamAliasService
    gaps = data_quality_service.mapping_gaps_summary(db)
    result = TeamAliasService.suggest_from_weak_teams(db, gaps.get("weak_teams") or [])
    return {"message": "已生成待确认别名", **result}


@router.post("/environment/schedule/enable")
async def enable_environment_schedule(
    interval_minutes: int = Query(360, ge=30, description="采集间隔（分钟），默认6小时"),
):
    scheduler.add_interval_task(
        "environment_crawl", crawler_service.crawl_environment, interval_minutes
    )
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"气象环境补全已启用，间隔 {interval_minutes} 分钟"}


@router.post("/environment/schedule/disable")
async def disable_environment_schedule():
    scheduler.remove_task("environment_crawl")
    return {"message": "气象环境补全已停止"}


@router.post("/environment/schedule/run-now")
async def run_environment_schedule_now():
    return _dispatch_scheduled("environment_crawl", "气象环境补全已入队")


@router.post("/quality-alerts/schedule/enable")
async def enable_quality_alert_schedule(
    interval_minutes: int = Query(360, ge=30, description="检查间隔（分钟），默认6小时"),
):
    scheduler.add_interval_task(
        "quality_alert_check", crawler_service.check_quality_alerts, interval_minutes
    )
    if not scheduler.is_running():
        scheduler.start()
    return {"message": f"数据质量告警已启用，间隔 {interval_minutes} 分钟"}


@router.post("/quality-alerts/schedule/disable")
async def disable_quality_alert_schedule():
    scheduler.remove_task("quality_alert_check")
    return {"message": "数据质量告警已停止"}


@router.post("/quality-alerts/schedule/run-now")
async def run_quality_alert_schedule_now():
    return _dispatch_scheduled("quality_alert_check", "数据质量告警检查已入队")


@router.post("/quality-alerts/run")
async def run_quality_alerts_now():
    """入队执行一次质量检查（写入风控预警 + quality 快照日志）。"""
    return _enqueue_manual("数据质量检查已入队", "check_quality_alerts", crawl_type="manual")


# ===== 系统运行日志 =====

@router.get("/runtime-logs")
async def get_runtime_logs():
    """列出系统启动后的运行日志文件（按日）。"""
    logs = list_runtime_logs()
    current = get_current_log_path()
    return {
        "current": current.name if current.is_file() else None,
        "logs": logs,
    }


@router.get("/runtime-logs/tail")
async def get_runtime_log_tail(
    name: str = Query(None, description="日志文件名，默认当日"),
    lines: int = Query(300, ge=1, le=2000, description="返回末尾行数"),
):
    """查看系统运行日志末尾内容。"""
    try:
        path = resolve_log_path(name)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的日志文件名")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="日志文件不存在")

    return {
        "name": path.name,
        "lines": lines,
        "content": read_log_tail(path, lines=lines),
        "size": path.stat().st_size if path.is_file() else 0,
    }


@router.get("/runtime-logs/download")
async def download_runtime_log(
    name: str = Query(None, description="日志文件名，默认当日"),
):
    """下载系统运行日志 .log 文件。"""
    try:
        path = resolve_log_path(name)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的日志文件名")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="日志文件不存在")

    return FileResponse(
        path,
        filename=path.name,
        media_type="text/plain; charset=utf-8",
    )


# ===== 采集日志 =====

@router.get("/logs")
async def get_crawl_logs(
    crawl_type: str = Query(None, description="采集类型: manual/scheduled/initial"),
    crawl_category: str = Query(None, description="采集类别: match/player"),
    league_id: str = Query(None, description="联赛ID"),
    status: str = Query(None, description="状态: success/failed"),
    hours: int = Query(24, ge=0, description="最近N小时的日志；0=全部"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db)
):
    """获取采集日志列表（支持分页和筛选）"""
    query = db.query(CrawlLog)

    if crawl_type:
        query = query.filter(CrawlLog.crawl_type == crawl_type)
    if crawl_category:
        query = query.filter(CrawlLog.crawl_category == crawl_category)
    if league_id:
        query = query.filter(CrawlLog.league_id == league_id)
    if status:
        query = query.filter(CrawlLog.status == status)
    # hours=0：不截断，用于查看全部历史采集记录（含 9 月之前）
    if hours:
        cutoff = datetime.now() - timedelta(hours=hours)
        query = query.filter(CrawlLog.started_at >= cutoff)

    total = query.count()
    logs = query.order_by(CrawlLog.started_at.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()

    return {
        "logs": logs,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


@router.get("/logs/stats")
async def get_crawl_stats(
    hours: int = Query(24, ge=0, description="统计最近N小时；0=全部"),
    db: Session = Depends(get_db)
):
    """获取采集统计信息"""
    try:
        # hours=0：不按时间截断，统计全部采集记录
        time_filters = []
        if hours:
            cutoff = datetime.now() - timedelta(hours=hours)
            time_filters.append(CrawlLog.started_at >= cutoff)

        total = db.query(CrawlLog).filter(*time_filters).count()
        success = db.query(CrawlLog).filter(
            *time_filters,
            CrawlLog.status == 'success'
        ).count()
        failed = total - success

        category_stats = db.query(
            CrawlLog.crawl_category,
            func.count(CrawlLog.id).label('count'),
            func.sum(CrawlLog.found_count).label('found'),
            func.sum(CrawlLog.saved_count).label('saved'),
            func.sum(CrawlLog.updated_count).label('updated')
        ).filter(*time_filters) \
         .group_by(CrawlLog.crawl_category).all()

        type_stats = db.query(
            CrawlLog.crawl_type,
            func.count(CrawlLog.id).label('count')
        ).filter(*time_filters) \
         .group_by(CrawlLog.crawl_type).all()

        status_stats = db.query(
            CrawlLog.status,
            func.count(CrawlLog.id).label('count')
        ).filter(*time_filters) \
         .group_by(CrawlLog.status).all()

        return {
            "hours": hours,
            "total": total,
            "success": success,
            "failed": failed,
            "success_rate": round(success / total * 100, 2) if total > 0 else 0,
            "by_category": [
                {
                    "category": r.crawl_category,
                    "count": r.count,
                    "found": r.found or 0,
                    "saved": r.saved or 0,
                    "updated": r.updated or 0
                } for r in category_stats
            ],
            "by_type": [{"type": r.crawl_type, "count": r.count} for r in type_stats],
            "by_status": [{"status": r.status, "count": r.count} for r in status_stats]
        }
    except Exception as e:
        import traceback
        logger.error(f"get_crawl_stats error: {str(e)}\n{traceback.format_exc()}")
        return {
            "hours": hours,
            "total": 0,
            "success": 0,
            "failed": 0,
            "success_rate": 0,
            "by_category": [],
            "by_type": [],
            "by_status": [],
            "error": str(e)
        }


@router.get("/logs/{log_id}")
async def get_crawl_log(log_id: int, db: Session = Depends(get_db)):
    log = CrawlLogService.get_by_id(db, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="日志不存在")
    return log


@router.delete("/logs/clean")
async def clean_old_logs(days: int = Query(30, description="删除N天前的日志"), db: Session = Depends(get_db)):
    CrawlLogService.delete_old(db, days)
    return {"message": f"已删除{days}天前的日志"}


@router.delete("/logs/{log_id}")
async def delete_crawl_log(log_id: int, db: Session = Depends(get_db)):
    log = CrawlLogService.delete(db, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="日志不存在")
    return {"message": "日志删除成功"}


# ===== 联赛字典 =====

@router.get("/leagues")
async def get_crawlable_leagues():
    return {
        "leagues": [
            {"id": "EPL", "name": "英超"},
            {"id": "LALIGA", "name": "西甲"},
            {"id": "BUNDES", "name": "德甲"},
            {"id": "SERIEA", "name": "意甲"},
            {"id": "LIGUE1", "name": "法甲"},
            {"id": "UCL", "name": "欧冠"},
            {"id": "UEL", "name": "欧联"},
            {"id": "ECH", "name": "英冠"},
            {"id": "WC", "name": "世界杯"},
            {"id": "NOR", "name": "挪超"},
            {"id": "K1", "name": "韩职"},
        ]
    }
