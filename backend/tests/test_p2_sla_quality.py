"""P2：SLA 动态配额与数据质量告警。"""
import json

from services.crawler_sla import (
    allocate_stats_limits,
    apply_sla_to_rows,
    sla_coverage_pct,
    sla_demand,
)
from services.quality_alert_service import (
    alert_key,
    mapping_gap_wow_triggered,
    miss_rate_from_log,
    miss_streak_triggered,
)


CFG = {
    "sla": {
        "enabled": True,
        "default_stats_coverage_pct": 99.0,
        "by_league": {
            "EPL": 99.5,
            "UCL": 99.5,
            "WC": 90.0,
        },
        "min_limit": 20,
        "max_limit": 400,
        "budget_per_run": 900,
    }
}


def _row(lid, with_stats, crawlable, finished=None):
    finished = finished if finished is not None else with_stats + crawlable
    return {
        "league_id": lid,
        "with_player_stats": with_stats,
        "crawlable_missing": crawlable,
        "finished": finished,
        "no_source_missing": max(0, finished - with_stats - crawlable),
    }


def test_sla_allocates_more_to_gap_leagues():
    rows = [
        _row("EPL", 990, 10, 1000),
        _row("LALIGA", 995, 1, 1000),
        _row("BUNDES", 995, 0, 1000),
        _row("SERIEA", 995, 0, 1000),
        _row("LIGUE1", 995, 0, 1000),
        _row("UCL", 200, 80, 780),
    ]
    plan = allocate_stats_limits(rows, cfg=CFG)
    assert plan["allocated"] <= 900
    assert plan["limits"]["UCL"] == 400
    assert plan["limits"]["BUNDES"] == 20
    assert plan["limits"]["EPL"] >= 20
    assert plan["by_league"]["UCL"]["sla_demand"] > plan["by_league"]["EPL"]["sla_demand"]
    assert plan["by_league"]["UCL"]["sla_met"] is False
    assert plan["by_league"]["LALIGA"]["sla_met"] is True


def test_sla_met_leagues_get_min_limit():
    rows = [
        _row("EPL", 1000, 0, 1000),
        _row("LALIGA", 1000, 0, 1000),
    ]
    plan = allocate_stats_limits(rows, budget=200, min_limit=20, max_limit=80, cfg=CFG)
    assert plan["limits"]["EPL"] == 20
    assert plan["limits"]["LALIGA"] == 20
    assert plan["allocated"] == 40


def test_ucl_sla_uses_crawlable_coverage():
    row = _row("UCL", 200, 8, 780)
    assert sla_coverage_pct(row) == round(100.0 * 200 / 208, 1)
    assert sla_demand(row, CFG) == 7
    assert sla_demand(row, CFG) <= 8


def test_apply_sla_skips_wc_budget():
    rows = [
        _row("EPL", 100, 20, 120),
        _row("WC", 10, 50, 60),
    ]
    plan = apply_sla_to_rows(rows, cfg=CFG)
    assert "WC" not in plan["limits"]
    assert rows[1]["sla_target_pct"] == 90.0
    assert rows[1]["sla_limit"] is None
    assert rows[0]["sla_limit"] >= 20


def test_miss_streak_and_sample_floor():
    class Log:
        def __init__(self, found, miss):
            self.found_count = found
            self.updated_count = found - miss
            self.crawled_data = json.dumps({"miss_count": miss})

    high = miss_rate_from_log(Log(10, 8), min_found=5)
    assert high == 0.8
    assert miss_rate_from_log(Log(3, 3), min_found=5) is None
    assert miss_streak_triggered([0.8, 0.7, 0.9], streak=3, threshold=0.5) is True
    assert miss_streak_triggered([0.8, 0.2, 0.9], streak=3, threshold=0.5) is False
    assert miss_streak_triggered([0.8, 0.7], streak=3, threshold=0.5) is False
    assert miss_streak_triggered([0.8, None, 0.9], streak=3, threshold=0.5) is False


def test_mapping_gap_wow_needs_ratio_and_delta():
    assert mapping_gap_wow_triggered(24, 10, ratio=1.2, min_delta=10) is True
    assert mapping_gap_wow_triggered(14, 10, ratio=1.2, min_delta=10) is False
    assert mapping_gap_wow_triggered(50, 0, ratio=1.2, min_delta=10) is False


def test_alert_key_prefix():
    assert alert_key("stats_miss_streak", "EPL") == "quality:stats_miss_streak:EPL"
    assert alert_key("mapping_gap_wow") == "quality:mapping_gap_wow"


def test_resolve_stats_limits_uses_sla_when_no_explicit(monkeypatch):
    from services.crawler_service import crawler_service

    monkeypatch.setattr("services.crawler_sla.sla_enabled", lambda cfg=None: True)
    monkeypatch.setattr(
        "services.crawler_sla.allocate_for_leagues",
        lambda db, ids, budget=None, cfg=None: {
            "limits": {lid: 33 for lid in ids},
            "budget": budget,
        },
    )
    limits, plan = crawler_service._resolve_stats_limits(
        None, ["EPL", "UCL"], explicit_limit=None, budget_key="budget_per_run"
    )
    assert limits["EPL"] == 33
    assert limits["UCL"] == 33
    assert plan is not None

    limits2, plan2 = crawler_service._resolve_stats_limits(
        None, ["EPL", "UCL"], explicit_limit=150, budget_key="budget_per_run"
    )
    assert limits2["EPL"] == 150
    assert limits2["UCL"] == 230
    assert plan2 is None
