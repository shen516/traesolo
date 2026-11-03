"""竞彩比分 Top3：比分归档 / 方向约束 / 泊松先验 / 逐级放宽 / 回测不穿越。"""

import time
from datetime import date, datetime, timedelta

import numpy as np
import pytest

from services import jingcai_score_top3 as s
from services.subscription_service import FEATURE_JINGCAI_BF, mask_score_top3_list

CFG = s.get_config({
    "k": 50, "bandwidth": 0.1, "smoothing_alpha": 5, "min_effective_samples": 5,
    "recency_half_life_days": 0, "same_league_boost": 1.0,
})


def _make_pool(rows):
    """rows: (kickoff_dt, handicap, nspf_sp|None, spf_sp, home_goals, away_goals)"""
    def probs(sp):
        raw = 1.0 / np.asarray(sp, dtype=float)
        return raw / raw.sum(axis=1, keepdims=True)

    nan3 = (np.nan, np.nan, np.nan)
    nspf_sp = np.array([r[2] or nan3 for r in rows], dtype=float).reshape(-1, 3)
    spf_sp = np.array([r[3] for r in rows], dtype=float).reshape(-1, 3)
    hg = np.array([r[4] for r in rows], dtype=int)
    ag = np.array([r[5] for r in rows], dtype=int)
    return s.SamplePool(
        match_ids=np.array([f"M{i}" for i in range(len(rows))], dtype=object),
        league=np.array(["EPL"] * len(rows), dtype=object),
        kickoff=np.array([r[0].timestamp() for r in rows], dtype=float),
        handicap=np.array([r[1] for r in rows], dtype=int),
        nspf=probs(nspf_sp),
        spf=probs(spf_sp),
        nspf_sp=nspf_sp,
        spf_sp=spf_sp,
        home_goals=hg,
        away_goals=ag,
        cell=np.minimum(hg, s.GRID - 1) * s.GRID + np.minimum(ag, s.GRID - 1),
        snapshot=np.ones(len(rows), dtype=bool),
        built_at=time.time(),
    )


def _target(**kw):
    base = {
        "id": "T1", "league_id": "EPL", "status": "upcoming",
        "match_date": date.today() + timedelta(days=1), "match_time": None,
        "handicap": -1,
        "odds_nspf_win": 1.6, "odds_nspf_draw": 3.8, "odds_nspf_lose": 5.0,
        "odds_spf_win": 2.9, "odds_spf_draw": 3.4, "odds_spf_lose": 2.1,
    }
    base.update(kw)
    return base


SP_NSPF = (1.6, 3.8, 5.0)
SP_SPF = (2.9, 3.4, 2.1)


def test_score_key_buckets_other():
    assert s.score_key(2, 1) == "2:1"
    assert s.score_key(6, 0) == "胜其它"
    assert s.score_key(4, 3) == "胜其它"
    assert s.score_key(4, 4) == "平其它"
    assert s.score_key(0, 6) == "负其它"
    assert len(s.ALL_KEYS) == 31


@pytest.mark.parametrize(
    "hg,ag,hc,nspf,spf,ok",
    [
        (2, 0, -1, "H", "H", True),
        (1, 0, -1, "H", "D", True),
        (1, 0, -1, "H", "H", False),
        (1, 1, -1, "D", "A", True),
        (0, 1, 1, "A", "D", True),
        (1, 1, 1, "D", "H", True),
        (3, 1, -2, "H", "D", True),
    ],
)
def test_satisfies_handicap(hg, ag, hc, nspf, spf, ok):
    assert s.satisfies(hg, ag, hc, nspf, spf) is ok


def test_impossible_direction_combo_has_empty_mask():
    # 主队让 1 球：客胜必然让负，「客胜 + 让胜」不可能
    assert not s.direction_mask(-1, "A", "H").any()
    # 受让 1 球：主胜必然让胜，「主胜 + 让平」不可能
    assert not s.direction_mask(1, "H", "D").any()
    assert s.direction_mask(-1, "H", "D").any()


def test_market_prior_symmetric_and_normalized():
    lh, la = s.fit_market_lambdas((0.36, 0.28, 0.36), None, None)
    assert abs(lh - la) < 1e-9
    grid = s.poisson_grid(lh, la)
    assert abs(grid.sum() - 1.0) < 1e-9
    strong = s.fit_market_lambdas((0.70, 0.18, 0.12), None, None)
    assert strong[0] > strong[1]


def test_handicap_direction_constraint_applied():
    now = datetime.now()
    rows = [(now - timedelta(days=5 + i % 20), -1, SP_NSPF, SP_SPF, 1, 0) for i in range(40)]
    pool = _make_pool(rows)
    out = s.recommend_top3(_target(), pool, CFG, nspf="H", spf="D")
    assert out["available"]
    assert out["top3"][0]["score"] == "1:0"
    for t in out["top3"]:
        h, a = map(int, t["score"].split(":"))
        assert h - a == 1
    assert out["constraint"]["source"] == {"nspf": "user", "spf": "user"}


def test_user_impossible_combo_reports_reason():
    pool = _make_pool([(datetime.now() - timedelta(days=3), -1, SP_NSPF, SP_SPF, 1, 0)])
    out = s.recommend_top3(_target(), pool, CFG, nspf="A", spf="H")
    assert out["available"] is False
    assert out["top3"] == []


def test_recommend_count_limits_returned_scores():
    empty = _make_pool([])
    wide = dict(CFG)
    wide["recommend_count"] = 5
    out = s.recommend_top3(_target(), empty, wide)
    assert out["available"]
    assert len(out["top3"]) == 5

    narrow = dict(CFG)
    narrow["recommend_count"] = 1
    out = s.recommend_top3(_target(), empty, narrow)
    assert len(out["top3"]) == 1

    with pytest.raises(ValueError):
        s.parse_recommend_count(0)
    with pytest.raises(ValueError):
        s.parse_recommend_count(11)


def test_jingcai_config_changes_score_count(seeded_matches, auth_headers, client):
    try:
        bad = client.put(
            "/api/v1/matches/jingcai/config",
            json={"recommend_score_count": 99},
            headers=auth_headers,
        )
        assert bad.status_code == 400

        saved = client.put(
            "/api/v1/matches/jingcai/config",
            json={"recommend_score_count": 1},
            headers=auth_headers,
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["recommend_score_count"] == 1

        got = client.get("/api/v1/matches/jingcai/config", headers=auth_headers)
        assert got.status_code == 200, got.text
        assert got.json()["recommend_score_count"] == 1
        assert got.json()["default"] == 3

        res = client.get(
            "/api/v1/matches/jingcai/score-top3",
            params={"match_ids": "TOP3-UP"},
            headers=auth_headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["recommend_count"] == 1
        assert len(body["items"][0]["top3"]) == 1
    finally:
        client.put(
            "/api/v1/matches/jingcai/config",
            json={"recommend_score_count": 3},
            headers=auth_headers,
        )


def test_fallback_levels_widen_with_small_pool():
    empty = _make_pool([])
    out = s.recommend_top3(_target(), empty, CFG)
    assert out["fallback_level"] == 3
    assert len(out["top3"]) == 3

    # 只有让球 SP 的样本：双玩法级别没有样本，退到单玩法
    rows = [(datetime.now() - timedelta(days=2 + i), -1, None, SP_SPF, 2, 0) for i in range(20)]
    out = s.recommend_top3(_target(), _make_pool(rows), CFG)
    assert out["fallback_level"] == 1
    assert out["top3"][0]["score"] == "2:0"


def _jc_match(mid, status, result, hg, ag, days_ago):
    from db.models import Match

    return Match(
        id=mid, league_id="EPL", home_team_id="TST-H", away_team_id="TST-A",
        match_date=date.today() - timedelta(days=days_ago), status=status, result=result,
        home_goals=hg, away_goals=ag, handicap=-1,
        odds_nspf_win=1.6, odds_nspf_draw=3.8, odds_nspf_lose=5.0,
        odds_spf_win=2.9, odds_spf_draw=3.4, odds_spf_lose=2.1,
    )


@pytest.fixture
def seeded_matches(client):
    from db.database import SessionLocal
    from db.models import Match

    ids = ["TOP3-FIN", "TOP3-UNSCORED", "TOP3-UP"]
    db = SessionLocal()
    try:
        db.query(Match).filter(Match.id.in_(ids)).delete(synchronize_session=False)
        db.add_all([
            _jc_match("TOP3-FIN", "finished", "H", 2, 0, 3),
            # home_goals 默认 0：未回写赛果的场次不能被当成 0:0 样本
            _jc_match("TOP3-UNSCORED", "upcoming", None, 0, 0, 2),
            _jc_match("TOP3-UP", "upcoming", None, 0, 0, -1),
        ])
        db.commit()
        s.invalidate_pool_cache()
        yield ids
    finally:
        db.query(Match).filter(Match.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        db.close()
        s.invalidate_pool_cache()


def test_pool_only_finished_with_result(seeded_matches):
    from db.database import SessionLocal

    db = SessionLocal()
    try:
        pool = s.load_sample_pool(db, 30)
    finally:
        db.close()
    ids = set(pool.match_ids.tolist())
    assert "TOP3-FIN" in ids
    assert "TOP3-UNSCORED" not in ids
    assert "TOP3-UP" not in ids


def test_pre_match_predictions_exclude_after_kickoff(seeded_matches):
    from db.database import SessionLocal
    from db.models import MatchPrediction

    kickoff = datetime.combine(date.today() - timedelta(days=3), datetime.max.time().replace(microsecond=0))
    db = SessionLocal()
    try:
        db.add_all([
            MatchPrediction(match_id="TOP3-FIN", home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                            lambda_home=1.5, lambda_away=0.9, created_at=kickoff - timedelta(days=1)),
            MatchPrediction(match_id="TOP3-FIN", home_win_prob=0.1, draw_prob=0.2, away_win_prob=0.7,
                            lambda_home=0.6, lambda_away=1.9, created_at=kickoff + timedelta(hours=5)),
        ])
        db.commit()
        preds = s.load_pre_match_predictions(db, {"TOP3-FIN": kickoff, "TOP3-UP": kickoff})
        assert preds["TOP3-FIN"][0] == (0.5, 0.3, 0.2)
        assert "TOP3-UP" not in preds
    finally:
        db.query(MatchPrediction).filter(MatchPrediction.match_id == "TOP3-FIN").delete()
        db.commit()
        db.close()


def test_score_top3_api(seeded_matches, auth_headers, client):
    res = client.get(
        "/api/v1/matches/jingcai/score-top3",
        params={"match_ids": "TOP3-UP,NOPE", "nspf": "H", "spf": "any"},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    items = {it["match_id"]: it for it in body["items"]}
    assert items["TOP3-UP"]["available"] is True
    assert body["recommend_count"] >= 1
    assert 1 <= len(items["TOP3-UP"]["top3"]) <= body["recommend_count"]
    assert items["NOPE"]["available"] is False

    bad = client.get(
        "/api/v1/matches/jingcai/score-top3",
        params={"match_ids": "TOP3-UP", "nspf": "X"},
        headers=auth_headers,
    )
    assert bad.status_code == 400

    model = client.get(
        "/api/v1/matches/jingcai/score-top3",
        params={"match_ids": "TOP3-UP", "nspf": "model", "spf": "model"},
        headers=auth_headers,
    )
    assert model.status_code == 200, model.text
    assert model.json()["items"][0]["model_available"] is False

    bt = client.get("/api/v1/matches/jingcai/score-top3/backtest", params={"days": 30}, headers=auth_headers)
    assert bt.status_code == 200, bt.text
    assert {"modes", "model_subset", "direction_accuracy"} <= set(bt.json())


def test_no_future_samples_used():
    kickoff = datetime.now() + timedelta(days=1)
    target = _target(match_date=kickoff.date(), match_time=kickoff.time())
    future = [(kickoff + timedelta(hours=1 + i), -1, SP_NSPF, SP_SPF, 5, 0) for i in range(30)]
    out = s.recommend_top3(target, _make_pool(future), CFG)
    assert out["samples"]["pool"] == 0
    assert out["fallback_level"] == 3


def test_unusable_bf_and_zero_weights_stay_on_market_prior():
    """缺格、非正数、开赛后快照、权重为 0 时，比分与纯泊松先验一致；不可能的方向仍然拒绝。"""
    from services.odds_snapshot_service import pick_pre_match_bf

    pool = _make_pool([])
    plain = s.recommend_top3(_target(), pool, CFG)
    plain_scores = [(t["score"], t["prob"]) for t in plain["top3"]]

    cfg = dict(CFG)
    cfg["bf_prior_weight"] = 1
    cfg["model_prior_weight"] = 1
    for bad in ({"1:0": 5}, _full_bf(**{"负其它": 0}), _full_bf(**{"负其它": -2})):
        out = s.recommend_top3(_target(), pool, cfg, bf_odds=bad, prediction=((0.6, 0.25, 0.15), None))
        assert out["bf_prior_used"] is False
        assert out["model_prior_used"] is False
        assert [(t["score"], t["prob"]) for t in out["top3"]] == plain_scores

    kickoff = datetime(2026, 10, 20, 20, 0, 0)

    class Row:
        def __init__(self, captured_at, odds_bf_json):
            self.match_id = "T1"
            self.captured_at = captured_at
            self.odds_bf_json = odds_bf_json

    closing = _full_bf(**{"0:1": 1.5})
    picked = pick_pre_match_bf([Row(kickoff + timedelta(minutes=30), closing)], {"T1": kickoff})
    assert picked == {}
    after = s.recommend_top3(
        _target(), pool, cfg, bf_odds=picked.get("T1"), prediction=((0.6, 0.25, 0.15), None),
    )
    assert after["bf_prior_used"] is False
    assert after["model_prior_used"] is False
    assert [(t["score"], t["prob"]) for t in after["top3"]] == plain_scores

    zero = dict(CFG)
    zero["bf_prior_weight"] = 0
    zero["model_prior_weight"] = 0
    held = s.recommend_top3(
        _target(), pool, zero,
        bf_odds=closing,
        prediction=((0.2, 0.2, 0.6), (0.4, 2.8)),
    )
    assert held["bf_prior_used"] is False and held["model_prior_used"] is False
    assert [(t["score"], t["prob"]) for t in held["top3"]] == plain_scores

    blocked = s.recommend_top3(
        _target(), pool, cfg, bf_odds=closing, prediction=((0.2, 0.2, 0.6), (0.4, 2.8)),
        nspf="A", spf="H",
    )
    assert blocked["available"] is False
    assert blocked["top3"] == []


def test_backtest_keeps_finish_gap_before_using_samples():
    """开赛前不足 3 小时的完赛样本不能进入回测；更早的样本可以。"""
    target = datetime.now().replace(microsecond=0) - timedelta(days=1)
    too_close = [(target - timedelta(hours=1), -1, SP_NSPF, SP_SPF, 5, 0) for _ in range(12)]
    too_close.append((target, -1, SP_NSPF, SP_SPF, 1, 0))
    near = s.backtest(None, days=60, overrides=CFG, pool=_make_pool(too_close))
    assert near["fallback_levels"]["0"] == 0
    assert near["fallback_levels"]["3"] == near["test_size"]

    far = [(target - timedelta(days=20 - i), -1, SP_NSPF, SP_SPF, 5, 0) for i in range(12)]
    far.append((target, -1, SP_NSPF, SP_SPF, 1, 0))
    distant = s.backtest(None, days=60, overrides=CFG, pool=_make_pool(far))
    assert distant["fallback_levels"]["0"] >= 1


def test_backtest_rolling_window():
    now = datetime.now()
    rows = [(now - timedelta(days=30 - i), -1, SP_NSPF, SP_SPF, 1, 0) for i in range(30)]
    report = s.backtest(None, days=60, overrides=CFG, pool=_make_pool(rows))
    assert report["test_size"] == 30
    # 第一场无历史样本，必走先验
    assert report["fallback_levels"]["3"] >= 1
    assert report["modes"]["oracle"]["top3"] >= report["modes"]["none"]["top3"]


@pytest.mark.parametrize("lams,hc", [((2.6, 0.5), -1), ((1.3, 1.0), -1), ((0.8, 1.6), 1), ((1.1, 1.1), 0)])
def test_model_directions_compatible(lams, hc):
    probs = (0.5, 0.3, 0.2) if lams[0] > lams[1] else (0.2, 0.3, 0.5)
    nspf, spf = s.model_directions((probs, lams), hc)
    assert nspf == s.OUTCOMES[int(np.argmax(probs))]
    assert spf in s.OUTCOMES
    assert s.direction_mask(hc, nspf, spf).any()


def test_model_directions_strong_home_covers_handicap():
    assert s.model_directions(((0.7, 0.2, 0.1), (2.8, 0.4)), -1) == ("H", "H")
    assert s.model_directions(((0.7, 0.2, 0.1), None), -1) == ("H", None)
    assert s.model_directions(None, -1) == (None, None)


def test_model_direction_requires_prediction():
    rows = [(datetime.now() - timedelta(days=3 + i), -1, SP_NSPF, SP_SPF, 1, 0) for i in range(30)]
    pool = _make_pool(rows)
    out = s.recommend_top3(_target(), pool, CFG, nspf="model", spf="model")
    assert out["model_available"] is False
    assert out["constraint"]["nspf"] is None and out["constraint"]["spf"] is None

    pred = ((0.6, 0.25, 0.15), (1.4, 0.8))
    out = s.recommend_top3(_target(), pool, CFG, nspf="model", spf="model", prediction=pred)
    assert out["model_available"] is True
    assert out["constraint"]["source"]["nspf"] == "model"
    assert out["constraint"]["nspf"] == "H"
    assert out["model"]["nspf"] == "H"


def test_backtest_model_mode_only_counts_predicted():
    now = datetime.now()
    rows = [(now - timedelta(days=30 - i), -1, SP_NSPF, SP_SPF, 1, 0) for i in range(30)]
    pool = _make_pool(rows)
    preds = {f"M{i}": ((0.6, 0.25, 0.15), (1.4, 0.8)) for i in range(0, 30, 3)}
    report = s.backtest(None, days=60, overrides=CFG, pool=pool, predictions=preds)
    assert report["modes"]["model"]["n"] == 10
    assert report["model_subset"]["none"]["n"] == 10
    acc = report["direction_accuracy"]["model"]
    assert acc["n"] == 10 and acc["nspf"] == 1.0


def _tune_report(none_top3, oracle_top3, prior_top3=0.30, prior_oracle_top3=0.80):
    return {
        "modes": {"none": {"top3": none_top3}, "oracle": {"top3": oracle_top3}},
        "baselines": {"prior": {"top3": prior_top3}, "prior_oracle": {"top3": prior_oracle_top3}},
    }


def _full_bf(**overrides):
    sp = {key: 12.0 for key in s.ALL_KEYS}
    sp.update(overrides)
    return sp


def test_bf_implied_grid_requires_complete_positive_sp():
    assert s.bf_implied_grid(None) is None
    assert s.bf_implied_grid({"1:0": 5}) is None
    missing = _full_bf()
    missing["负其它"] = 0
    assert s.bf_implied_grid(missing) is None
    missing["负其它"] = -1
    assert s.bf_implied_grid(missing) is None
    assert s.bf_implied_grid("{") is None


def test_bf_implied_grid_keeps_other_as_one_key():
    sp = _full_bf(**{"1:0": 2.0})
    grid = s.bf_implied_grid(sp)
    assert grid is not None and grid.sum() == pytest.approx(1)
    keys = np.bincount(s._CELL_KEY, weights=grid, minlength=len(s.ALL_KEYS))
    inv = np.array([1.0 / sp[key] for key in s.ALL_KEYS])
    expected = inv / inv.sum()
    assert keys == pytest.approx(expected)
    assert keys[s._KEY_INDEX["胜其它"]] == pytest.approx(expected[s._KEY_INDEX["胜其它"]])
    assert "4:3" not in s.ALL_KEYS


def test_zero_bf_weight_matches_poisson_prior():
    pool = _make_pool([])
    plain = s.recommend_top3(_target(), pool, CFG)
    weighted = dict(CFG)
    weighted["bf_prior_weight"] = 0
    with_bf = s.recommend_top3(_target(), pool, weighted, bf_odds=_full_bf(**{"1:0": 2.0}))
    assert with_bf["bf_prior_used"] is False
    assert [(t["score"], t["prob"]) for t in with_bf["top3"]] == [(t["score"], t["prob"]) for t in plain["top3"]]


def test_bf_prior_applied_after_direction_constraint():
    pool = _make_pool([])
    cfg = dict(CFG)
    cfg["bf_prior_weight"] = 1
    bf = _full_bf(**{"1:0": 2.0, "0:1": 2.2})
    out = s.recommend_top3(_target(), pool, cfg, bf_odds=bf, nspf="H", spf="D")
    assert out["bf_prior_used"] is True
    assert out["top3"][0]["score"] == "1:0"
    for item in out["top3"]:
        if ":" not in item["score"]:
            continue
        home, away = map(int, item["score"].split(":"))
        assert home - away == 1

    blocked = s.recommend_top3(_target(), pool, cfg, bf_odds=bf, nspf="A", spf="H")
    assert blocked["available"] is False
    assert blocked["top3"] == []

    partial = s.recommend_top3(_target(), pool, cfg, bf_odds={"1:0": 2.0})
    plain = s.recommend_top3(_target(), pool, cfg)
    assert partial["bf_prior_used"] is False
    assert [(t["score"], t["prob"]) for t in partial["top3"]] == [
        (t["score"], t["prob"]) for t in plain["top3"]
    ]


def test_backtest_bf_subset_counts_only_complete_pre_match(monkeypatch):
    now = datetime.now()
    rows = [(now - timedelta(days=2), -1, SP_NSPF, SP_SPF, 1, 0)]
    pool = _make_pool(rows)
    captured = {}

    def fake_load(db, kickoffs):
        captured["ids"] = set(kickoffs)
        return {}

    monkeypatch.setattr("services.odds_snapshot_service.load_pre_match_bf", fake_load)
    loaded = s.backtest(object(), days=60, overrides=CFG, pool=pool, predictions={})
    assert captured["ids"] == {"M0"}
    assert loaded["bf_subset"]["n"] == 0

    full = s.backtest(
        None, days=60, overrides=CFG, pool=pool, predictions={},
        bf_by_match={"M0": _full_bf(**{"1:0": 2.0})},
    )
    assert full["bf_subset"]["n"] == 1
    assert full["bf_subset"]["prior"]["n"] == 1
    assert full["bf_subset"]["bf_prior"]["n"] == 1
    assert full["bf_subset"]["bf_prior"]["top1"] == 1

    incomplete = s.backtest(
        None, days=60, overrides=CFG, pool=pool, predictions={},
        bf_by_match={"M0": {"1:0": 2.0}},
    )
    assert incomplete["bf_subset"]["n"] == 0


def test_model_lambda_grid_uses_full_grid_not_truncated_matrix():
    assert s.model_lambda_grid(None) is None
    assert s.model_lambda_grid((0.0, 1.2)) is None
    assert s.model_lambda_grid((1.2,)) is None
    grid = s.model_lambda_grid((4.8, 0.3))
    assert grid is not None and grid.size == s.GRID * s.GRID
    keys = np.bincount(s._CELL_KEY, weights=grid, minlength=len(s.ALL_KEYS))
    assert keys[s._KEY_INDEX["5:0"]] > 0


def test_zero_model_weight_matches_market_prior():
    pool = _make_pool([])
    plain = s.recommend_top3(_target(), pool, CFG)
    cfg = dict(CFG)
    cfg["model_prior_weight"] = 0
    with_lams = s.recommend_top3(
        _target(), pool, cfg, prediction=((0.7, 0.2, 0.1), (4.8, 0.3)),
    )
    assert with_lams["model_prior_used"] is False
    assert [(t["score"], t["prob"]) for t in with_lams["top3"]] == [
        (t["score"], t["prob"]) for t in plain["top3"]
    ]


def test_model_lambda_prior_blends_and_keeps_direction():
    pool = _make_pool([])
    cfg = dict(CFG)
    cfg["model_prior_weight"] = 1
    cfg["bf_prior_weight"] = 0
    out = s.recommend_top3(
        _target(), pool, cfg, prediction=((0.7, 0.2, 0.1), (4.8, 0.3)), nspf="H", spf="H",
    )
    assert out["model_prior_used"] is True
    assert out["top3"]
    for item in out["top3"]:
        if ":" not in item["score"]:
            continue
        home, away = map(int, item["score"].split(":"))
        assert home - away >= 2
    blocked = s.recommend_top3(
        _target(), pool, cfg, prediction=((0.2, 0.2, 0.6), (0.4, 2.4)), nspf="A", spf="H",
    )
    assert blocked["available"] is False

    missing = s.recommend_top3(
        _target(), pool, cfg, prediction=((0.7, 0.2, 0.1), None),
    )
    assert missing["model_prior_used"] is False

    poisson = s.poisson_grid(1.2, 1.0)
    bf = _full_bf(**{"1:0": 2.0})
    mixed, bf_used, model_used = s._blend_market_prior(poisson, bf, 0.6, (3.5, 0.4), 0.6)
    assert bf_used and model_used
    expected = 0.5 * s.bf_implied_grid(bf) + 0.5 * s.model_lambda_grid((3.5, 0.4))
    assert mixed == pytest.approx(expected)


def test_backtest_model_lambda_subset_needs_pre_match_lams():
    now = datetime.now()
    rows = [(now - timedelta(days=2), -1, SP_NSPF, SP_SPF, 1, 0)]
    pool = _make_pool(rows)
    with_lams = s.backtest(
        None, days=60, overrides=CFG, pool=pool,
        predictions={"M0": ((0.55, 0.25, 0.2), (1.6, 0.9))},
    )
    assert with_lams["model_lambda_subset"]["n"] == 1
    assert with_lams["model_lambda_subset"]["none"]["n"] == 1
    assert with_lams["model_lambda_subset"]["model_prior"]["n"] == 1

    no_lams = s.backtest(
        None, days=60, overrides=CFG, pool=pool,
        predictions={"M0": ((0.55, 0.25, 0.2), None)},
    )
    assert no_lams["model_lambda_subset"]["n"] == 0


def _gate_report(bf_top3, bf_base, model_top3, model_base, n_bf=12, n_model=8):
    def stats(top3, n):
        return {"n": n, "top3": top3}
    return {
        "bf_subset": {"n": n_bf, "bf_prior": stats(bf_top3, n_bf), "prior": stats(bf_base, n_bf)},
        "model_lambda_subset": {
            "n": n_model,
            "model_prior": stats(model_top3, n_model),
            "none": stats(model_base, n_model),
        },
    }


def test_prior_weight_decision_requires_both_windows_and_both_paths():
    weak = _gate_report(0.40, 0.30, 0.20, 0.32)
    strong = _gate_report(0.42, 0.30, 0.40, 0.32)
    both = s.prior_weight_decision(strong, strong)
    assert both == {"bf_prior_weight": 1.0, "model_prior_weight": 1.0, "retune_alpha": True}

    only_bf = s.prior_weight_decision(strong, weak)
    assert only_bf["bf_prior_weight"] == 1.0
    assert only_bf["model_prior_weight"] == 0.0
    assert only_bf["retune_alpha"] is False

    bf_short = _gate_report(0.30, 0.30, 0.40, 0.32)
    one_window_short = s.prior_weight_decision(strong, bf_short)
    assert one_window_short["bf_prior_weight"] == 0.0
    assert one_window_short["model_prior_weight"] == 1.0
    assert one_window_short["retune_alpha"] is False

    tied = s.prior_weight_decision(_gate_report(0.305, 0.30, 0.325, 0.32))
    assert tied["bf_prior_weight"] == 0.0 and tied["model_prior_weight"] == 0.0

    empty = s.prior_weight_decision(_gate_report(0.9, 0.1, 0.9, 0.1, n_bf=0, n_model=0))
    assert empty["retune_alpha"] is False
    assert s.prior_weight_decision()["retune_alpha"] is False


def test_tune_row_advice_blocks_lower_alpha_until_both_weights_pass():
    lower = {"params": {"smoothing_alpha": 40}, "modes": {"none": {"top3": 0.40}}, "baselines": {"prior": {"top3": 0.30}}}
    same = {"params": {"smoothing_alpha": 80}, "modes": {"none": {"top3": 0.40}}, "baselines": {"prior": {"top3": 0.30}}}
    assert s.tune_row_advice(lower, retune_alpha=False, current_alpha=80) == "暂不下调 α"
    assert s.tune_row_advice(same, retune_alpha=False, current_alpha=80) == "可考虑"
    assert s.tune_row_advice(lower, retune_alpha=True, current_alpha=80) == "可考虑"
    flat = {"params": {"smoothing_alpha": 80}, "modes": {"none": {"top3": 0.30}}, "baselines": {"prior": {"top3": 0.30}}}
    assert s.tune_row_advice(flat, retune_alpha=True, current_alpha=80) == "未超过先验"


def test_rank_tune_results_prefers_unconstrained_delta_then_oracle():
    low_delta = ({"k": 1}, _tune_report(0.32, 0.90))
    high_delta = ({"k": 2}, _tune_report(0.40, 0.81))
    tie_better_oracle = ({"k": 3}, _tune_report(0.40, 0.85))
    eligible, rejected = s.rank_tune_results([low_delta, high_delta, tie_better_oracle])
    assert rejected == []
    assert [item[0]["k"] for item in eligible] == [3, 2, 1]
    assert s.tune_none_delta(high_delta[1]) == pytest.approx(0.10)


def test_rank_tune_results_rejects_oracle_below_prior():
    worse = ({"k": 1}, _tune_report(0.50, 0.70))
    tied = ({"k": 2}, _tune_report(0.31, 0.80))
    missing = ({"k": 3}, _tune_report(None, 0.90))
    eligible, rejected = s.rank_tune_results([worse, tied, missing])
    assert [item[0]["k"] for item in eligible] == [2]
    assert {item[0]["k"] for item in rejected} == {1, 3}
    assert s.tune_oracle_gap(worse[1]) == pytest.approx(-0.10)


def test_mask_score_top3_for_free_users():
    items = [{"top3": [{"score": "1:0"}, {"score": "2:0"}, {"score": "2:1"}], "hit": True}]
    masked = mask_score_top3_list(items, set())
    assert len(masked[0]["top3"]) == 1
    assert masked[0]["top3_locked"] is True
    assert masked[0]["hit"] is None
    full = [{"top3": [{"score": "1:0"}, {"score": "2:0"}]}]
    assert len(mask_score_top3_list(full, {FEATURE_JINGCAI_BF})[0]["top3"]) == 2
