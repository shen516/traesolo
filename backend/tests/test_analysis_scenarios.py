"""analysis_scenarios 自动选主结论规则。"""

from services.analysis_scenarios import (
    SCENARIO_ENSEMBLE,
    SCENARIO_POISSON,
    select_primary_scenario,
    scenario_availability,
)


def test_select_ensemble_when_espn_and_full_xg():
    sid, reason = select_primary_scenario("EPL", 0.9, espn_pipeline=True)
    assert sid == SCENARIO_ENSEMBLE
    assert "整合版" in reason


def test_select_poisson_when_espn_but_no_xg():
    sid, reason = select_primary_scenario("EPL", 0.0, espn_pipeline=True)
    assert sid == SCENARIO_POISSON
    assert "泊松" in reason


def test_select_poisson_when_no_espn():
    sid, reason = select_primary_scenario("K1", 0.0, espn_pipeline=False)
    assert sid == SCENARIO_POISSON
    assert "无 ESPN" in reason


def test_partial_xg_still_ensemble():
    sid, _ = select_primary_scenario("UEL", 0.2, espn_pipeline=True)
    assert sid == SCENARIO_ENSEMBLE


def test_xg_unavailable_without_espn():
    avail = scenario_availability(0.9, espn_pipeline=False)
    assert avail["xg"] is False
    assert avail["poisson"] is True
    assert avail["elo"] is True
    assert avail["ensemble"] is False


def test_apply_scenario_override_locks():
    from services.analysis_scenarios import apply_scenario_override
    result = {
        "scenarios": {
            "poisson": {
                "id": "poisson",
                "label": "进球分布（泊松）",
                "available": True,
                "home_win_prob": 0.55,
                "draw_prob": 0.25,
                "away_win_prob": 0.20,
                "weights": {"poisson": 1.0, "elo": 0, "xg": 0, "monte_carlo": 0},
                "main_score": "1-0",
            },
            "elo": {
                "id": "elo",
                "label": "ELO",
                "available": True,
                "home_win_prob": 0.4,
                "draw_prob": 0.3,
                "away_win_prob": 0.3,
                "weights": {"elo": 1.0},
                "is_primary": True,
            },
        },
        "primary_scenario": "elo",
        "home_win_prob": 0.4,
        "draw_prob": 0.3,
        "away_win_prob": 0.3,
        "analysis": "old",
    }
    out = apply_scenario_override(result, "poisson", locked=True)
    assert out["primary_scenario"] == "poisson"
    assert out["scenario_locked"] is True
    assert out["home_win_prob"] == 0.55
    assert out["scenarios"]["poisson"]["is_primary"] is True
    assert out["scenarios"]["elo"]["is_primary"] is False
