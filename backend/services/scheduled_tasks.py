"""定时任务定义（单一数据源）

main.py 启动时通过 register_all() 注册到调度器；
新增任务时只需在此文件添加一条记录。
"""
import logging
from typing import Callable, List, Tuple

logger = logging.getLogger(__name__)


def get_task_definitions(crawler_service) -> List[Tuple[str, Callable, int, str, str, str]]:
    return [
        (
            "match_crawl",
            crawler_service.crawl_all_leagues,
            60,
            "赛事数据采集",
            "match",
            "定时采集各联赛近期赛事（500.com 主；若「胜平负/让球」专项任务已启用则跳过竞彩赔率，空结果或无 500 URL 时 ESPN 兜底）",
        ),
        (
            "jingcai_odds_crawl",
            crawler_service.crawl_jingcai_odds,
            30,
            "胜平负/让球采集",
            "odds",
            "定时采集 trade.500.com/jczq 胜平负与让球 SP（分析用，默认 30 分钟）",
        ),
        (
            "jingcai_bf_crawl",
            crawler_service.crawl_jingcai_bf_odds,
            30,
            "竞彩比分采集",
            "odds",
            "定时采集 trade.500.com/jczq 比分页投注区 SP（分析用，默认 30 分钟）",
        ),
        (
            "jingcai_hh_crawl",
            crawler_service.crawl_jingcai_hh_odds,
            30,
            "竞彩半全场采集",
            "odds",
            "定时采集 trade.500.com/jczq?playid=272 半全场 9 项真实 SP 并推导半场三选一（分析用，默认 30 分钟）",
        ),
        (
            "jingcai_bf_history_crawl",
            crawler_service.crawl_jingcai_bf_history,
            360,
            "竞彩分析历史比分回补",
            "odds",
            "定时回补 trade.500.com/jczq?playid=271 历史日期比分投注区 SP，补齐「竞彩分析」历史比分列表（默认 6 小时，每次回补近 30 天）",
        ),
        (
            "jingcai_trade_all_crawl",
            crawler_service.crawl_jingcai_trade_all,
            30,
            "竞彩全玩法采集",
            "odds",
            "定时采集 trade.500.com/jczq 混合过关页全玩法（单关/胜平负让球/混合过关/比分/进球数/半全场）SP 与 subactive 开关，落 jingcai_match_odds 在售视图（分析用，默认 30 分钟）",
        ),
        (
            "jingcai_trade_poll",
            crawler_service.crawl_jingcai_trade_poll,
            5,
            "竞彩全玩法轮询",
            "odds",
            "轻量轮询：临近开赛（≤60 分钟）或已开赛/完赛缺赛果时才抓取并回补，否则跳过（低成本，默认 5 分钟）",
        ),
        (
            "jingcai_trade_history",
            crawler_service.crawl_jingcai_trade_history,
            360,
            "竞彩全玩法历史回补",
            "odds",
            "向后回补近 30 个销售日的全玩法 SP 与赛果到 jingcai_match_odds，供赛果校验与历史分析对照（分析用，默认 6 小时）",
        ),
        (
            "jingcai_score_crawl",
            crawler_service.crawl_jingcai_scores,
            60,
            "竞彩赛果回写",
            "odds",
            "按 date 回查 trade.500.com/jczq?playid=269 近 N 日胜平负赛果比分并回写入库（默认 60 分钟）",
        ),
        (
            "live_jingcai_crawl",
            crawler_service.crawl_live_jingcai,
            30,
            "竞彩比分列表采集",
            "odds",
            "定时采集 live.500.com/jczq.php 竞彩比分列表（比分/状态/SP 回写，分析用，默认 30 分钟）",
        ),
        (
            "league_crawl",
            crawler_service.crawl_leagues,
            1440,
            "联赛数据采集",
            "league",
            "定时采集 liansai.500.com 联赛信息（联赛目录主入口）",
        ),
        (
            "team_crawl",
            crawler_service.crawl_all_teams,
            1440,
            "球队名单采集",
            "team",
            "定时从 ESPN / 500.com 积分榜采集真实球队名单（500 主，ESPN 补 espn_id/队徽）",
        ),
        (
            "squad_crawl",
            crawler_service.crawl_all_players,
            1440,
            "球队阵容采集",
            "squad",
            "定时从 ESPN / 500.com 刷新规范联赛各队阵容（软先验与球员映射）",
        ),
        (
            "player_stats_crawl",
            crawler_service.crawl_all_player_stats,
            360,
            "球员进球统计",
            "player",
            "定时从 ESPN 刷新球员进球、助攻、出场数据",
        ),
        (
            "match_player_stats_crawl",
            crawler_service.crawl_all_match_player_stats,
            360,
            "逐场球员统计",
            "match_player",
            "定时采集完赛场次的逐场球员技术统计（射门、传球、评分等）",
        ),
        (
            "image_crawl",
            crawler_service.crawl_images,
            720,
            "球员头像采集",
            "media",
            "全量采集联赛徽标、球队队徽与球员头像（500.com + ESPN）",
        ),
        (
            "priority_train",
            crawler_service.crawl_priority_and_train,
            720,
            "重点联赛采集+训练",
            "train",
            "重点联赛赛程增量后自动训练；若逐场统计/积分榜/射手榜/气象专项任务已启用则跳过对应步骤避免双跑",
        ),
        (
            "standings_crawl",
            crawler_service.crawl_standings,
            360,
            "积分榜采集",
            "standings",
            "定时采集五大联赛+欧冠/欧联积分榜（500 主，空则 ESPN 兜底）",
        ),
        (
            "scorers_crawl",
            crawler_service.crawl_scorers,
            360,
            "射手榜采集",
            "scorers",
            "定时采集五大联赛+欧冠射手榜（ESPN statistics）",
        ),
        (
            "environment_crawl",
            crawler_service.crawl_environment,
            360,
            "气象环境补全",
            "environment",
            "Open-Meteo 补全赛事天气/气温/草坪，并生成环境类风控预警",
        ),
        (
            "quality_alert_check",
            crawler_service.check_quality_alerts,
            360,
            "数据质量告警",
            "quality",
            "检查射门 miss 连续失败、完赛回写停滞、映射缺口环比，并写入风控预警",
        ),
        (
            "live500_crawl",
            crawler_service.crawl_live500,
            30,
            "Live500比分回写",
            "match",
            "重点联赛比分/状态轻量回写（只更新已有场次，不新建）",
        ),
        (
            "injury_crawl",
            crawler_service.crawl_injuries,
            120,
            "伤病采集",
            "injury",
            "ESPN 伤病 → 临近场次 injury 风控预警（分析用，默认 2 小时）",
        ),
    ]


def get_system_task_definitions() -> List[Tuple[str, Callable, int, str, str, str]]:
    """系统类任务（非采集）：订阅到期检查、模拟投注结算等。"""
    from services.subscription_service import expire_overdue_subscriptions_task
    from services.simulation_bet_service import settle_task
    return [
        (
            "subscription_expire_check",
            expire_overdue_subscriptions_task,
            1440,
            "订阅到期检查",
            "subscription",
            "每日批量将到期订阅置为 expired（请求内懒检查之外的兜底，首次注册默认启用）",
        ),
        (
            "simulation_bet_settle",
            settle_task,
            5,
            "模拟投注结算",
            "simulation",
            "扫描 pending 且赛事已 finished 的模拟投注单，按实际赛果核对命中并计算模拟派奖（幂等，每 5 分钟）",
        ),
    ]


# 已从注册表移除的旧任务 ID（仅作文档说明，cleanup_orphan_tasks 会清理不在注册表中的 DB 记录）
RETIRED_TASK_IDS = frozenset({"player_crawl"})

# 首次注册即默认启用的任务（无 DB 记录时启用一次；用户停用后不再强开）
DEFAULT_ENABLED_TASK_IDS = frozenset({"subscription_expire_check"})


def register_all(scheduler, crawler_service, *, enable_defaults: bool = True) -> None:
    """注册任务函数。enable_defaults=False 时不写库、不启动调度（供 RQ worker 使用）。"""
    for task_id, func, interval, name, category, desc in [
        *get_task_definitions(crawler_service),
        *get_system_task_definitions(),
    ]:
        scheduler.register_task(
            task_id, func, interval, name=name, category=category, description=desc
        )
    if enable_defaults:
        _enable_default_tasks(scheduler)


def ensure_task_registry(*, enable_defaults: bool = False) -> None:
    """进程内注册表为空时补注册。worker 不启用默认任务，避免改写 DB 里的启停状态。"""
    from services.crawler_service import crawler_service
    from services.scheduler_service import scheduler

    if scheduler._registry:
        return
    register_all(scheduler, crawler_service, enable_defaults=enable_defaults)


def _brief_result(result) -> dict:
    if not isinstance(result, dict):
        text = "" if result is None else str(result)
        return {"value": text[:300]}
    brief = {}
    for key in (
        "status", "message", "saved", "saved_count", "saved_matches",
        "updated", "found", "error", "total_matches", "model_version",
    ):
        if key in result and result[key] is not None:
            brief[key] = result[key]
    if not brief:
        brief["keys"] = list(result.keys())[:12]
    return brief


def invoke_scheduled_task(task_id: str, lock_token: str = None) -> dict:
    """同步执行已注册任务，直到函数返回。供 worker 与线程回退调用，不要在调度线程里直接用。"""
    from services.scheduler_service import scheduler
    from services.task_run_lock import task_run_lock

    ensure_task_registry(enable_defaults=False)
    info = scheduler._registry.get(task_id) or {}
    func = info.get("func")
    if func is None:
        return {"task_id": task_id, "success": False, "error": "任务未注册"}

    token = lock_token if lock_token and task_run_lock.refresh(task_id, lock_token) else None
    if token is None:
        token = task_run_lock.acquire(task_id)
    if not token:
        logger.info("跳过任务 %s：已有一份正在执行", task_id)
        return {
            "task_id": task_id,
            "success": False,
            "skipped": True,
            "message": "任务正在执行",
        }

    task_run_lock.write_status(task_id, {
        "phase": "running",
        "in_progress": True,
        "message": "执行中",
    })
    task_run_lock.start_heartbeat(task_id, token)
    logger.info("开始执行定时任务: %s", task_id)
    try:
        result = func()
        scheduler._update_last_run(task_id)
        logger.info("定时任务完成: %s", task_id)
        return {
            "task_id": task_id,
            "success": True,
            "result": _brief_result(result),
        }
    except Exception as e:
        logger.exception("定时任务失败: %s", task_id)
        return {"task_id": task_id, "success": False, "error": str(e)}
    finally:
        task_run_lock.release(task_id, token)


def _enable_default_tasks(scheduler) -> None:
    """DEFAULT_ENABLED_TASK_IDS 中尚无 DB 状态记录的任务，首次启用并持久化。"""
    if not DEFAULT_ENABLED_TASK_IDS:
        return
    from db.database import SessionLocal
    from db.models import ScheduledTaskStatus

    defs = {t[0]: t for t in get_system_task_definitions()}
    db = SessionLocal()
    try:
        existing = {
            row.task_id
            for row in db.query(ScheduledTaskStatus)
            .filter(ScheduledTaskStatus.task_id.in_(DEFAULT_ENABLED_TASK_IDS))
            .all()
        }
        for task_id in DEFAULT_ENABLED_TASK_IDS - existing:
            _, func, interval, *_ = defs[task_id]
            scheduler.add_interval_task(task_id, func, interval)
            logger.info("Default-enabled scheduled task: %s", task_id)
    except Exception as e:
        logger.warning("Enable default scheduled tasks skipped: %s", e)
    finally:
        db.close()
