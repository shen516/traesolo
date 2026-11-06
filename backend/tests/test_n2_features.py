"""N2：回测 / 分维准确率 / 报告导出。"""
from datetime import date, timedelta
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

REPORT_MATCH_ID = "N2-RPT-001"
REPORT_HOME = "N2-H"
REPORT_AWAY = "N2-A"
REPORT_LEAGUE = "N2LG"


def _seed_report_match(db):
    from db.models import League, Team, Match, MatchPrediction

    db.query(MatchPrediction).filter(MatchPrediction.match_id == REPORT_MATCH_ID).delete(
        synchronize_session=False
    )
    db.query(Match).filter(Match.id == REPORT_MATCH_ID).delete(synchronize_session=False)
    db.query(Team).filter(Team.id.in_([REPORT_HOME, REPORT_AWAY])).delete(
        synchronize_session=False
    )
    db.query(League).filter(League.id == REPORT_LEAGUE).delete(synchronize_session=False)

    db.add(League(id=REPORT_LEAGUE, name="N2联赛", avg_goals=2.70))
    db.add(
        Team(
            id=REPORT_HOME,
            name="N2主队",
            short_name="N2主",
            league_id=REPORT_LEAGUE,
            elo_rating=1550,
        )
    )
    db.add(
        Team(
            id=REPORT_AWAY,
            name="N2客队",
            short_name="N2客",
            league_id=REPORT_LEAGUE,
            elo_rating=1480,
        )
    )
    db.add(
        Match(
            id=REPORT_MATCH_ID,
            league_id=REPORT_LEAGUE,
            home_team_id=REPORT_HOME,
            away_team_id=REPORT_AWAY,
            match_date=date.today() + timedelta(days=1),
            status="upcoming",
        )
    )
    db.add(
        MatchPrediction(
            match_id=REPORT_MATCH_ID,
            home_win_prob=0.48,
            draw_prob=0.27,
            away_win_prob=0.25,
            lambda_home=1.45,
            lambda_away=1.10,
            main_score="1:0",
            total_goals="2.5-",
            tendency="主胜倾向",
            analysis="N2 单元测试报告",
            model_version="v5.0.0",
        )
    )
    db.commit()


def _cleanup_report_match(db):
    from db.models import League, Team, Match, MatchPrediction

    db.query(MatchPrediction).filter(MatchPrediction.match_id == REPORT_MATCH_ID).delete(
        synchronize_session=False
    )
    db.query(Match).filter(Match.id == REPORT_MATCH_ID).delete(synchronize_session=False)
    db.query(Team).filter(Team.id.in_([REPORT_HOME, REPORT_AWAY])).delete(
        synchronize_session=False
    )
    db.query(League).filter(League.id == REPORT_LEAGUE).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def report_seeded(client):
    from db.database import SessionLocal

    db = SessionLocal()
    try:
        _seed_report_match(db)
        yield
    finally:
        _cleanup_report_match(db)
        db.close()


def test_monitor_breakdown_requires_auth(client: TestClient):
    res = client.get("/api/v1/model/monitor/breakdown")
    assert res.status_code == 401


def test_monitor_breakdown_admin(client: TestClient, auth_headers):
    res = client.get(
        "/api/v1/model/monitor/breakdown",
        params={"days": 30},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "by_league" in body
    assert "by_play" in body
    assert "1x2" in body["by_play"]
    assert "sample_size" in body


def test_simulate_backtest_endpoint(client: TestClient, auth_headers):
    res = client.post(
        "/api/v1/predictions/simulate/backtest",
        json={"days": 30, "limit": 20, "simulations": 500},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["period_days"] == 30
    assert "evaluated" in body
    assert "hit_rate" in body
    assert "brier" in body
    assert "samples" in body
    assert "disclaimer" in body


def test_simulate_backtest_requires_auth(client: TestClient):
    res = client.post(
        "/api/v1/predictions/simulate/backtest",
        json={"days": 30, "limit": 20, "simulations": 500},
    )
    assert res.status_code == 401


def test_match_report_txt(client: TestClient, report_seeded, auth_headers):
    res = client.get(
        f"/api/v1/matches/{REPORT_MATCH_ID}/report",
        params={"fmt": "txt"},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    assert "text/plain" in res.headers.get("content-type", "")
    text = res.content.decode("utf-8")
    assert "足球赛事量化分析报告" in text
    assert "不构成投注建议" in text
    assert "N2主队" in text


def test_match_report_xlsx(client: TestClient, report_seeded, auth_headers):
    from openpyxl import load_workbook

    res = client.get(
        f"/api/v1/matches/{REPORT_MATCH_ID}/report",
        params={"fmt": "xlsx"},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    assert "spreadsheetml" in res.headers.get("content-type", "")
    wb = load_workbook(BytesIO(res.content))
    ws = wb.active
    assert ws["A1"].value == "字段"
    assert ws["B1"].value == "值"
    assert any(cell.value == "赛事ID" for cell in ws["A"])


def test_match_report_404(client: TestClient, auth_headers):
    res = client.get(
        "/api/v1/matches/__NO_SUCH_MATCH__/report",
        headers=auth_headers,
    )
    assert res.status_code == 404


def test_report_export_helpers_unit():
    from services.match_report_export import render_txt, render_xlsx

    payload = {
        "match_id": "M1",
        "home_team": "A",
        "away_team": "B",
        "league_id": "EPL",
        "match_date": "2026-01-01",
        "match_time": "20:00",
        "status": "finished",
        "score": "2:1",
        "home_win_prob": 0.45,
        "draw_prob": 0.28,
        "away_win_prob": 0.27,
        "lambda_home": 1.4,
        "lambda_away": 1.1,
        "main_score": "1:0",
        "total_goals": "2.5-",
        "tendency": "主胜",
        "model_version": "v5.0.0",
        "analysis": "单元测试",
        "generated_at": "2026-11-06T12:00:00",
        "disclaimer": "仅供学习、研究与数据分析，不构成投注建议。",
    }
    txt = render_txt(payload).decode("utf-8")
    assert "A vs B" in txt
    xlsx = render_xlsx(payload)
    assert len(xlsx) > 100
