"""P2 完善：TeamResolver、球队射门、500 解析、Live500 比分回写。"""

from services.five00_fenxi_crawler import Five00FenxiCrawler
from services.real_team_crawler import RealTeamCrawler
from services.team_resolver import TeamResolver


def test_team_resolver_wraps_alias():
    assert TeamResolver.resolve("arsenal") == "ARS"
    assert TeamResolver.is_clean("ARS") is True
    assert TeamResolver.is_clean("曼城") is False
    assert TeamResolver.resolve_clean("曼城") == "MCI"


def test_aggregate_team_shots_from_players():
    players = [
        {"team_id": "ARS", "is_home": True, "shots": 3, "shots_on_target": 1},
        {"team_id": "ARS", "is_home": True, "shots": 2, "shots_on_target": 2},
        {"team_id": "CHE", "is_home": False, "shots": 5, "shots_on_target": 1},
    ]
    rows = RealTeamCrawler.aggregate_team_shots_from_players(
        players, {"id": "ARS"}, {"id": "CHE"}
    )
    by_side = {r["is_home"]: r for r in rows}
    assert by_side[True]["shots"] == 5
    assert by_side[True]["shots_on_target"] == 3
    assert by_side[False]["shots"] == 5
    assert by_side[True]["source"] == "espn_agg"


def test_five00_fenxi_parses_table_and_text():
    html = """
    <table>
      <tr><td>12</td><td>射门</td><td>8</td></tr>
      <tr><td>4</td><td>射正</td><td>2</td></tr>
      <tr><td>55</td><td>控球率</td><td>45</td></tr>
    </table>
    """
    crawler = Five00FenxiCrawler()
    crawler._fetch_fenxi_shuju = lambda _fid: html
    crawler._fetch_mobile_analysis = lambda _fid: None
    rows = crawler.crawl_team_shots("123", "HOM", "AWY")
    assert len(rows) == 2
    home = next(r for r in rows if r["is_home"])
    away = next(r for r in rows if not r["is_home"])
    assert home["shots"] == 12 and away["shots"] == 8
    assert home["shots_on_target"] == 4 and away["shots_on_target"] == 2
    assert home["source"] == "500_fenxi"

    text_only = "技术统计 12 射门 10 3 射正 6"
    assert Five00FenxiCrawler._pair_from_text(text_only, ("射门",)) == (12, 10)
    assert Five00FenxiCrawler._pair_from_text(text_only, ("射正",)) == (3, 6)


def test_update_match_score_status(monkeypatch):
    import sys
    from services.crawler_service import crawler_service

    class FakeMatch:
        def __init__(self):
            self.status = "upcoming"
            self.home_goals = None
            self.away_goals = None
            self.result = None

    existing = FakeMatch()

    class FakeDB:
        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    mod = sys.modules["services.crawler_service"]
    monkeypatch.setattr(mod, "SessionLocal", lambda: FakeDB())
    monkeypatch.setattr(
        "services.match_dedup.find_existing_match",
        lambda *a, **k: existing,
    )
    monkeypatch.setattr(
        "services.team_resolver.TeamResolver.resolve_clean",
        lambda name: {"主队": "ARS", "客队": "CHE"}.get(name),
    )
    monkeypatch.setattr(
        "services.team_resolver.TeamResolver.is_clean",
        lambda tid: True,
    )

    updated, skipped = crawler_service._update_match_score_status([
        {
            "league_id": "EPL",
            "match_date": "2026-09-01",
            "home_team_name": "主队",
            "away_team_name": "客队",
            "status": "finished",
            "home_goals": 2,
            "away_goals": 1,
            "result": "H",
        }
    ])
    assert updated == 1
    assert skipped == 0
    assert existing.status == "finished"
    assert existing.home_goals == 2
    assert existing.away_goals == 1
    assert existing.result == "H"


def test_live500_registered_and_not_retired():
    from services.scheduled_tasks import RETIRED_TASK_IDS, get_task_definitions
    from services.crawler_service import crawler_service

    ids = [t[0] for t in get_task_definitions(crawler_service)]
    assert "live500_crawl" in ids
    assert "live500_crawl" not in RETIRED_TASK_IDS


def test_player_crawl_retired_cannot_schedule():
    from services.scheduled_tasks import RETIRED_TASK_IDS, get_task_definitions
    from services.scheduler_service import SchedulerService
    from services.crawler_service import crawler_service

    assert "player_crawl" in RETIRED_TASK_IDS
    assert "player_crawl" not in [t[0] for t in get_task_definitions(crawler_service)]

    svc = SchedulerService()
    try:
        svc.add_interval_task("player_crawl", lambda: None, 60)
        assert False, "expected ValueError for retired task"
    except ValueError as e:
        assert "retired" in str(e).lower()


def test_priority_train_description_mentions_dedupe():
    from services.scheduled_tasks import get_task_definitions
    from services.crawler_service import crawler_service

    defs = {t[0]: t for t in get_task_definitions(crawler_service)}
    assert "priority_train" in defs
    assert "跳过" in defs["priority_train"][5] or "双跑" in defs["priority_train"][5]