"""模拟预测（未来赛事比分推演）回归测试。"""

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

MATCH_ID = "SIM-TEST-001"
HOME_ID = "SIM-H"
AWAY_ID = "SIM-A"
LEAGUE_ID = "SIMLG"


def _seed(db):
    from db.models import League, Team, Match

    db.query(Match).filter(Match.id == MATCH_ID).delete(synchronize_session=False)
    db.query(Team).filter(Team.id.in_([HOME_ID, AWAY_ID])).delete(synchronize_session=False)
    db.query(League).filter(League.id == LEAGUE_ID).delete(synchronize_session=False)

    db.add(League(id=LEAGUE_ID, name="模拟联赛", avg_goals=2.80))
    db.add(Team(id=HOME_ID, name="模拟主队", short_name="模拟主", league_id=LEAGUE_ID,
                elo_rating=1600, attack_strength=1.20, defense_strength=0.85,
                xg_for=1.60, xg_against=1.00))
    db.add(Team(id=AWAY_ID, name="模拟客队", short_name="模拟客", league_id=LEAGUE_ID,
                elo_rating=1500, attack_strength=1.00, defense_strength=1.00,
                xg_for=1.20, xg_against=1.30))
    db.add(Match(
        id=MATCH_ID, league_id=LEAGUE_ID, home_team_id=HOME_ID, away_team_id=AWAY_ID,
        match_date=date.today() + timedelta(days=2), status="upcoming",
        match_no="周六001", handicap=-1,
        odds_spf_win=1.80, odds_spf_draw=3.40, odds_spf_lose=4.20,
        odds_nspf_win=2.60, odds_nspf_draw=3.30, odds_nspf_lose=2.30,
        odds_bf_json=json.dumps({"1:0": 7.5, "2:1": 8.5, "0:0": 10.0, "1:1": 6.5, "0:1": 12.0}),
    ))
    db.commit()


def _cleanup(db):
    from db.models import League, Team, Match

    db.query(Match).filter(Match.id == MATCH_ID).delete(synchronize_session=False)
    db.query(Team).filter(Team.id.in_([HOME_ID, AWAY_ID])).delete(synchronize_session=False)
    db.query(League).filter(League.id == LEAGUE_ID).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def seeded(client):
    from db.database import SessionLocal
    from services import simulation_cache

    simulation_cache.clear()
    db = SessionLocal()
    try:
        _seed(db)
        yield
    finally:
        _cleanup(db)
        simulation_cache.clear()
        db.close()


def test_simulate_baseline_only(client: TestClient, seeded, auth_headers):
    """无 overrides：基线与模拟一致，delta 全 0，不落库。"""
    from db.database import SessionLocal
    from db.models import MatchPrediction

    res = client.post(
        "/api/v1/predictions/simulate",
        json={"match_id": MATCH_ID, "simulations": 2000, "seed": 42},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["match"]["id"] == MATCH_ID
    assert body["match"]["status"] == "upcoming"
    assert body["home"]["id"] == HOME_ID and body["away"]["id"] == AWAY_ID

    base, sim = body["baseline"], body["simulated"]
    assert base["home_win_prob"] == sim["home_win_prob"]
    assert base["lambda_home"] == sim["lambda_home"]
    for v in body["delta"].values():
        assert v == 0

    mc = sim["mc"]
    assert mc["simulations"] == 2000 and mc["seed"] == 42
    assert len(mc["score_matrix"]) == mc["score_matrix_size"] == 9
    assert len(mc["goal_distribution"]) == 11
    assert 0 <= mc["over_2_5_prob"] <= 1
    assert len(sim["scenarios"]) >= 4

    # 奖金分析挂载：赛事有真实胜平负/让球/比分赔率
    prize = body["prize"]
    assert prize["sp_source"]["spf"] == "real"
    assert prize["sp_source"]["nspf"] == "real"
    assert prize["sp_source"]["bf"] == "real"
    assert prize["sp_source"]["tg"] == "synthetic"
    assert prize["nspf"]["handicap"] == -1
    assert prize["disclaimer"]
    assert body["meta"]["applied_overrides"] == []

    # 只读：不产生预测记录
    db = SessionLocal()
    try:
        assert db.query(MatchPrediction).filter(MatchPrediction.match_id == MATCH_ID).count() == 0
    finally:
        db.close()


def test_simulate_reproducible_with_seed(client: TestClient, seeded, auth_headers):
    payload = {"match_id": MATCH_ID, "simulations": 2000, "seed": 7}
    r1 = client.post("/api/v1/predictions/simulate", json=payload, headers=auth_headers)
    r2 = client.post("/api/v1/predictions/simulate", json=payload, headers=auth_headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["simulated"]["mc"]["score_matrix"] == r2.json()["simulated"]["mc"]["score_matrix"]


def test_simulate_with_overrides_changes_result(client: TestClient, seeded, auth_headers):
    res = client.post(
        "/api/v1/predictions/simulate",
        json={
            "match_id": MATCH_ID,
            "simulations": 2000,
            "seed": 42,
            "overrides": {
                "lambda_home": 2.5,
                "lambda_away": 0.8,
                "weights": {"elo": 0.25, "poisson": 0.35, "xg": 0.25, "monte_carlo": 0.15},
            },
        },
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["simulated"]["lambda_home"] == pytest.approx(2.5, abs=0.05)
    assert body["simulated"]["lambda_away"] == pytest.approx(0.8, abs=0.05)
    # 显式权重生效（与基线不同，且归一化后总和≈1）
    assert body["simulated"]["weights_used"] != body["baseline"]["weights_used"]
    assert abs(sum(body["simulated"]["weights_used"].values()) - 1.0) < 1e-3
    assert body["delta"]["lambda_home"] != 0
    assert set(body["meta"]["applied_overrides"]) == {"lambda_home", "lambda_away", "weights"}
    # 覆盖 λ 后主胜概率应高于基线
    assert body["simulated"]["home_win_prob"] > body["baseline"]["home_win_prob"]


def test_simulate_rejects_non_upcoming(client: TestClient, seeded, auth_headers):
    from db.database import SessionLocal
    from db.models import Match

    db = SessionLocal()
    try:
        db.query(Match).filter(Match.id == MATCH_ID).update({"status": "finished"}, synchronize_session=False)
        db.commit()
    finally:
        db.close()

    res = client.post(
        "/api/v1/predictions/simulate",
        json={"match_id": MATCH_ID, "simulations": 1000},
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "upcoming" in res.json()["detail"]


def test_simulate_match_not_found(client: TestClient, seeded, auth_headers):
    res = client.post(
        "/api/v1/predictions/simulate",
        json={"match_id": "SIM-NOT-EXIST", "simulations": 1000},
        headers=auth_headers,
    )
    assert res.status_code == 404


def test_simulate_rejects_zero_weights(client: TestClient, seeded, auth_headers):
    res = client.post(
        "/api/v1/predictions/simulate",
        json={
            "match_id": MATCH_ID,
            "simulations": 1000,
            "overrides": {"weights": {"elo": 0, "poisson": 0, "xg": 0, "monte_carlo": 0}},
        },
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "权重" in res.json()["detail"]


def test_simulate_manual_sp_overrides(client: TestClient, seeded, auth_headers):
    """结构化 manual_sp：覆盖真实赔率，来源标记 manual。"""
    res = client.post(
        "/api/v1/predictions/simulate",
        json={
            "match_id": MATCH_ID,
            "simulations": 1000,
            "seed": 42,
            "overrides": {
                "manual_sp": {
                    "spf": {"win": 2.0, "draw": 3.5, "lose": 3.8},
                    "bf": {"1:0": 6.0, "胜其它": 20.0},
                    "tg": {"3": 4.2},
                },
            },
        },
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    prize = res.json()["prize"]
    assert prize["sp_source"]["spf"] == "manual"
    assert prize["spf"]["sp"]["win"] == 2.0
    assert prize["sp_source"]["bf"] == "manual"
    assert prize["sp_source"]["tg"] == "manual"
    # 未覆盖的玩法仍走真实赔率
    assert prize["sp_source"]["nspf"] == "real"


def test_simulate_manual_sp_rejects_invalid(client: TestClient, seeded, auth_headers):
    """非法选项键 / 非正 SP 均 422。"""
    res = client.post(
        "/api/v1/predictions/simulate",
        json={
            "match_id": MATCH_ID,
            "simulations": 1000,
            "overrides": {"manual_sp": {"bf": {"9:9": 100.0}}},
        },
        headers=auth_headers,
    )
    assert res.status_code == 422

    res = client.post(
        "/api/v1/predictions/simulate",
        json={
            "match_id": MATCH_ID,
            "simulations": 1000,
            "overrides": {"manual_sp": {"spf": {"win": -1}}},
        },
        headers=auth_headers,
    )
    assert res.status_code == 422


def test_simulate_validation_bounds(client: TestClient, seeded, auth_headers):
    res = client.post(
        "/api/v1/predictions/simulate",
        json={"match_id": MATCH_ID, "simulations": 100},
        headers=auth_headers,
    )
    assert res.status_code == 422

    res = client.post(
        "/api/v1/predictions/simulate",
        json={"match_id": MATCH_ID, "simulations": 1000, "overrides": {"lambda_home": 9.9}},
        headers=auth_headers,
    )
    assert res.status_code == 422


def test_simulate_rejects_invalid_env_enum(client: TestClient, seeded, auth_headers):
    """非法 weather / pitch_condition 须 422（否则 λ_factor 静默为 1）。"""
    res = client.post(
        "/api/v1/predictions/simulate",
        json={"match_id": MATCH_ID, "simulations": 1000, "overrides": {"weather": "中雨"}},
        headers=auth_headers,
    )
    assert res.status_code == 422

    res = client.post(
        "/api/v1/predictions/simulate",
        json={"match_id": MATCH_ID, "simulations": 1000, "overrides": {"pitch_condition": "湿滑"}},
        headers=auth_headers,
    )
    assert res.status_code == 422


def test_simulate_valid_env_enum_applied(client: TestClient, seeded, auth_headers):
    res = client.post(
        "/api/v1/predictions/simulate",
        json={"match_id": MATCH_ID, "simulations": 1000, "seed": 42,
              "overrides": {"weather": "大雨", "pitch_condition": "较差"}},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    assert set(res.json()["meta"]["applied_overrides"]) == {"weather", "pitch_condition"}
    # 恶劣环境应下调 λ
    assert res.json()["simulated"]["lambda_home"] < res.json()["baseline"]["lambda_home"]


def test_simulate_concurrency_limit(client: TestClient, seeded, auth_headers):
    """并发占满信号量时应返回 429。"""
    from api import predictions as pred_api

    for _ in range(pred_api._SIMULATE_MAX_CONCURRENCY):
        assert pred_api._SIMULATE_SEMAPHORE.acquire(blocking=False)
    try:
        res = client.post(
            "/api/v1/predictions/simulate",
            json={"match_id": MATCH_ID, "simulations": 1000},
            headers=auth_headers,
        )
        assert res.status_code == 429
        assert "繁忙" in res.json()["detail"]
    finally:
        for _ in range(pred_api._SIMULATE_MAX_CONCURRENCY):
            pred_api._SIMULATE_SEMAPHORE.release()


def test_simulate_requires_permission(client: TestClient, seeded):
    """无 token 直接 401/403。"""
    res = client.post(
        "/api/v1/predictions/simulate",
        json={"match_id": MATCH_ID, "simulations": 1000},
    )
    assert res.status_code in (401, 403)


# ---------- 低优先级：缓存 / 敏感性 / 批量串关 / 历史 ----------

MATCH2_ID = "SIM-TEST-002"


def _seed_second_match(db):
    from db.models import Match

    db.query(Match).filter(Match.id == MATCH2_ID).delete(synchronize_session=False)
    db.add(Match(
        id=MATCH2_ID, league_id=LEAGUE_ID, home_team_id=HOME_ID, away_team_id=AWAY_ID,
        match_date=date.today() + timedelta(days=3), status="upcoming",
        match_no="周日001",
        odds_spf_win=2.10, odds_spf_draw=3.20, odds_spf_lose=3.50,
    ))
    db.commit()


def _cleanup_second_match(db):
    from db.models import Match

    db.query(Match).filter(Match.id == MATCH2_ID).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def seeded_two(client, seeded):
    from db.database import SessionLocal

    db = SessionLocal()
    try:
        _seed_second_match(db)
        yield
    finally:
        _cleanup_second_match(db)
        db.close()


def test_simulate_cache_hit(client: TestClient, seeded, auth_headers):
    """相同参数重复请求：第二次命中缓存（meta.cache_hit=True），结果一致。"""
    payload = {"match_id": MATCH_ID, "simulations": 1000, "seed": 42}
    r1 = client.post("/api/v1/predictions/simulate", json=payload, headers=auth_headers)
    assert r1.status_code == 200, r1.text
    assert r1.json()["meta"]["cache_hit"] is False

    r2 = client.post("/api/v1/predictions/simulate", json=payload, headers=auth_headers)
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["meta"]["cache_hit"] is True
    assert body2["simulated"]["home_win_prob"] == r1.json()["simulated"]["home_win_prob"]

    # 参数不同则不命中
    r3 = client.post(
        "/api/v1/predictions/simulate",
        json={"match_id": MATCH_ID, "simulations": 1000, "seed": 43},
        headers=auth_headers,
    )
    assert r3.status_code == 200
    assert r3.json()["meta"]["cache_hit"] is False


def test_sensitivity_lambda_scan(client: TestClient, seeded, auth_headers):
    """λ 敏感性：主/客各 7 个扫描点，主 λ 增大 → 主胜概率单调不降。"""
    res = client.post(
        "/api/v1/predictions/simulate/sensitivity",
        json={"match_id": MATCH_ID, "simulations": 1000, "seed": 42},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["match"]["id"] == MATCH_ID
    for key in ("lambda_home", "lambda_away"):
        s = body["series"][key]
        assert s["base"] > 0
        assert len(s["points"]) == 7
        for p in s["points"]:
            assert 0 <= p["home_win_prob"] <= 1
            assert abs(p["home_win_prob"] + p["draw_prob"] + p["away_win_prob"] - 1) < 0.02

    home_pts = body["series"]["lambda_home"]["points"]
    assert home_pts[-1]["home_win_prob"] > home_pts[0]["home_win_prob"]
    away_pts = body["series"]["lambda_away"]["points"]
    assert away_pts[-1]["away_win_prob"] > away_pts[0]["away_win_prob"]


def test_batch_simulate_with_parlay(client: TestClient, seeded_two, auth_headers):
    """批量模拟 2 场：逐场结果 + 2串1 组合奖金（3^2=9 组合）。"""
    res = client.post(
        "/api/v1/predictions/simulate/batch",
        json={"match_ids": [MATCH_ID, MATCH2_ID], "simulations": 1000, "seed": 42},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["meta"]["succeeded"] == 2 and body["meta"]["failed"] == 0
    assert [r["match"]["id"] for r in body["results"]] == [MATCH_ID, MATCH2_ID]

    parlay = body["parlay"]
    assert parlay is not None
    assert parlay["legs"] == 2
    assert parlay["total_combos"] == 9
    assert len(parlay["top_combos"]) == 9
    for c in parlay["top_combos"]:
        assert len(c["picks"]) == 2
        assert c["payout"] <= parlay["payout_cap"]
        assert c["payout"] >= 0
    assert abs(parlay["total_prob"] - 1.0) < 0.02
    assert parlay["disclaimer"]


def test_batch_simulate_partial_failure(client: TestClient, seeded, auth_headers):
    """1 场有效 + 1 场不存在：成功 1 场，错误列表非空，不足 2 场无串关。"""
    res = client.post(
        "/api/v1/predictions/simulate/batch",
        json={"match_ids": [MATCH_ID, "SIM-NOT-EXIST"], "simulations": 1000},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["meta"]["succeeded"] == 1 and body["meta"]["failed"] == 1
    assert body["errors"][0]["match_id"] == "SIM-NOT-EXIST"
    assert body["parlay"] is None


def test_batch_simulate_validation(client: TestClient, seeded, auth_headers):
    """<2 场或 >8 场均 422。"""
    res = client.post(
        "/api/v1/predictions/simulate/batch",
        json={"match_ids": [MATCH_ID], "simulations": 1000},
        headers=auth_headers,
    )
    assert res.status_code == 422

    res = client.post(
        "/api/v1/predictions/simulate/batch",
        json={"match_ids": [f"M{i}" for i in range(9)], "simulations": 1000},
        headers=auth_headers,
    )
    assert res.status_code == 422


def test_simulate_history_saved_and_listed(client: TestClient, seeded, auth_headers):
    """模拟后写入历史，列表端点可回看参数与摘要。"""
    res = client.post(
        "/api/v1/predictions/simulate",
        json={"match_id": MATCH_ID, "simulations": 1000, "seed": 42,
              "overrides": {"lambda_home": 2.0}},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text

    hist = client.get("/api/v1/predictions/simulate/history", headers=auth_headers)
    assert hist.status_code == 200, hist.text
    rows = hist.json()["history"]
    assert rows, "模拟后应有历史记录"
    row = rows[0]
    assert row["match_id"] == MATCH_ID
    assert row["simulations"] == 1000 and row["seed"] == 42
    assert row["params"].get("lambda_home") == 2.0
    assert 0 <= row["summary"]["home_win_prob"] <= 1
    assert row["summary"]["main_score"]
    assert row["match_name"]

    # 按赛事过滤
    filtered = client.get(
        "/api/v1/predictions/simulate/history",
        params={"match_id": "OTHER-MATCH"},
        headers=auth_headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["history"] == []


def test_history_trimmed_to_limit():
    """历史上限：超过 50 条时裁剪最旧记录。"""
    from db.database import SessionLocal
    from db.models import SimulationHistory
    from services.simulation_service import _trim_history, HISTORY_LIMIT

    db = SessionLocal()
    try:
        db.query(SimulationHistory).delete(synchronize_session=False)
        db.commit()
        for i in range(HISTORY_LIMIT + 5):
            db.add(SimulationHistory(
                match_id=f"TRIM-{i}", match_name=f"t{i}",
                simulations=1000, params_json="{}", summary_json="{}",
            ))
        db.commit()
        _trim_history(db)
        assert db.query(SimulationHistory).count() == HISTORY_LIMIT
        db.query(SimulationHistory).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_parlay_calculator_unit():
    """串关计算器单元校验：概率乘积 / 奖金乘积 / 上限截断。"""
    from services.parlay_calculator import calculate_parlay, PAYOUT_CAP_PARLAY

    legs = [
        {"match_id": "A", "match_name": "A", "probs": {"win": 0.5, "draw": 0.3, "lose": 0.2},
         "spf": {"win": 2.0, "draw": 3.0, "lose": 4.0}},
        {"match_id": "B", "match_name": "B", "probs": {"win": 0.4, "draw": 0.35, "lose": 0.25},
         "spf": {"win": 2.5, "draw": 3.2, "lose": 3.0}},
    ]
    out = calculate_parlay(legs)
    assert out["legs"] == 2 and out["total_combos"] == 9
    top = out["top_combos"][0]
    assert top["picks"] == ["主胜", "主胜"]
    assert top["prob"] == pytest.approx(0.2, abs=1e-4)
    assert top["payout"] == pytest.approx(2.0 * 2.0 * 2.5, abs=0.01)

    # SP 缺失 → ValueError；场数越界 → ValueError
    import pytest as _pt
    with _pt.raises(ValueError):
        calculate_parlay([{"match_id": "A", "probs": {"win": 1}, "spf": {"win": 2.0}}])
    with _pt.raises(ValueError):
        calculate_parlay(legs * 5)  # 10 场 > 8

    # 上限截断
    huge = [
        {"match_id": str(i), "match_name": str(i),
         "probs": {"win": 0.9, "draw": 0.05, "lose": 0.05},
         "spf": {"win": 50.0, "draw": 10.0, "lose": 10.0}}
        for i in range(8)
    ]
    out8 = calculate_parlay(huge)
    assert out8["legs"] == 8
    assert all(c["payout"] <= PAYOUT_CAP_PARLAY for c in out8["top_combos"])
