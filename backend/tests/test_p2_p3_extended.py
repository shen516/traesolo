"""P2 扩展联赛 + P3 NOR/K1 双源与纯 500 策略。"""

from services.analysis_scenarios import (
    build_scenarios_payload,
    league_data_policy,
    select_primary_scenario,
)
from services.real_team_crawler import (
    CANONICAL_FIVE00_URL,
    ESPN_LEAGUE_MAP,
    EXTENDED_LEAGUES_DEFAULT,
    FIVE00_TO_CANONICAL,
    get_extended_leagues,
    get_p3_dual_leagues,
    get_stats_leagues,
    league_pipeline_tier,
)


def test_extended_leagues_default():
    assert get_extended_leagues() == EXTENDED_LEAGUES_DEFAULT
    for lid in ("MLS", "BRA", "SWE", "FIN"):
        assert lid in ESPN_LEAGUE_MAP
        assert lid in CANONICAL_FIVE00_URL
        assert league_pipeline_tier(lid) == "extended"


def test_p3_nor_k1_dual_maps():
    assert get_p3_dual_leagues() == ("NOR", "K1", "ECH")
    assert ESPN_LEAGUE_MAP["NOR"] == "nor.1"
    assert ESPN_LEAGUE_MAP["K1"] == "kor.1"
    assert ESPN_LEAGUE_MAP["ECH"] == "eng.2"
    assert "NOR" in CANONICAL_FIVE00_URL
    assert "K1" in CANONICAL_FIVE00_URL
    assert "ECH" in CANONICAL_FIVE00_URL
    assert FIVE00_TO_CANONICAL["LS19507"] == "NOR"
    assert FIVE00_TO_CANONICAL["LS19554"] == "K1"
    assert FIVE00_TO_CANONICAL["LS9116"] == "ECH"
    assert FIVE00_TO_CANONICAL["LS19935"] == "ECH"
    assert CANONICAL_FIVE00_URL["ECH"].endswith("zuqiu-19935/")
    assert league_pipeline_tier("NOR") == "dual_mapped"
    assert league_pipeline_tier("K1") == "dual_mapped"
    assert league_pipeline_tier("ECH") == "dual_mapped"


def test_ec_remains_espn_only():
    assert "EC" in ESPN_LEAGUE_MAP
    assert "EC" not in CANONICAL_FIVE00_URL
    assert league_pipeline_tier("EC") == "espn_only"


def test_stats_leagues_include_extended_and_p3():
    stats = get_stats_leagues()
    for lid in ("MLS", "BRA", "SWE", "FIN", "NOR", "K1", "ECH", "UEL", "EPL"):
        assert lid in stats


def test_five00_only_policy_forces_poisson():
    policy = league_data_policy("LS99999")
    assert policy["five00_only"] is True
    assert policy["xg_priority"] is False
    sid, reason = select_primary_scenario("LS99999", 0.0)
    assert sid == "poisson"
    assert "纯 500" in reason

    payload = build_scenarios_payload(
        league_id="LS99999",
        xg_coverage=0.0,
        ensemble_weights={"elo": 0.3, "poisson": 0.4, "xg": 0.2, "monte_carlo": 0.1},
        poisson={"home_win_prob": 0.4, "draw_prob": 0.3, "away_win_prob": 0.3},
        elo={"home_win_prob": 0.5, "draw_prob": 0.25, "away_win_prob": 0.25},
        xg={"home_win_prob": 0.4, "draw_prob": 0.3, "away_win_prob": 0.3},
        mc={"home_win_prob": 0.4, "draw_prob": 0.3, "away_win_prob": 0.3},
    )
    assert payload["five00_only"] is True
    assert payload["primary_scenario"] == "poisson"
    assert payload["scenarios"]["ensemble"]["available"] is False
    assert payload["scenarios"]["xg"]["available"] is False


def test_enqueue_extended_catchup(monkeypatch):
    from services import job_queue

    monkeypatch.setattr(job_queue, "_queue_enabled", lambda: False)
    calls = []

    def fake_thread(kind, func, meta=None):
        calls.append(kind)
        return {"mode": "thread", "job_id": f"local-{kind}-test", "status": "started", **(meta or {})}

    monkeypatch.setattr(job_queue, "_enqueue_thread", fake_thread)
    out = job_queue.enqueue_extended_catchup(
        include_history=False, seasons_back=1, stats_limit=20, train=False, league_ids=["MLS", "NOR"]
    )
    assert out["job_id"] == "local-extended-test"
    assert "extended" in calls


def test_run_extended_catchup_orchestrates(monkeypatch):
    from services.crawler_service import crawler_service

    seen = []

    monkeypatch.setattr(
        crawler_service,
        "enrich_league",
        lambda lid, **k: seen.append(("enrich", lid)) or {"status": "success", "league_id": lid},
    )
    monkeypatch.setattr(
        crawler_service,
        "crawl_match_player_stats",
        lambda **k: seen.append(("stats", k.get("league_id")))
        or {"status": "success", "saved_matches": 1},
    )
    monkeypatch.setattr(crawler_service, "_save_crawl_log", lambda **k: None)

    out = crawler_service.run_extended_catchup(
        include_history=False,
        stats_limit=10,
        train=False,
        league_ids=["MLS", "NOR"],
    )
    assert out["status"] == "success"
    assert out["leagues"] == ["MLS", "NOR"]
    assert ("enrich", "MLS") in seen
    assert ("stats", "NOR") in seen
