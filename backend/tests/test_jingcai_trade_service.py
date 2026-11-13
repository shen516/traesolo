"""测试竞彩全玩法服务：upsert / query / API。

仅供学习研究；接口不构成投注建议。
"""
import json
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db import models
from services import jingcai_trade_service as svc


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _row(**over):
    base = {
        "process_id": "1001",
        "process_date": date.today().strftime("%Y-%m-%d"),
        "match_num": "周六001",
        "fixture_id": "F1",
        "match_id": "M1",
        "home_team_id": "H1",
        "away_team_id": "A1",
        "league_name": "英超",
        "home_name": "曼城",
        "away_name": "利物浦",
        "match_date": date.today(),
        "match_time": "20:00",
        "buy_end_time": "19:30",
        "is_end": False,
        "handicap": -1,
        "kdg": True,
        "subactive": {"spf": {"dg": True, "gg": True}, "bf": {"dg": True, "gg": True}},
        "odds": {
            "spf": {"3": 2.10, "1": 3.20, "0": 3.50},
            "nspf": {"3": 1.80, "1": 3.40, "0": 4.20},
            "bf": {"1:0": 8.0, "0:0": 12.0, "胜其它": 30.0},
            "jqs": {"0": 9.0, "1": 4.5, "7": 25.0},
            "bqc": {"3-3": 15.0, "0-0": 20.0},
        },
        "home_goals": None,
        "away_goals": None,
        "result": None,
        "source": "500_trade_mix",
    }
    base.update(over)
    return base


def test_upsert_insert_and_query(db_session):
    rows = [_row()]
    stats = svc.upsert_crawl_result(db_session, rows)
    assert stats["inserted"] == 1
    assert stats["updated"] == 0

    got = svc.query_matches(db_session, play="spf")
    assert len(got) == 1
    assert got[0]["home_name"] == "曼城"
    assert got[0]["odds"]["spf"]["3"] == 2.10
    assert got[0]["kdg"] is True


def test_upsert_update_idempotent(db_session):
    svc.upsert_crawl_result(db_session, [_row(handicap=-1)])
    # 第二次同主键：更新而非重复插入
    stats = svc.upsert_crawl_result(db_session, [_row(handicap=1)])
    assert stats["inserted"] == 0
    assert stats["updated"] == 1
    got = svc.query_matches(db_session, play="spf")
    assert len(got) == 1
    assert got[0]["handicap"] == 1


def test_query_filter_play(db_session):
    svc.upsert_crawl_result(db_session, [_row()])
    # 单关视图：仅可单关
    dg = svc.query_matches(db_session, play="dg")
    assert len(dg) == 1
    # 混合过关：全部玩法
    hhgg = svc.query_matches(db_session, play="hhgg")
    assert set(hhgg[0]["odds"].keys()) == {"spf", "nspf", "bf", "jqs", "bqc"}
    # 进球数过滤
    jqs = svc.query_matches(db_session, play="jqs")
    assert jqs[0]["odds"]["jqs"]["0"] == 9.0
    # 半全场过滤
    bqc = svc.query_matches(db_session, play="bqc")
    assert bqc[0]["odds"]["bqc"]["0-0"] == 20.0


def test_query_excludes_old_dates(db_session):
    yesterday = (date.today().strftime("%Y-%m-%d"))
    old = (date(2020, 1, 1)).strftime("%Y-%m-%d")
    svc.upsert_crawl_result(db_session, [_row(process_date=yesterday)])
    svc.upsert_crawl_result(db_session, [_row(process_date=old, process_id="2002")])
    got = svc.query_matches(db_session, play="spf")
    assert all(m["process_date"] != old for m in got)


def test_option_order():
    assert svc.option_order("jqs") == ["0", "1", "2", "3", "4", "5", "6", "7"]
    assert svc.option_order("bqc")[0] == "3-3"
    assert svc.option_order("bf")[-1] == "负其它"


def test_cleanup_old(db_session):
    svc.upsert_crawl_result(db_session, [_row()])
    deleted = svc.cleanup_old(db_session, keep_days=7)
    assert deleted == 0  # 今天不删


# ===== P2：奖金计算 =====

def _sel(pid, play, option, dt=None):
    return {
        "process_id": pid,
        "process_date": (dt or date.today()).strftime("%Y-%m-%d"),
        "play": play,
        "option": option,
    }


def test_calculate_single_bet(db_session):
    svc.upsert_crawl_result(db_session, [_row()])
    out = svc.calculate_bet(db_session, [_sel("1001", "spf", "3")])
    assert out["ok"] is True
    assert out["bet_count"] == 1
    assert out["total_amount"] == 2.0
    assert out["min_amount"] == pytest.approx(4.2)   # 2.10 × 2
    assert out["max_amount"] == pytest.approx(4.2)
    assert out["details"][0]["items"][0]["sp"] == 2.10
    assert "不构成投注建议" in out["note"]


def test_calculate_single_multi_select(db_session):
    svc.upsert_crawl_result(db_session, [_row()])
    out = svc.calculate_bet(
        db_session,
        [_sel("1001", "spf", "3"), _sel("1001", "spf", "1"), _sel("1001", "spf", "0")],
        pass_types=["single"],
    )
    assert out["bet_count"] == 3
    assert out["total_amount"] == 6.0
    # 单关每注独立，总额 = (2.10+3.20+3.50)×2
    assert out["max_amount"] == pytest.approx(17.6)


def test_calculate_parlay_2x1(db_session):
    svc.upsert_crawl_result(db_session, [_row(process_id="1001"), _row(process_id="1002")])
    out = svc.calculate_bet(
        db_session,
        [_sel("1001", "spf", "3"), _sel("1002", "spf", "3")],
        pass_types=["2x1"],
    )
    assert out["bet_count"] == 1
    assert out["total_amount"] == 2.0
    # 2.10 × 2.10 × 2 = 8.82
    assert out["max_amount"] == pytest.approx(8.82)


def test_calculate_parlay_combo_3x4(db_session):
    svc.upsert_crawl_result(
        db_session, [_row(process_id="1001"), _row(process_id="1002"), _row(process_id="1003")]
    )
    out = svc.calculate_bet(
        db_session,
        [_sel("1001", "spf", "3"), _sel("1002", "spf", "3"), _sel("1003", "spf", "3")],
        pass_types=["3x4"],
    )
    # 3 个 2串1 + 1 个 3串1 = 4 注
    assert out["bet_count"] == 4
    assert out["total_amount"] == 8.0
    # 3×(2.1²×2) + 2.1³×2
    assert out["max_amount"] == pytest.approx(44.98, abs=0.01)


def test_calculate_parlay_fushi(db_session):
    svc.upsert_crawl_result(db_session, [_row(process_id="1001"), _row(process_id="1002")])
    out = svc.calculate_bet(
        db_session,
        [_sel("1001", "spf", "3"), _sel("1001", "spf", "1"), _sel("1002", "spf", "3")],
        pass_types=["2x1"],
    )
    # 第 1 场 2 项 × 第 2 场 1 项 = 2 注
    assert out["bet_count"] == 2
    assert out["total_amount"] == 4.0
    assert out["min_amount"] == pytest.approx(2.1 * 2.1 * 2)
    assert out["max_amount"] == pytest.approx(3.2 * 2.1 * 2)


def test_calculate_unknown_pass_type(db_session):
    svc.upsert_crawl_result(db_session, [_row()])
    out = svc.calculate_bet(db_session, [_sel("1001", "spf", "3")], pass_types=["9x9"])
    assert out["ok"] is False
    assert "不支持" in out["reason"]


def test_calculate_invalid_and_empty(db_session):
    svc.upsert_crawl_result(db_session, [_row()])
    out = svc.calculate_bet(db_session, [_sel("1001", "bf", "9:9")])
    assert out["ok"] is False
    assert out["invalid"][0]["reason"]

    empty = svc.calculate_bet(db_session, [])
    assert empty["ok"] is False
    assert empty["bet_count"] == 0


def test_calculate_times(db_session):
    svc.upsert_crawl_result(db_session, [_row()])
    out = svc.calculate_bet(db_session, [_sel("1001", "spf", "3")], times=5)
    assert out["bet_count"] == 1
    assert out["total_amount"] == 10.0
    assert out["max_amount"] == pytest.approx(2.1 * 2 * 5)


# ===== P3：销售时序派生 =====

def test_derive_sale_status_open(db_session):
    # 封盘/开赛都在未来 → open
    future = (datetime.now() + timedelta(hours=3)).strftime("%H:%M")
    svc.upsert_crawl_result(db_session, [_row(match_time=future, buy_end_time=future)])
    rec = db_session.query(models.JingcaiMatchOdds).first()
    st = svc.derive_sale_status(rec)
    assert st["sale_status"] == "open"
    assert st["closed"] is False
    assert st["sale_status_label"] == "在售"


def test_derive_sale_status_closing(db_session):
    # 封盘在 10 分钟内 → closing（临场）
    closing = (datetime.now() + timedelta(minutes=10)).strftime("%H:%M")
    svc.upsert_crawl_result(db_session, [_row(match_time=closing, buy_end_time=closing)])
    rec = db_session.query(models.JingcaiMatchOdds).first()
    st = svc.derive_sale_status(rec)
    assert st["sale_status"] == "closing"
    assert st["closed"] is False
    assert st["remaining_seconds"] > 0
    assert st["remaining_seconds"] <= 15 * 60


def test_derive_sale_status_closed(db_session):
    # 封盘时间已过 → closed（未开赛）
    past = (datetime.now() - timedelta(minutes=5)).strftime("%H:%M")
    future = (datetime.now() + timedelta(hours=2)).strftime("%H:%M")
    svc.upsert_crawl_result(db_session, [_row(match_time=future, buy_end_time=past)])
    rec = db_session.query(models.JingcaiMatchOdds).first()
    st = svc.derive_sale_status(rec)
    assert st["sale_status"] == "closed"
    assert st["closed"] is True


def test_derive_sale_status_started_and_ended(db_session):
    # 已开赛（无赛果）→ started
    started = (datetime.now() - timedelta(minutes=20)).strftime("%H:%M")
    svc.upsert_crawl_result(db_session, [_row(match_time=started, buy_end_time=started, is_end=False)])
    rec = db_session.query(models.JingcaiMatchOdds).first()
    st = svc.derive_sale_status(rec)
    assert st["sale_status"] == "started"
    assert st["closed"] is True

    # 已完赛 → ended
    ended = (datetime.now() - timedelta(hours=2)).strftime("%H:%M")
    svc.upsert_crawl_result(db_session, [_row(match_time=ended, buy_end_time=ended, is_end=True)])
    rec = db_session.query(models.JingcaiMatchOdds).first()
    st = svc.derive_sale_status(rec)
    assert st["sale_status"] == "ended"
    assert st["closed"] is True


def test_count_pending_refresh(db_session):
    # 临近开赛（30 分钟内）→ 值得刷新
    near = (datetime.now() + timedelta(minutes=30)).strftime("%H:%M")
    svc.upsert_crawl_result(db_session, [_row(process_id="P1", match_time=near, buy_end_time=near)])
    # 已开赛但缺赛果 → 需要回补
    started = (datetime.now() - timedelta(minutes=10)).strftime("%H:%M")
    svc.upsert_crawl_result(db_session, [_row(process_id="P2", match_time=started, buy_end_time=started, is_end=False)])
    # 远期（3 小时后）→ 不需要
    far = (datetime.now() + timedelta(hours=3)).strftime("%H:%M")
    svc.upsert_crawl_result(db_session, [_row(process_id="P3", match_time=far, buy_end_time=far)])
    stat = svc.count_pending_refresh(db_session)
    assert stat["near_kickoff"] >= 1
    assert stat["pending_result"] >= 1
    assert svc.refresh_trigger_required(db_session) is True


def test_refresh_trigger_false_when_no_need(db_session):
    far = (datetime.now() + timedelta(hours=5)).strftime("%H:%M")
    svc.upsert_crawl_result(db_session, [_row(match_time=far, buy_end_time=far, is_end=True, result="3:1", home_goals=3, away_goals=1)])
    assert svc.refresh_trigger_required(db_session) is False

