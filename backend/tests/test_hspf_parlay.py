"""§12-6 半场胜平负 & §12-7 串关落单。

覆盖：
- hspf 半场胜平负命中判定（_hit_hspf 解析 half_score）
- 串关组合整体结算（全中 → 2×∏sp×倍数封顶；任一未中 → 整组 lost）
- 串关 API 创建（POST /simulation/bets/parlay）与组合分组
- parlay_calculator.calculate_parlay_picks 全玩法选项
- 只读边界：串关创建不写 predictions 表

仅供学习、研究、数据分析，不构成投注建议，不接入真实资金。
"""

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from services.parlay_calculator import calculate_parlay_picks

BASE_DATE = date.today() + timedelta(days=2)


def _seed_match(db, mid, home_id, away_id, league_id, mh="周五001", handicap=0,
                half_score=None, hspf_win=2.0, hspf_draw=3.2, hspf_lose=4.5):
    from db.models import Match

    db.add(Match(
        id=mid, league_id=league_id, home_team_id=home_id, away_team_id=away_id,
        match_date=BASE_DATE, status="upcoming", match_no=mh, handicap=handicap,
        odds_spf_win=1.80, odds_spf_draw=3.40, odds_spf_lose=4.20,
        odds_nspf_win=2.60, odds_nspf_draw=3.30, odds_nspf_lose=2.30,
        odds_bf_json=json.dumps({"1:0": 7.5, "2:1": 8.5, "0:0": 10.0, "1:1": 6.5, "0:1": 12.0}),
        odds_hspf_win=hspf_win, odds_hspf_draw=hspf_draw, odds_hspf_lose=hspf_lose,
        half_score=half_score,
    ))


@pytest.fixture
def parlay_seed(client):
    from db.database import SessionLocal
    from db.models import League, Match, Team, SimulationBet

    db = SessionLocal()
    try:
        db.query(SimulationBet).delete(synchronize_session=False)
        db.query(Match).filter(Match.id.in_(["HP-M1", "HP-M2", "HP-M3"])).delete(synchronize_session=False)
        db.query(Team).filter(Team.id.in_(["HP-H1", "HP-A1", "HP-H2", "HP-A2", "HP-H3", "HP-A3"])).delete(synchronize_session=False)
        db.query(League).filter(League.id == "HP-LG").delete(synchronize_session=False)

        db.add(League(id="HP-LG", name="半场串关联赛", avg_goals=2.80))
        for hid, aid, name, elo in (("HP-H1", "HP-A1", "主A", 1600), ("HP-H2", "HP-A2", "主B", 1550), ("HP-H3", "HP-A3", "主C", 1580)):
            db.add(Team(id=hid, name=name, short_name=name, league_id="HP-LG",
                        elo_rating=elo, attack_strength=1.20, defense_strength=0.85,
                        xg_for=1.60, xg_against=1.00))
            db.add(Team(id=aid, name=name + "客", short_name=name + "客", league_id="HP-LG",
                        elo_rating=1500, attack_strength=1.00, defense_strength=1.00,
                        xg_for=1.20, xg_against=1.30))
        _seed_match(db, "HP-M1", "HP-H1", "HP-A1", "HP-LG", "周六001", half_score="1 - 0")
        _seed_match(db, "HP-M2", "HP-H2", "HP-A2", "HP-LG", "周六002", half_score="0-0")
        _seed_match(db, "HP-M3", "HP-H3", "HP-A3", "HP-LG", "周六003", half_score="0-1")
        db.commit()
        yield
    finally:
        db.query(SimulationBet).delete(synchronize_session=False)
        db.query(Match).filter(Match.id.in_(["HP-M1", "HP-M2", "HP-M3"])).delete(synchronize_session=False)
        db.query(Team).filter(Team.id.in_(["HP-H1", "HP-A1", "HP-H2", "HP-A2", "HP-H3", "HP-A3"])).delete(synchronize_session=False)
        db.query(League).filter(League.id == "HP-LG").delete(synchronize_session=False)
        db.commit()
        db.close()


def _finish(db, mid, status="finished", hg=1, ag=0, result="H", half_score="1 - 0"):
    from db.models import Match
    db.query(Match).filter(Match.id == mid).update(
        {"status": status, "home_goals": hg, "away_goals": ag, "result": result, "half_score": half_score},
        synchronize_session=False,
    )


# ---- hspf 命中判定 ----

def test_hit_hspf_win_draw_lose():
    """半场比分 → hspf 选项命中判定（win/draw/lose）。"""
    from types import SimpleNamespace

    from services.simulation_bet_service import _hit_hspf

    m = SimpleNamespace(half_score="1 - 0")
    assert _hit_hspf("win", m) is True
    assert _hit_hspf("draw", m) is False
    assert _hit_hspf("lose", m) is False

    m2 = SimpleNamespace(half_score="0-0")
    assert _hit_hspf("draw", m2) is True
    assert _hit_hspf("win", m2) is False

    m3 = SimpleNamespace(half_score="2-3")
    assert _hit_hspf("lose", m3) is True


def test_hit_hspf_missing_raises():
    """半场比分缺失 → ValueError（触发失败计数）。"""
    from types import SimpleNamespace

    from services.simulation_bet_service import _hit_hspf

    with pytest.raises(ValueError):
        _hit_hspf("win", SimpleNamespace(half_score=""))
    with pytest.raises(ValueError):
        _hit_hspf("win", SimpleNamespace(half_score="1-0-2"))


# ---- hspf 采集边际推导 ----

def test_derive_hspf_from_hh():
    """半全场 9 项边际推导半场三选一 SP。"""
    from services.real_crawler import RealMatchCrawler

    hh = {
        "胜胜": 3.00, "胜平": 8.50, "胜负": 18.00,
        "平胜": 4.50, "平平": 5.20, "平负": 8.00,
        "负胜": 15.00, "负平": 8.00, "负负": 3.50,
    }
    win, draw, lose = RealMatchCrawler._derive_hspf_from_hh(hh)
    assert win > 1.0 and draw > 1.0 and lose > 1.0
    # 概率和为 1 附近：主胜边际应明显高于客胜（该场 3.0 vs 3.5 相近）
    assert abs(1 / win + 1 / draw + 1 / lose - 1) < 0.05


# ---- 串关组合整体结算 ----

def test_parlay_all_hit_settles_won(client, parlay_seed, auth_headers):
    """串关全部命中 → 整组 won，奖金 = min(2×∏sp×倍数, 封顶)。"""
    from db.database import SessionLocal
    from db.models import SimulationBet
    from services.simulation_bet_service import settle_pending

    res = client.post(
        "/api/v1/simulation/bets/parlay",
        json={
            "legs": [
                {"match_id": "HP-M1", "play_type": "hspf", "selection": "win", "sp": 2.00, "sp_source": "real"},
                {"match_id": "HP-M2", "play_type": "hspf", "selection": "draw", "sp": 3.20, "sp_source": "real"},
            ],
            "stake": 2.0, "multiple": 1,
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    data = res.json()
    cid = data["combination_id"]
    assert cid.startswith("pl_")
    assert len(data["legs"]) == 2
    assert all(l["is_parlay"] for l in data["legs"])
    assert all(l["combination_id"] == cid for l in data["legs"])

    # 结算：两场都 finished，半场比分 1-0(H) / 0-0(D) → 全中
    db = SessionLocal()
    try:
        _finish(db, "HP-M1", hg=2, ag=1, result="H", half_score="1 - 0")
        _finish(db, "HP-M2", hg=1, ag=1, result="D", half_score="0-0")
        db.commit()
    finally:
        db.close()

    settle_pending(SessionLocal())
    db = SessionLocal()
    try:
        rows = db.query(SimulationBet).filter(SimulationBet.combination_id == cid).all()
        assert len(rows) == 2
        for r in rows:
            assert r.status == "won"
        # 2 × 2.00 × 3.20 × 1 = 12.80
        assert abs(float(rows[0].payout) - 12.80) < 0.01
        assert abs(float(rows[1].payout) - 12.80) < 0.01
    finally:
        db.close()


def test_parlay_one_lost_settles_lost(client, parlay_seed, auth_headers):
    """串关任一 leg 未中 → 整组 lost，奖金 0。"""
    from db.database import SessionLocal
    from db.models import SimulationBet
    from services.simulation_bet_service import settle_pending

    res = client.post(
        "/api/v1/simulation/bets/parlay",
        json={
            "legs": [
                {"match_id": "HP-M1", "play_type": "hspf", "selection": "win", "sp": 2.00, "sp_source": "real"},
                {"match_id": "HP-M2", "play_type": "hspf", "selection": "lose", "sp": 4.50, "sp_source": "real"},
            ],
            "stake": 2.0, "multiple": 1,
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    cid = res.json()["combination_id"]

    db = SessionLocal()
    try:
        # M1 半场 1-0 主胜(win 中)，M2 半场 0-0 平(lose 未中) → 整组 lost
        _finish(db, "HP-M1", hg=2, ag=1, result="H", half_score="1 - 0")
        _finish(db, "HP-M2", hg=1, ag=1, result="D", half_score="0-0")
        db.commit()
    finally:
        db.close()

    settle_pending(SessionLocal())
    db = SessionLocal()
    try:
        rows = db.query(SimulationBet).filter(SimulationBet.combination_id == cid).all()
        for r in rows:
            assert r.status == "lost"
            assert r.payout == 0
    finally:
        db.close()


def test_parlay_payout_cap(client, parlay_seed, auth_headers):
    """串关奖金封顶 PAYOUT_CAP_PARLAY=500000。"""
    from db.database import SessionLocal
    from db.models import SimulationBet
    from services.simulation_bet_service import settle_pending

    # 3 腿高 SP：2 × 50 × 50 × 50 = 250000 < 500000 未超；改 2×100×100×100=2000000 > 封顶
    res = client.post(
        "/api/v1/simulation/bets/parlay",
        json={
            "legs": [
                {"match_id": "HP-M1", "play_type": "hspf", "selection": "win", "sp": 100.0, "sp_source": "real"},
                {"match_id": "HP-M2", "play_type": "hspf", "selection": "draw", "sp": 100.0, "sp_source": "real"},
                {"match_id": "HP-M3", "play_type": "hspf", "selection": "lose", "sp": 100.0, "sp_source": "real"},
            ],
            "stake": 2.0, "multiple": 1,
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    cid = res.json()["combination_id"]

    db = SessionLocal()
    try:
        _finish(db, "HP-M1", hg=2, ag=1, result="H", half_score="1 - 0")
        _finish(db, "HP-M2", hg=1, ag=1, result="D", half_score="0-0")
        _finish(db, "HP-M3", hg=0, ag=1, result="A", half_score="0-1")
        db.commit()
    finally:
        db.close()

    settle_pending(SessionLocal())
    db = SessionLocal()
    try:
        rows = db.query(SimulationBet).filter(SimulationBet.combination_id == cid).all()
        for r in rows:
            assert r.status == "won"
            assert float(r.payout) == 500000.0  # 封顶
    finally:
        db.close()


def test_parlay_void_whole_group(client, parlay_seed, auth_headers):
    """串关整组作废：作废一条腿 → 整组 void。"""
    from db.database import SessionLocal
    from db.models import SimulationBet

    res = client.post(
        "/api/v1/simulation/bets/parlay",
        json={
            "legs": [
                {"match_id": "HP-M1", "play_type": "hspf", "selection": "win", "sp": 2.00, "sp_source": "real"},
                {"match_id": "HP-M2", "play_type": "hspf", "selection": "draw", "sp": 3.20, "sp_source": "real"},
            ],
            "stake": 2.0, "multiple": 1,
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    cid = res.json()["combination_id"]
    first_id = res.json()["legs"][0]["id"]

    void = client.post(f"/api/v1/simulation/bets/{first_id}/void", headers=auth_headers)
    assert void.status_code == 200, void.text
    assert void.json()["status"] == "void"

    db = SessionLocal()
    try:
        rows = db.query(SimulationBet).filter(SimulationBet.combination_id == cid).all()
        assert len(rows) == 2
        assert all(r.status == "void" for r in rows)
    finally:
        db.close()


def test_parlay_rejected_when_started(client, parlay_seed, auth_headers):
    """串关含已开赛赛事 → 400。"""
    from db.database import SessionLocal
    from db.models import Match

    db = SessionLocal()
    try:
        db.query(Match).filter(Match.id == "HP-M2").update({"status": "live"}, synchronize_session=False)
        db.commit()
    finally:
        db.close()

    res = client.post(
        "/api/v1/simulation/bets/parlay",
        json={
            "legs": [
                {"match_id": "HP-M1", "play_type": "hspf", "selection": "win", "sp": 2.00, "sp_source": "real"},
                {"match_id": "HP-M2", "play_type": "hspf", "selection": "draw", "sp": 3.20, "sp_source": "real"},
            ],
            "stake": 2.0, "multiple": 1,
        },
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "已开赛" in res.json()["detail"]


# ---- 只读边界 ----

def test_parlay_readonly_predictions(client, parlay_seed, auth_headers):
    """串关创建后 predictions 表行数不变（只读边界）。"""
    from db.database import SessionLocal
    from db.models import MatchPrediction

    db = SessionLocal()
    try:
        before = db.query(MatchPrediction).count()
    finally:
        db.close()

    res = client.post(
        "/api/v1/simulation/bets/parlay",
        json={
            "legs": [
                {"match_id": "HP-M1", "play_type": "hspf", "selection": "win", "sp": 2.00, "sp_source": "real"},
                {"match_id": "HP-M2", "play_type": "hspf", "selection": "draw", "sp": 3.20, "sp_source": "real"},
            ],
            "stake": 2.0, "multiple": 1,
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text

    db = SessionLocal()
    try:
        after = db.query(MatchPrediction).count()
    finally:
        db.close()
    assert after == before


# ---- parlay_calculator 全玩法 ----

def test_calculate_parlay_picks_all_play_types():
    """全玩法串关落单计算：spf + bf + tg + hspf 混合。"""
    picks = [
        {"match_id": "M1", "match_name": "A vs B", "play_type": "spf", "option": "win", "sp": 1.80, "prob": 0.50},
        {"match_id": "M2", "match_name": "C vs D", "play_type": "bf", "option": "1:0", "sp": 7.50, "prob": 0.12},
        {"match_id": "M3", "match_name": "E vs F", "play_type": "tg", "option": "2", "sp": 3.10, "prob": 0.25},
        {"match_id": "M4", "match_name": "G vs H", "play_type": "hspf", "option": "draw", "sp": 3.20, "prob": 0.30},
    ]
    r = calculate_parlay_picks(picks, multiple=1)
    assert r["legs"] == 4
    # prob = 0.5 × 0.12 × 0.25 × 0.30 = 0.0045
    assert abs(r["prob"] - 0.0045) < 0.0001
    # payout = min(2 × 1.8×7.5×3.1×3.2, cap) = 2 × 133.92 = 267.84
    assert abs(r["payout"] - 267.84) < 0.01
    # 标签含玩法前缀
    assert "胜平负-主胜" in r["picks"][0]["label"]
    assert "半场胜平负-平" in r["picks"][3]["label"]


def test_calculate_parlay_picks_validation():
    """legs 不足 / 超上限 / SP 非法 → 抛 ValueError。"""
    with pytest.raises(ValueError):
        calculate_parlay_picks([{"match_id": "M1", "play_type": "spf", "option": "win", "sp": 1.8, "prob": 0.5}])
    with pytest.raises(ValueError):
        calculate_parlay_picks(
            [{"match_id": f"M{i}", "play_type": "spf", "option": "win", "sp": 1.8, "prob": 0.5} for i in range(9)]
        )
    with pytest.raises(ValueError):
        calculate_parlay_picks([
            {"match_id": "M1", "play_type": "spf", "option": "win", "sp": 0.5, "prob": 0.5},
            {"match_id": "M2", "play_type": "spf", "option": "win", "sp": 1.8, "prob": 0.5},
        ])
