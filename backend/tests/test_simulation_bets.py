"""模拟投注单：创建 / 防重复 / 作废 / 结算失败重试与改判 / 只读边界。

仅供学习、研究、数据分析，不构成投注建议，不接入真实资金。
只读边界：任何投注单操作不得写入 predictions 表。
"""

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

MATCH_ID = "SBT-M-001"
HOME_ID = "SBT-H"
AWAY_ID = "SBT-A"
LEAGUE_ID = "SBT-LG"


def _seed(db):
    from db.models import League, Team, Match

    db.query(Match).filter(Match.id == MATCH_ID).delete(synchronize_session=False)
    db.query(Team).filter(Team.id.in_([HOME_ID, AWAY_ID])).delete(synchronize_session=False)
    db.query(League).filter(League.id == LEAGUE_ID).delete(synchronize_session=False)

    db.add(League(id=LEAGUE_ID, name="投注联赛", avg_goals=2.80))
    db.add(Team(id=HOME_ID, name="投注主队", short_name="投主", league_id=LEAGUE_ID,
                elo_rating=1600, attack_strength=1.20, defense_strength=0.85,
                xg_for=1.60, xg_against=1.00))
    db.add(Team(id=AWAY_ID, name="投注客队", short_name="投客", league_id=LEAGUE_ID,
                elo_rating=1500, attack_strength=1.00, defense_strength=1.00,
                xg_for=1.20, xg_against=1.30))
    db.add(Match(
        id=MATCH_ID, league_id=LEAGUE_ID, home_team_id=HOME_ID, away_team_id=AWAY_ID,
        match_date=date.today() + timedelta(days=2), status="upcoming",
        match_no="周五001", handicap=-1,
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
    from db.models import SimulationBet

    db = SessionLocal()
    try:
        # 投注单按用户维度防重复，跨用例会互相污染（前一个用例留下的同选项单
        # 会让下一个用例首建即 400）。每用例前清空测试库中的投注单。
        db.query(SimulationBet).delete(synchronize_session=False)
        db.commit()
        _seed(db)
        yield
    finally:
        _cleanup(db)
        db.close()


def _count_predictions(match_id: str) -> int:
    from db.database import SessionLocal
    from db.models import MatchPrediction

    db = SessionLocal()
    try:
        return db.query(MatchPrediction).filter(MatchPrediction.match_id == match_id).count()
    finally:
        db.close()


def _cleanup_bets(user_id: int):
    from db.database import SessionLocal
    from db.models import SimulationBet

    db = SessionLocal()
    try:
        db.query(SimulationBet).filter(SimulationBet.user_id == user_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_create_bet_readonly_predictions(client: TestClient, seeded, auth_headers):
    """B4：创建投注单后 predictions 表行数不变（只读边界）。"""
    assert _count_predictions(MATCH_ID) == 0
    res = client.post(
        "/api/v1/simulation/bets",
        json={
            "match_id": MATCH_ID, "play_type": "spf", "selection": "win",
            "sp": 1.80, "sp_source": "real", "stake": 2.0, "multiple": 1,
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "pending"
    # 只读：不写 predictions 表
    assert _count_predictions(MATCH_ID) == 0


def test_create_bet_duplicate_rejected(client: TestClient, seeded, auth_headers):
    """A3：同用户同赛事同玩法同选项未作废 → 400 防重复。"""
    body = {
        "match_id": MATCH_ID, "play_type": "spf", "selection": "win",
        "sp": 1.80, "sp_source": "real", "stake": 2.0, "multiple": 1,
    }
    r1 = client.post("/api/v1/simulation/bets", json=body, headers=auth_headers)
    assert r1.status_code == 201, r1.text
    r2 = client.post("/api/v1/simulation/bets", json=body, headers=auth_headers)
    assert r2.status_code == 400
    assert "重复" in r2.json()["detail"]


def test_create_bet_invalid_selection(client: TestClient, seeded, auth_headers):
    """非法玩法 / 选项 / SP 均 400。"""
    cases = [
        {"match_id": MATCH_ID, "play_type": "spf", "selection": "xxx",
         "sp": 1.8, "sp_source": "real", "stake": 2.0, "multiple": 1},
        {"match_id": MATCH_ID, "play_type": "bf", "selection": "9:9",
         "sp": 1.8, "sp_source": "real", "stake": 2.0, "multiple": 1},
        {"match_id": MATCH_ID, "play_type": "spf", "selection": "win",
         "sp": 1.0, "sp_source": "real", "stake": 2.0, "multiple": 1},
    ]
    for body in cases:
        res = client.post("/api/v1/simulation/bets", json=body, headers=auth_headers)
        assert res.status_code == 400, res.text


def test_void_bet_before_kickoff(client: TestClient, seeded, auth_headers):
    """B1：pending 且赛事未开赛可作废；作废后同选项可重新提交。"""
    body = {
        "match_id": MATCH_ID, "play_type": "spf", "selection": "draw",
        "sp": 3.40, "sp_source": "real", "stake": 2.0, "multiple": 1,
    }
    created = client.post("/api/v1/simulation/bets", json=body, headers=auth_headers).json()
    bet_id = created["id"]

    void = client.post(f"/api/v1/simulation/bets/{bet_id}/void", headers=auth_headers)
    assert void.status_code == 200, void.text
    assert void.json()["status"] == "void"

    # 作废后可重新提交（防重复排除 void）
    re = client.post("/api/v1/simulation/bets", json=body, headers=auth_headers)
    assert re.status_code == 201, re.text


def test_void_bet_after_kickoff_rejected(client: TestClient, seeded, auth_headers):
    """B1：赛事已开赛 → 400 不可作废。"""
    from db.database import SessionLocal
    from db.models import Match

    body = {
        "match_id": MATCH_ID, "play_type": "spf", "selection": "lose",
        "sp": 4.20, "sp_source": "real", "stake": 2.0, "multiple": 1,
    }
    created = client.post("/api/v1/simulation/bets", json=body, headers=auth_headers).json()
    bet_id = created["id"]

    db = SessionLocal()
    try:
        db.query(Match).filter(Match.id == MATCH_ID).update({"status": "finished"}, synchronize_session=False)
        db.commit()
    finally:
        db.close()

    void = client.post(f"/api/v1/simulation/bets/{bet_id}/void", headers=auth_headers)
    assert void.status_code == 400
    assert "不可作废" in void.json()["detail"]


def test_settle_fail_count_to_void(client: TestClient, seeded, auth_headers):
    """A4：赛果缺失累计达阈值后置 void。"""
    from db.database import SessionLocal
    from db.models import Match, SimulationBet
    from services.simulation_bet_service import SETTLE_FAIL_MAX, settle_pending

    body = {
        "match_id": MATCH_ID, "play_type": "spf", "selection": "win",
        "sp": 1.80, "sp_source": "real", "stake": 2.0, "multiple": 1,
    }
    created = client.post("/api/v1/simulation/bets", json=body, headers=auth_headers).json()
    bet_id = created["id"]

    db = SessionLocal()
    try:
        db.query(Match).filter(Match.id == MATCH_ID).update({"status": "finished"}, synchronize_session=False)
        db.commit()
    finally:
        db.close()

    # 无赛果（score_home 为 None）：连续调用，前 SETTLE_FAIL_MAX-1 次保持 pending
    for i in range(SETTLE_FAIL_MAX - 1):
        settle_pending(SessionLocal())
        db = SessionLocal()
        try:
            bet = db.query(SimulationBet).filter(SimulationBet.id == bet_id).first()
            assert bet.status == "pending", f"第 {i + 1} 次应仍 pending"
        finally:
            db.close()
    # 第 SETTLE_FAIL_MAX 次 → void
    settle_pending(SessionLocal())
    db = SessionLocal()
    try:
        bet = db.query(SimulationBet).filter(SimulationBet.id == bet_id).first()
        assert bet.status == "void"
        assert bet.settle_fail_count >= SETTLE_FAIL_MAX
    finally:
        db.close()


def test_settle_score_correction_void(client: TestClient, seeded, auth_headers):
    """A5：已结算后赛果改判（快照不一致）→ 置 void。"""
    from db.database import SessionLocal
    from db.models import Match, SimulationBet
    from services.simulation_bet_service import settle_pending

    body = {
        "match_id": MATCH_ID, "play_type": "spf", "selection": "win",
        "sp": 1.80, "sp_source": "real", "stake": 2.0, "multiple": 1,
    }
    created = client.post("/api/v1/simulation/bets", json=body, headers=auth_headers).json()
    bet_id = created["id"]

    db = SessionLocal()
    try:
        db.query(Match).filter(Match.id == MATCH_ID).update(
            {"status": "finished", "home_goals": 2, "away_goals": 1, "result": "H"},
            synchronize_session=False)
        db.commit()
    finally:
        db.close()

    settle_pending(SessionLocal())
    db = SessionLocal()
    try:
        bet = db.query(SimulationBet).filter(SimulationBet.id == bet_id).first()
        assert bet.status == "won"  # 主胜 2:1
    finally:
        db.close()

    # 赛果改判：2:1(H) → 0:0(D)
    db = SessionLocal()
    try:
        db.query(Match).filter(Match.id == MATCH_ID).update(
            {"home_goals": 0, "away_goals": 0, "result": "D"}, synchronize_session=False)
        db.commit()
    finally:
        db.close()

    settle_pending(SessionLocal())
    db = SessionLocal()
    try:
        bet = db.query(SimulationBet).filter(SimulationBet.id == bet_id).first()
        assert bet.status == "void"
        assert bet.settle_score_snapshot == "0:0"
    finally:
        db.close()


# ---- 权限收紧：普通用户（simulation:view 但无 model:manage）只读 ----
# 复用 test_trend_permissions.py 的造角色/用户/token 模式（不 import conftest）。

import hashlib
import time


def _sbt_unique(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}_{hashlib.md5(prefix.encode()).hexdigest()[:6]}"


def _sbt_seed_role(db, code, perm_codes):
    from db.models import Role, Permission, RolePermission

    def _perm(pcode):
        p = db.query(Permission).filter(Permission.code == pcode).first()
        if not p:
            p = Permission(name=pcode, code=pcode, type="button", parent_id=0)
            db.add(p)
            db.commit()
            db.refresh(p)
        return p

    r = db.query(Role).filter(Role.code == code).first()
    if r is None:
        r = Role(name=code, code=code, is_system=False)
        db.add(r)
        db.commit()
        db.refresh(r)
    db.query(RolePermission).filter(RolePermission.role_id == r.id).delete(synchronize_session=False)
    for pcode in perm_codes:
        db.add(RolePermission(role_id=r.id, permission_id=_perm(pcode).id))
    db.commit()
    return r


def _sbt_mk_user(db, role):
    from api.deps import load_user_auth_payload
    from db.models import User, UserRole

    uname = _sbt_unique("sbtuser")
    u = User(username=uname, email=f"{uname}@sbt.test", password_hash="x",
             level="free", subscription_plan="free", subscription_status="active",
             is_active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(UserRole(user_id=u.id, role_id=role.id))
    db.commit()

    payload = load_user_auth_payload(db, u)
    u._session_roles = payload["roles"]
    u._session_permissions = payload["permissions"]
    return u


def _sbt_headers_for(client, user):
    from api.deps import store_token

    tok = hashlib.md5(f"{user.id}:{user.username}:sbt".encode()).hexdigest()
    roles = list(user._session_roles) if getattr(user, "_session_roles", None) else []
    store_token(tok, user.id, user.username, roles, list(user._session_permissions))
    return {"Authorization": f"Bearer {tok}"}


def _sbt_drop_user(db, u):
    from db.models import (
        UserRole, UserFavorite, UserHistory, UserPreference,
        OperationLog, SubscriptionRecord, UserFollowedLeague, SimulationBet,
    )

    db.query(SimulationBet).filter(SimulationBet.user_id == u.id).delete(synchronize_session=False)
    db.query(UserRole).filter(UserRole.user_id == u.id).delete(synchronize_session=False)
    for m in (UserFavorite, UserHistory, UserPreference, OperationLog,
              SubscriptionRecord, UserFollowedLeague):
        db.query(m).filter(m.user_id == u.id).delete(synchronize_session=False)
    db.delete(u)
    db.commit()


def test_write_bets_require_model_manage(client: TestClient, seeded):
    """权限收紧：仅持 simulation:view 的普通用户可读、不可写（创建/作废 403）。"""
    from db.database import SessionLocal

    db = SessionLocal()
    user = None
    try:
        role = _sbt_seed_role(db, "__sbt_viewer_only", ["simulation:view"])
        user = _sbt_mk_user(db, role)
        headers = _sbt_headers_for(client, user)

        # 读放行
        r_list = client.get("/api/v1/simulation/bets", headers=headers)
        assert r_list.status_code == 200, r_list.text
        r_stats = client.get("/api/v1/simulation/bets/stats", headers=headers)
        assert r_stats.status_code == 200, r_stats.text

        # 创建被拒 403
        body = {
            "match_id": MATCH_ID, "play_type": "spf", "selection": "win",
            "sp": 1.80, "sp_source": "real", "stake": 2.0, "multiple": 1,
        }
        r_create = client.post("/api/v1/simulation/bets", json=body, headers=headers)
        assert r_create.status_code == 403, r_create.text

        # 作废被拒 403（权限检查先于 404，无需真实投注单）
        r_void = client.post("/api/v1/simulation/bets/999999/void", headers=headers)
        assert r_void.status_code == 403, r_void.text
    finally:
        try:
            if user is not None:
                _sbt_drop_user(db, user)
        except Exception:
            db.rollback()
        db.close()
