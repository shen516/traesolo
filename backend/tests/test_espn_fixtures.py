"""赛程 500 主 / ESPN 软兜底与 enrich。"""
from datetime import date, time as dt_time


def test_espn_fixture_date_windows_current_season():
    from services.real_team_crawler import RealTeamCrawler

    crawler = RealTeamCrawler.__new__(RealTeamCrawler)
    windows = crawler._espn_fixture_date_windows(include_history=False, seasons_back=0)
    assert windows
    assert windows[0][0].month == 7
    assert windows[0][0].day == 1
    assert all(a <= b for a, b in windows)


def test_convert_espn_events_basic():
    from services.real_team_crawler import RealTeamCrawler

    crawler = RealTeamCrawler.__new__(RealTeamCrawler)
    events = [
        {
            "id": "70001",
            "date": "2025-08-16T11:30:00Z",
            "status": {"type": {"state": "post", "name": "STATUS_FINAL"}},
            "competitions": [
                {
                    "competitors": [
                        {
                            "homeAway": "home",
                            "score": "2",
                            "team": {
                                "id": "359",
                                "displayName": "Arsenal",
                                "shortDisplayName": "Arsenal",
                                "abbreviation": "ARS",
                            },
                        },
                        {
                            "homeAway": "away",
                            "score": "1",
                            "team": {
                                "id": "364",
                                "displayName": "Liverpool",
                                "shortDisplayName": "Liverpool",
                                "abbreviation": "LIV",
                            },
                        },
                    ],
                    "venue": {"fullName": "Emirates Stadium"},
                }
            ],
        }
    ]
    rows = crawler._convert_espn_events(events, "EPL")
    assert len(rows) == 1
    m = rows[0]
    assert m["home_team_id"] == "ARS"
    assert m["away_team_id"] == "LIV"
    assert m["status"] == "finished"
    assert m["result"] == "H"
    assert m["home_goals"] == 2
    assert m["away_goals"] == 1
    assert m["venue"] == "Emirates Stadium"
    assert m["process_id"] == "70001"
    assert m["match_date"] == date(2025, 8, 16)
    assert isinstance(m["match_time"], dt_time)


def test_crawl_fixtures_500_first(monkeypatch):
    from services.real_team_crawler import RealTeamCrawler

    crawler = RealTeamCrawler.__new__(RealTeamCrawler)
    calls = {"espn": 0, "five00": 0, "enrich": 0}

    def fake_espn(*_a, **_k):
        calls["espn"] += 1
        return [{"id": "E1"}]

    def fake_500(*_a, **_k):
        calls["five00"] += 1
        return [{"id": "F1", "fixture_id": "123", "match_date": date(2025, 8, 16),
                 "home_team_id": "ARS", "away_team_id": "LIV", "status": "upcoming"}]

    def fake_enrich(base, *_a, **_k):
        calls["enrich"] += 1
        return base

    monkeypatch.setattr(crawler, "_crawl_espn_fixtures", fake_espn)
    monkeypatch.setattr(crawler, "_crawl_500_fixtures", fake_500)
    monkeypatch.setattr(crawler, "_maybe_enrich_fixtures_espn", fake_enrich)

    out = crawler.crawl_fixtures("EPL")
    assert out[0]["id"] == "F1"
    assert calls["five00"] == 1
    assert calls["espn"] == 0
    assert calls["enrich"] == 1


def test_crawl_fixtures_500_empty_falls_back_to_espn(monkeypatch):
    from services.real_team_crawler import RealTeamCrawler

    crawler = RealTeamCrawler.__new__(RealTeamCrawler)
    monkeypatch.setattr(crawler, "_crawl_500_fixtures", lambda *_a, **_k: [])
    monkeypatch.setattr(
        crawler,
        "_crawl_espn_fixtures",
        lambda *_a, **_k: [{"id": "E-fallback"}],
    )
    out = crawler.crawl_fixtures("EPL")
    assert out[0]["id"] == "E-fallback"


def test_crawl_fixtures_no_500_url_uses_espn(monkeypatch):
    """EC 等无 CANONICAL_FIVE00_URL 时走 ESPN。"""
    from services.real_team_crawler import RealTeamCrawler

    crawler = RealTeamCrawler.__new__(RealTeamCrawler)
    monkeypatch.setattr(
        crawler,
        "_crawl_500_fixtures",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not call 500")),
    )
    monkeypatch.setattr(
        crawler,
        "_crawl_espn_fixtures",
        lambda *_a, **_k: [{"id": "E-ec"}],
    )
    out = crawler.crawl_fixtures("EC")
    assert out[0]["id"] == "E-ec"


def test_uel_has_500_url():
    from services.real_team_crawler import CANONICAL_FIVE00_URL, FIVE00_TO_CANONICAL

    assert "UEL" in CANONICAL_FIVE00_URL
    assert "zuqiu-20000" in CANONICAL_FIVE00_URL["UEL"]
    assert FIVE00_TO_CANONICAL.get("LS20000") == "UEL"


def test_crawl_fixtures_non_espn_uses_500(monkeypatch):
    from services.real_team_crawler import RealTeamCrawler

    crawler = RealTeamCrawler.__new__(RealTeamCrawler)
    monkeypatch.setattr(
        crawler,
        "_crawl_espn_fixtures",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not call ESPN")),
    )
    monkeypatch.setattr(
        crawler,
        "_crawl_500_fixtures",
        lambda league_id, url, **_k: [{"id": "F-only", "league_id": league_id}],
    )
    out = crawler.crawl_fixtures("LS99999", source_url="https://liansai.500.com/zuqiu-99999/")
    assert out[0]["id"] == "F-only"


def test_enrich_preserves_fixture_id():
    from services.real_team_crawler import RealTeamCrawler

    crawler = RealTeamCrawler.__new__(RealTeamCrawler)
    base = [{
        "fixture_id": "999001",
        "home_team_id": "ARS",
        "away_team_id": "LIV",
        "match_date": date(2025, 8, 16),
        "status": "upcoming",
        "venue": "",
        "process_id": None,
        "home_goals": 0,
        "away_goals": 0,
        "result": None,
    }]
    espn = [{
        "home_team_id": "ARS",
        "away_team_id": "LIV",
        "match_date": date(2025, 8, 16),
        "status": "finished",
        "venue": "Emirates Stadium",
        "process_id": "70001",
        "home_goals": 2,
        "away_goals": 1,
        "result": "H",
        "fixture_id": "SHOULD_NOT_APPLY",
    }]
    out = crawler._enrich_fixtures_from_espn(base, espn)
    assert out[0]["fixture_id"] == "999001"
    assert out[0]["venue"] == "Emirates Stadium"
    assert out[0]["process_id"] == "70001"
    assert out[0]["status"] == "finished"
    assert out[0]["result"] == "H"


def test_merge_espn_onto_500_keeps_chinese_name():
    from services.real_team_crawler import RealTeamCrawler

    crawler = RealTeamCrawler.__new__(RealTeamCrawler)
    zh = [{"id": "ARS", "name": "阿森纳", "short_name": "阿森纳", "source": "500.com"}]
    espn = [{"id": "ARS", "name": "Arsenal", "espn_id": "359", "remote_logo": "http://x/a.png"}]
    out = crawler._merge_espn_onto_500(zh, espn)
    assert out[0]["name"] == "阿森纳"
    assert out[0]["espn_id"] == "359"
    assert out[0]["remote_logo"] == "http://x/a.png"
    assert out[0]["source"] == "500+espn"
