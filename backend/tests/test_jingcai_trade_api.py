"""测试竞彩全玩法 API 端点（只读分析，非投注建议）。"""
from datetime import date

from services import jingcai_trade_service as svc
from db.database import SessionLocal


def _seed(db):
    svc.upsert_crawl_result(db, [{
        "process_id": "3001",
        "process_date": date.today().strftime("%Y-%m-%d"),
        "match_num": "周日001",
        "fixture_id": "F9",
        "league_name": "西甲",
        "home_name": "皇马",
        "away_name": "巴萨",
        "match_date": date.today(),
        "match_time": "22:00",
        "is_end": False,
        "handicap": 0,
        "kdg": True,
        "subactive": {"spf": {"dg": True, "gg": True}},
        "odds": {"spf": {"3": 2.5, "1": 3.1, "0": 2.9}},
    }])


def test_jingcai_trade_matches_requires_auth(client):
    res = client.get("/api/v1/jingcai/trade/matches")
    assert res.status_code in (401, 403)


def test_jingcai_trade_matches_ok(client, auth_headers):
    _seed(SessionLocal())
    res = client.get("/api/v1/jingcai/trade/matches?play=spf", headers=auth_headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["play"] == "spf"
    assert "matches" in data
    assert "dates" in data
    assert "option_order" in data


def test_jingcai_trade_invalid_play(client, auth_headers):
    res = client.get("/api/v1/jingcai/trade/matches?play=xx", headers=auth_headers)
    assert res.status_code == 400


def test_jingcai_trade_dates(client, auth_headers):
    _seed(SessionLocal())
    res = client.get("/api/v1/jingcai/trade/dates", headers=auth_headers)
    assert res.status_code == 200, res.text
    assert "dates" in res.json()


def test_jingcai_trade_pass_types(client, auth_headers):
    res = client.get("/api/v1/jingcai/trade/pass-types", headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert "3x4" in body["pass_types"]
    assert body["single"] is True


def test_jingcai_trade_calculate(client, auth_headers):
    _seed(SessionLocal())
    payload = {
        "selections": [{
            "process_id": "3001",
            "process_date": date.today().strftime("%Y-%m-%d"),
            "play": "spf",
            "option": "3",
        }],
        "pass_types": ["single"],
        "times": 1,
    }
    res = client.post("/api/v1/jingcai/trade/calculate", json=payload, headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["bet_count"] == 1
    assert body["max_amount"] == 5.0  # 2.5 × 2
    assert "不构成投注建议" in body["note"]


def test_jingcai_trade_calculate_invalid_play(client, auth_headers):
    payload = {
        "selections": [{
            "process_id": "3001",
            "process_date": date.today().strftime("%Y-%m-%d"),
            "play": "dg",
            "option": "3",
        }],
    }
    res = client.post("/api/v1/jingcai/trade/calculate", json=payload, headers=auth_headers)
    assert res.status_code == 400


def test_jingcai_trade_export_requires_auth(client):
    res = client.get("/api/v1/jingcai/trade/export")
    assert res.status_code in (401, 403)


def test_jingcai_trade_export_csv(client, auth_headers):
    _seed(SessionLocal())
    res = client.get("/api/v1/jingcai/trade/export", headers=auth_headers)
    assert res.status_code == 200, res.text
    # 响应形态：CSV + BOM + attachment 下载头
    assert "text/csv" in res.headers.get("content-type", "")
    assert "attachment" in res.headers.get("content-disposition", "")
    body = res.content
    assert body, "导出内容不应为空"
    assert body.startswith("\ufeff".encode("utf-8")), "CSV 应以 UTF-8 BOM 开头"
    text = body.decode("utf-8-sig")
    lines = text.splitlines()
    # 后端 /export 表头使用 EXPORT_COLUMNS 的中文 label，而非字段 key
    assert lines and "销售日" in lines[0] and "场次编号" in lines[0], \
        "表头应包含销售日/场次编号"


def test_jingcai_trade_export_by_date(client, auth_headers):
    _seed(SessionLocal())
    d = date.today().strftime("%Y-%m-%d")
    res = client.get(f"/api/v1/jingcai/trade/export?process_date={d}", headers=auth_headers)
    assert res.status_code == 200, res.text
    assert f"jingcai_trade_{d}.csv" in res.headers.get("content-disposition", "")
    text = res.content.decode("utf-8-sig")
    assert "皇马" in text and "巴萨" in text, "按销售日导出应含种子数据"
