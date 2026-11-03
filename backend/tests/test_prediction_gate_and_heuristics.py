"""赔率完整性检测、看盘启发式、英冠映射（预测计算与开售无关）。"""

from services.odds_analysis import (
    PredictionSkipped,
    assert_nspf_on_sale,
    has_nspf_odds,
    analyze_odds,
)
from services.odds_heuristics import analyze_odds_heuristics
from services.real_team_crawler import (
    CANONICAL_FIVE00_URL,
    ESPN_LEAGUE_MAP,
    FIVE00_TO_CANONICAL,
    get_p3_dual_leagues,
    get_stats_leagues,
    league_pipeline_tier,
)


def test_has_nspf_odds():
    assert has_nspf_odds({"odds_nspf_win": 2.1, "odds_nspf_draw": 3.2, "odds_nspf_lose": 3.4})
    assert not has_nspf_odds({"odds_nspf_win": 2.1, "odds_nspf_draw": None, "odds_nspf_lose": 3.4})
    assert not has_nspf_odds({})


def test_assert_nspf_gate(monkeypatch):
    monkeypatch.setattr(
        "services.odds_analysis.require_nspf_odds_enabled",
        lambda: True,
    )
    try:
        assert_nspf_on_sale({})
        assert False, "should raise"
    except PredictionSkipped as e:
        assert e.code == "nspf_not_on_sale"
    assert_nspf_on_sale(
        {"odds_nspf_win": 1.85, "odds_nspf_draw": 3.4, "odds_nspf_lose": 4.2}
    )


def test_assert_nspf_gate_off_by_default(monkeypatch):
    """默认关闭：无胜平负 SP 也不拦截预测。"""
    monkeypatch.setattr(
        "services.odds_analysis.require_nspf_odds_enabled",
        lambda: False,
    )
    assert_nspf_on_sale({})
    assert_nspf_on_sale({"odds_nspf_win": None, "odds_nspf_draw": None, "odds_nspf_lose": None})


def test_heuristics_draw_when_above_threshold():
    h = analyze_odds_heuristics(
        {
            "odds_nspf_win": 2.05,
            "odds_nspf_draw": 3.2,
            "odds_nspf_lose": 3.5,
            "handicap": -1,
            "odds_spf_win": 2.0,
            "odds_spf_draw": 3.3,
            "odds_spf_lose": 3.4,
        }
    )
    assert h is not None
    assert h["nspf"]["lean"] == "draw"
    assert h["main_score"] in ("0-0", "1-1", "2-2")
    assert h["spf"]["lean"] == "draw"
    assert "胜平" in h["htft"]["combos"] or "平平" in h["htft"]["combos"]


def test_heuristics_strong_vs_weak_big_scores():
    h = analyze_odds_heuristics(
        {
            "odds_nspf_win": 1.25,
            "odds_nspf_draw": 5.5,
            "odds_nspf_lose": 11.0,
        }
    )
    assert h["nspf"]["rule"] == "strong_vs_weak"
    assert h["main_score"] in ("3-0", "3-1", "4-0", "4-1")


def test_analyze_odds_includes_heuristics():
    full = analyze_odds(
        {
            "odds_nspf_win": 2.2,
            "odds_nspf_draw": 3.1,
            "odds_nspf_lose": 3.3,
        },
        compact=False,
    )
    assert full["heuristics"] is not None
    assert full["has_nspf"] is True


def test_ech_championship_dual_map():
    assert "ECH" in get_p3_dual_leagues()
    assert ESPN_LEAGUE_MAP["ECH"] == "eng.2"
    assert CANONICAL_FIVE00_URL["ECH"].endswith("zuqiu-19935/")
    assert FIVE00_TO_CANONICAL["LS19935"] == "ECH"
    assert FIVE00_TO_CANONICAL["LS9116"] == "ECH"
    assert league_pipeline_tier("ECH") == "dual_mapped"
    assert "ECH" in get_stats_leagues()
    # EC 仍是欧洲杯，勿混淆
    assert ESPN_LEAGUE_MAP["EC"] == "uefa.euro"
    assert league_pipeline_tier("EC") == "espn_only"
