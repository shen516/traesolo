"""竞彩 SP 隐含概率 / overround / 模型偏差。"""

from services.odds_analysis import (
    analyze_odds,
    compare_to_model,
    implied_probs_from_sp,
    odds_deviation_report,
)


def test_implied_probs_normalize():
    out = implied_probs_from_sp(2.0, 3.5, 3.5)
    assert out is not None
    assert abs(out["home"] + out["draw"] + out["away"] - 1.0) < 1e-3
    assert out["overround"] > 0
    assert out["tendency"] == "H"


def test_implied_rejects_incomplete():
    assert implied_probs_from_sp(2.0, None, 3.0) is None
    assert implied_probs_from_sp(0, 3.0, 3.0) is None


def test_compare_to_model_levels():
    implied = implied_probs_from_sp(1.5, 4.0, 6.0)
    model = {"home": 0.40, "draw": 0.30, "away": 0.30}
    vs = compare_to_model(implied, model)
    assert vs["max_abs_delta"] > 0
    assert vs["level"] in ("low", "mid", "high")
    assert "agree_tendency" in vs


def test_analyze_odds_compact_and_full():
    src = {
        "handicap": -1,
        "odds_nspf_win": 2.1,
        "odds_nspf_draw": 3.2,
        "odds_nspf_lose": 3.4,
        "odds_spf_win": 1.8,
        "odds_spf_draw": 3.5,
        "odds_spf_lose": 4.0,
    }
    pred = {"home_win_prob": 0.45, "draw_prob": 0.28, "away_win_prob": 0.27}
    full = analyze_odds(src, pred, compact=False)
    assert full["nspf"]["home"] > 0
    assert full["spf"] is not None
    assert full["vs_model"] is not None
    compact = analyze_odds(src, pred, compact=True)
    assert compact["has_odds"] is True
    assert compact["market_tendency"] in ("H", "D", "A")
    assert compact["delta_level"] in ("low", "mid", "high")


def test_odds_deviation_report_empty(monkeypatch):
    class FakeQ:
        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def all(self):
            return []

    class FakeDB:
        def query(self, *a, **k):
            return FakeQ()

    out = odds_deviation_report(FakeDB(), days=30)
    assert out["sample_size"] == 0
    assert out["with_prediction"] == 0
