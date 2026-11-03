"""竞彩分析历史比分回补：days_back 参数与定时任务注册。"""

from datetime import date, timedelta
from unittest.mock import MagicMock

from services.real_crawler import RealMatchCrawler
from services.scheduled_tasks import get_task_definitions


def test_crawl_jczq_bf_history_dates():
    crawler = RealMatchCrawler()
    called = []

    def fake_url(url, date_str=None, extract_bf=False):
        called.append({"url": url, "date_str": date_str, "extract_bf": extract_bf})
        return []

    crawler._crawl_jczq_trade_url = fake_url
    crawler._crawl_jczq_bf(days_ahead=0, days_back=3)

    assert any("playid=271" in c["url"] and c["date_str"] is None for c in called)
    today = date.today()
    for i in range(1, 4):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        assert any(c["date_str"] == d and c["extract_bf"] for c in called)
    # 不应请求未来日（days_ahead=0 时仍会请求今日一次）
    future = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    assert not any(c["date_str"] == future for c in called)
    # 同窗口会额外拉胜平负页（无 playid=271）用于合并 NSPF/SPF
    assert any("playid=271" not in c["url"] and not c["extract_bf"] for c in called)


def test_merge_spf_into_bf_by_fixture_id():
    bf = [{
        "id": "EPL-2026-10-28-A-B",
        "fixture_id": "fid-1",
        "odds_bf_json": '{"1:0": 5.0}',
        "odds_nspf_win": None,
        "odds_spf_win": None,
        "handicap": None,
    }]
    spf = [{
        "id": "EPL-2026-10-28-A-B",
        "fixture_id": "fid-1",
        "odds_nspf_win": 1.85,
        "odds_nspf_draw": 3.4,
        "odds_nspf_lose": 4.2,
        "odds_spf_win": 2.1,
        "odds_spf_draw": 3.2,
        "odds_spf_lose": 3.0,
        "handicap": -1,
    }]
    out = RealMatchCrawler._merge_spf_into_bf(bf, spf)
    assert out[0]["odds_nspf_win"] == 1.85
    assert out[0]["odds_nspf_draw"] == 3.4
    assert out[0]["odds_spf_lose"] == 3.0
    assert out[0]["handicap"] == -1
    assert out[0]["odds_bf_json"] == '{"1:0": 5.0}'


def test_jingcai_bf_history_task_registered():
    crawler_service = MagicMock()
    defs = {d[0]: d for d in get_task_definitions(crawler_service)}
    assert "jingcai_bf_history_crawl" in defs
    assert defs["jingcai_bf_history_crawl"][2] == 360
    assert defs["jingcai_bf_history_crawl"][3] == "竞彩分析历史比分回补"
    assert defs["jingcai_bf_history_crawl"][4] == "odds"
    assert defs["jingcai_bf_history_crawl"][1] == crawler_service.crawl_jingcai_bf_history
