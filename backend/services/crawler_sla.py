"""逐场射门统计的 SLA 目标与动态配额。"""

from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_BY_LEAGUE = {
    "EPL": 99.5,
    "LALIGA": 99.5,
    "BUNDES": 99.5,
    "SERIEA": 99.5,
    "LIGUE1": 99.5,
    "UCL": 99.5,
    "UEL": 95.0,
    "WC": 90.0,
    "MLS": 88.0,
    "BRA": 88.0,
    "SWE": 85.0,
    "FIN": 85.0,
    "NOR": 85.0,
    "K1": 85.0,
}


def _crawler_cfg() -> dict:
    try:
        from db.database import config as app_config
        return dict((app_config or {}).get("crawler") or {})
    except Exception:
        return {}


def sla_section(cfg: Optional[dict] = None) -> dict:
    raw = (cfg if cfg is not None else _crawler_cfg()).get("sla") or {}
    return dict(raw) if isinstance(raw, dict) else {}


def sla_enabled(cfg: Optional[dict] = None) -> bool:
    sec = sla_section(cfg)
    if "enabled" not in sec:
        return True
    return bool(sec.get("enabled"))


def sla_target_pct(league_id: str, cfg: Optional[dict] = None) -> float:
    sec = sla_section(cfg)
    default = float(sec.get("default_stats_coverage_pct") or 99.0)
    by_league = sec.get("by_league") or _DEFAULT_BY_LEAGUE
    lid = str(league_id or "").upper()
    if isinstance(by_league, dict) and lid in by_league:
        try:
            return float(by_league[lid])
        except (TypeError, ValueError):
            return default
    return default


def sla_eligible(row: dict) -> int:
    """可补范围：已有统计 + 可补缺场（不含 UCL 资格赛无源）。"""
    with_stats = int(row.get("with_player_stats") or 0)
    crawlable = int(row.get("crawlable_missing") or 0)
    return max(0, with_stats + crawlable)


def sla_coverage_pct(row: dict) -> float:
    eligible = sla_eligible(row)
    with_stats = int(row.get("with_player_stats") or 0)
    if eligible <= 0:
        return 100.0
    return round(100.0 * with_stats / eligible, 1)


def sla_demand(row: dict, cfg: Optional[dict] = None) -> int:
    """为达到 SLA 还需补采的场次（不超过 crawlable_missing）。"""
    eligible = sla_eligible(row)
    crawlable = int(row.get("crawlable_missing") or 0)
    if eligible <= 0 or crawlable <= 0:
        return 0
    target = sla_target_pct(row.get("league_id") or "", cfg)
    with_stats = int(row.get("with_player_stats") or 0)
    need = max(0, math.ceil(eligible * target / 100.0) - with_stats)
    return min(crawlable, need)


def _largest_remainder(remaining: int, weights: Dict[str, int], caps: Dict[str, int]) -> Dict[str, int]:
    """把 remaining 按权重整数分配，单联赛不超过 caps。"""
    extras = {k: 0 for k in weights}
    if remaining <= 0:
        return extras
    total_w = sum(max(0, int(w)) for w in weights.values())
    if total_w <= 0:
        return extras
    remainders = []
    used = 0
    for key, w in weights.items():
        cap = max(0, int(caps.get(key) or 0))
        raw = remaining * max(0, int(w)) / total_w
        base = min(int(raw), cap)
        extras[key] = base
        used += base
        remainders.append((raw - int(raw), key))
    leftover = remaining - used
    remainders.sort(key=lambda x: (-x[0], x[1]))
    while leftover > 0:
        progressed = False
        for _, key in remainders:
            if int(weights.get(key) or 0) <= 0:
                continue
            cap = max(0, int(caps.get(key) or 0))
            if extras[key] >= cap:
                continue
            extras[key] += 1
            leftover -= 1
            progressed = True
            if leftover <= 0:
                break
        if not progressed:
            break
    return extras


def allocate_stats_limits(
    rows: List[dict],
    *,
    budget: Optional[int] = None,
    min_limit: Optional[int] = None,
    max_limit: Optional[int] = None,
    cfg: Optional[dict] = None,
) -> dict:
    """按 SLA 缺口比例分配一次运行的逐场统计配额。"""
    crawler_cfg = cfg if cfg is not None else _crawler_cfg()
    sec = sla_section(crawler_cfg)
    budget = int(budget if budget is not None else (sec.get("budget_per_run") or 900))
    min_limit = int(min_limit if min_limit is not None else (sec.get("min_limit") or 20))
    max_limit = int(max_limit if max_limit is not None else (sec.get("max_limit") or 400))
    min_limit = max(1, min_limit)
    max_limit = max(min_limit, max_limit)
    budget = max(min_limit, budget)

    ids = [str(r.get("league_id") or "") for r in rows if r.get("league_id")]
    n = len(ids)
    if n == 0:
        return {
            "enabled": sla_enabled(crawler_cfg),
            "budget": budget,
            "min_limit": min_limit,
            "max_limit": max_limit,
            "limits": {},
            "by_league": {},
        }

    floor = min_limit
    if floor * n > budget:
        floor = max(1, budget // n)

    demands = {}
    by_league = {}
    for row in rows:
        lid = str(row.get("league_id") or "")
        if not lid:
            continue
        coverage = sla_coverage_pct(row)
        target = sla_target_pct(lid, crawler_cfg)
        demand = sla_demand(row, crawler_cfg)
        demands[lid] = demand
        by_league[lid] = {
            "sla_target_pct": target,
            "sla_coverage_pct": coverage,
            "sla_met": coverage + 1e-9 >= target,
            "sla_demand": demand,
            "sla_eligible": sla_eligible(row),
        }

    remaining = budget - floor * n
    caps = {lid: max_limit - floor for lid in ids}
    extras = _largest_remainder(remaining, demands, caps)
    limits = {}
    for lid in ids:
        limit = min(max_limit, floor + int(extras.get(lid) or 0))
        limits[lid] = limit
        by_league.setdefault(lid, {})["sla_limit"] = limit

    return {
        "enabled": sla_enabled(crawler_cfg),
        "budget": budget,
        "min_limit": min_limit,
        "max_limit": max_limit,
        "allocated": sum(limits.values()),
        "limits": limits,
        "by_league": by_league,
    }


def apply_sla_to_rows(rows: List[dict], cfg: Optional[dict] = None) -> dict:
    """把 SLA 字段写回覆盖率行。配额在重点+扩展联赛间分配。"""
    try:
        from services.real_team_crawler import get_stats_leagues
        priority = set(get_stats_leagues())
    except Exception:
        priority = {"EPL", "LALIGA", "BUNDES", "SERIEA", "LIGUE1", "UCL", "UEL", "MLS", "BRA", "SWE", "FIN"}
    crawler_cfg = cfg if cfg is not None else _crawler_cfg()
    alloc_rows = [r for r in rows if str(r.get("league_id") or "") in priority]
    plan = allocate_stats_limits(alloc_rows, cfg=crawler_cfg)
    extra = plan.get("by_league") or {}
    for row in rows:
        lid = str(row.get("league_id") or "")
        if lid in extra:
            row.update(extra[lid])
            continue
        coverage = sla_coverage_pct(row)
        target = sla_target_pct(lid, crawler_cfg)
        row["sla_target_pct"] = target
        row["sla_coverage_pct"] = coverage
        row["sla_met"] = coverage + 1e-9 >= target
        row["sla_demand"] = sla_demand(row, crawler_cfg)
        row["sla_eligible"] = sla_eligible(row)
        row["sla_limit"] = None
    return plan


def allocate_for_leagues(
    db,
    league_ids: List[str],
    *,
    budget: Optional[int] = None,
    cfg: Optional[dict] = None,
) -> dict:
    from services.data_quality_service import data_quality_service

    rows = [data_quality_service._league_coverage(db, lid) for lid in league_ids]
    plan = allocate_stats_limits(rows, budget=budget, cfg=cfg)
    return plan
