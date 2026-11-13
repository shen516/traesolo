"""测试竞彩全玩法 P4 增强：赛果校验 / SP 异动监测 / 导出 / 汇总。

仅供学习研究；接口不构成投注建议。
"""
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
        "is_end": True,
        "handicap": -1,
        "kdg": True,
        "subactive": {"spf": {"dg": True, "gg": True}},
        "odds": {
            "spf": {"3": 2.10, "1": 3.20, "0": 3.50},
            "nspf": {"3": 1.80, "1": 3.40, "0": 4.20},
        },
        "home_goals": None,
        "away_goals": None,
        "result": None,
        "source": "500_trade_mix",
    }
    base.update(over)
    return base


# ===== 赛果校验 =====

def test_verify_results_match(db_session):
    svc.upsert_crawl_result(db_session, [_row(process_id="1001", is_end=True, result="3",
                                             home_goals=2, away_goals=1)])
    rows = [{
        "process_id": "1001",
        "process_date": date.today().strftime("%Y-%m-%d"),
        "home_goals": 2,
        "away_goals": 1,
        "result": "3",
        "odds": {},
    }]
    out = svc.verify_results(db_session, rows)
    assert out["checked"] == 1
    assert out["matched"] == 1
    assert out["mismatched"] == 0
    assert out["missing"] == 0


def test_verify_results_mismatch(db_session):
    svc.upsert_crawl_result(db_session, [_row(process_id="1001", is_end=True, result="1")])
    rows = [{
        "process_id": "1001",
        "process_date": date.today().strftime("%Y-%m-%d"),
        "home_goals": 2,
        "away_goals": 1,
        "result": "3",
        "odds": {},
    }]
    out = svc.verify_results(db_session, rows)
    assert out["mismatched"] == 1
    assert out["mismatches"][0]["db_result"] == "1"
    assert out["mismatches"][0]["crawled_result"] == "3"


def test_verify_results_missing_in_db(db_session):
    # DB 无赛果，采集侧有 → missing
    svc.upsert_crawl_result(db_session, [_row(process_id="1001", is_end=True, result=None)])
    rows = [{
        "process_id": "1001",
        "process_date": date.today().strftime("%Y-%m-%d"),
        "home_goals": 1,
        "away_goals": 0,
        "result": "3",
        "odds": {},
    }]
    out = svc.verify_results(db_session, rows)
    assert out["missing"] == 1
    assert out["matched"] == 0


def test_verify_skips_not_ended(db_session):
    # 未开赛且无赛果 → 不校验
    svc.upsert_crawl_result(db_session, [_row(process_id="1001", is_end=False)])
    rows = [{
        "process_id": "1001",
        "process_date": date.today().strftime("%Y-%m-%d"),
        "home_goals": None,
        "away_goals": None,
        "result": None,
        "odds": {},
    }]
    out = svc.verify_results(db_session, rows)
    assert out["checked"] == 0


# ===== SP 异动监测 =====

def test_detect_sp_changes_records(db_session):
    svc.upsert_crawl_result(db_session, [_row(process_id="1001")])
    # 采集侧：spf 3 从 2.10 → 2.50（+19%），1 从 3.20 → 4.00（+25%）
    rows = [{
        "process_id": "1001",
        "process_date": date.today().strftime("%Y-%m-%d"),
        "odds": {"spf": {"3": 2.50, "1": 4.00, "0": 3.50}},
    }]
    out = svc.detect_sp_changes(db_session, rows, threshold=0.20)
    assert out["changed"] == 2
    assert out["alerts"] == 1  # 仅 1 触发 20% 阈值
    # 落库
    recs = db_session.query(models.JingcaiSpChange).all()
    assert len(recs) == 2
    alert_rec = [r for r in recs if r.alert][0]
    assert alert_rec.play == "spf"
    assert alert_rec.option == "1"
    assert alert_rec.change_type == "spike"


def test_detect_sp_changes_no_change(db_session):
    svc.upsert_crawl_result(db_session, [_row(process_id="1001")])
    rows = [{
        "process_id": "1001",
        "process_date": date.today().strftime("%Y-%m-%d"),
        "odds": {"spf": {"3": 2.10, "1": 3.20, "0": 3.50}},  # 完全一致
    }]
    out = svc.detect_sp_changes(db_session, rows, threshold=0.20)
    assert out["changed"] == 0
    assert out["alerts"] == 0


def test_query_sp_changes_filter_alert(db_session):
    svc.upsert_crawl_result(db_session, [_row(process_id="1001")])
    rows = [{
        "process_id": "1001",
        "process_date": date.today().strftime("%Y-%m-%d"),
        "odds": {"spf": {"3": 3.00, "1": 3.20, "0": 3.50}},
    }]
    svc.detect_sp_changes(db_session, rows, threshold=0.20)
    all_changes = svc.query_sp_changes(db_session)
    assert len(all_changes) == 1
    alerts = svc.query_sp_changes(db_session, only_alert=True)
    assert len(alerts) == 1
    by_play = svc.query_sp_changes(db_session, play="spf")
    assert len(by_play) == 1


# ===== 导出 =====

def test_export_matches(db_session):
    svc.upsert_crawl_result(db_session, [_row()])
    rows = svc.export_matches(db_session)
    assert len(rows) == 1
    row = rows[0]
    assert row["home_name"] == "曼城"
    assert "3:2.1" in row["spf"]  # opt:sp 序列化
    assert row["result"] == ""
    assert row["kdg"] == "是"


def test_export_latest_date(db_session):
    svc.upsert_crawl_result(db_session, [_row()])
    rows = svc.export_matches(db_session, process_date=date.today().strftime("%Y-%m-%d"))
    assert len(rows) == 1


# ===== 汇总 =====

def test_summarize_matches(db_session):
    svc.upsert_crawl_result(db_session, [
        _row(process_id="1001", result="3", home_goals=2, away_goals=1, is_end=True),
        _row(process_id="1002", match_num="周六002", home_name="阿森纳", away_name="切尔西",
             result=None, is_end=False),
    ])
    out = svc.summarize_matches(db_session)
    assert out["total_matches"] == 2
    assert out["ended_matches"] == 1
    assert out["ended_with_result"] == 1
    assert out["result_coverage"] == 1.0
    assert out["kdg_matches"] == 2
    assert out["by_league"][0] == ("英超", 2)
    assert "在售" in out["by_status"] or "已完赛" in out["by_status"]
    assert out["play_coverage"]["spf"] == 2
