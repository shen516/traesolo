"""P3：重点联赛扩围、赔率快照、伤病任务、长任务入队。"""

from services.odds_snapshot_service import has_any_odds, maybe_snapshot_odds, odds_tuple_from_obj
from services.real_team_crawler import PRIORITY_LEAGUES_DEFAULT, get_priority_leagues
from services.scheduled_tasks import get_task_definitions


def test_priority_leagues_include_uel():
    assert "UEL" in PRIORITY_LEAGUES_DEFAULT
    leagues = get_priority_leagues()
    assert "UEL" in leagues
    assert "EPL" in leagues


def test_injury_crawl_registered():
    from services.crawler_service import crawler_service

    defs = {d[0]: d for d in get_task_definitions(crawler_service)}
    assert "injury_crawl" in defs
    assert defs["injury_crawl"][2] == 120
    assert defs["injury_crawl"][4] == "injury"


def test_squad_crawl_registered():
    from services.crawler_service import crawler_service

    defs = {d[0]: d for d in get_task_definitions(crawler_service)}
    assert "squad_crawl" in defs
    assert defs["squad_crawl"][2] == 1440
    assert defs["squad_crawl"][4] == "squad"
    assert defs["squad_crawl"][1].__func__ is crawler_service.crawl_all_players.__func__
    assert "player_crawl" not in defs


def test_odds_tuple_and_has_any():
    empty = odds_tuple_from_obj({})
    assert has_any_odds(empty) is False
    filled = odds_tuple_from_obj({"odds_nspf_win": 1.85, "odds_nspf_draw": 3.4, "odds_nspf_lose": 4.2})
    assert has_any_odds(filled) is True
    assert filled[1] == 1.85


def test_maybe_snapshot_odds_on_change():
    class FakeMatch:
        id = "m1"
        fixture_id = "f1"
        handicap = None
        odds_nspf_win = 2.0
        odds_nspf_draw = 3.2
        odds_nspf_lose = 3.5
        odds_spf_win = None
        odds_spf_draw = None
        odds_spf_lose = None

    added = []

    class FakeDB:
        def add(self, obj):
            added.append(obj)

    match = FakeMatch()
    # 无变化 → 不写
    assert maybe_snapshot_odds(FakeDB(), match, {
        "odds_nspf_win": 2.0,
        "odds_nspf_draw": 3.2,
        "odds_nspf_lose": 3.5,
    }) is False
    assert not added

    # 有变化 → 写快照
    assert maybe_snapshot_odds(FakeDB(), match, {
        "odds_nspf_win": 1.9,
        "odds_nspf_draw": 3.3,
        "odds_nspf_lose": 3.8,
        "fixture_id": "f1",
    }) is True
    assert len(added) == 1
    assert added[0].match_id == "m1"
    assert float(added[0].odds_nspf_win) == 1.9
    assert added[0].odds_bf_json is None


def test_snapshot_bf_change_keeps_existing_odds_and_seeds_once():
    from datetime import datetime, timedelta

    from services.odds_snapshot_service import maybe_snapshot_odds, normalize_bf_json

    bf = {"1:0": 7.5, "1:1": 6.0}
    later = {"1:0": 8.0, "1:1": 5.5}
    kickoff = datetime(2026, 10, 20, 20, 0, 0)

    class FakeMatch:
        id = "m1"
        fixture_id = "f1"
        handicap = -1
        odds_nspf_win = 2.0
        odds_nspf_draw = 3.2
        odds_nspf_lose = 3.5
        odds_spf_win = 1.8
        odds_spf_draw = 3.4
        odds_spf_lose = 3.6
        odds_bf_json = normalize_bf_json(bf)
        match_date = kickoff.date()
        match_time = kickoff.time()

    added = []
    existing = []

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def limit(self, n):
            return self

        def first(self):
            return existing[0] if existing else None

    class FakeDB:
        def add(self, obj):
            added.append(obj)

        def query(self, *args):
            return FakeQuery()

    same_odds = {
        "handicap": -1,
        "odds_nspf_win": 2.0,
        "odds_nspf_draw": 3.2,
        "odds_nspf_lose": 3.5,
        "odds_spf_win": 1.8,
        "odds_spf_draw": 3.4,
        "odds_spf_lose": 3.6,
        "odds_bf_json": bf,
    }
    match = FakeMatch()
    before = kickoff - timedelta(hours=2)
    assert maybe_snapshot_odds(FakeDB(), match, same_odds, now=before) is True
    assert json_has_score(added[0].odds_bf_json, "1:0", 7.5)
    assert float(added[0].odds_nspf_win) == 2.0

    existing.append(added[0])
    assert maybe_snapshot_odds(FakeDB(), match, same_odds, now=before) is False

    assert maybe_snapshot_odds(FakeDB(), match, {"odds_bf_json": later}, now=before) is True
    assert float(added[-1].odds_nspf_win) == 2.0
    assert json_has_score(added[-1].odds_bf_json, "1:0", 8.0)

    after = kickoff + timedelta(hours=1)
    fresh = []

    class FreshDB(FakeDB):
        def add(self, obj):
            fresh.append(obj)

    assert maybe_snapshot_odds(FreshDB(), match, same_odds, now=after) is False
    assert fresh == []


def json_has_score(raw, key, value):
    import json
    data = json.loads(raw)
    return data[key] == value


def test_pick_pre_match_bf_uses_last_frame_before_kickoff():
    from datetime import datetime

    from services.odds_snapshot_service import pick_pre_match_bf

    kickoff = datetime(2026, 10, 20, 20, 0, 0)

    class Row:
        def __init__(self, match_id, captured_at, odds_bf_json):
            self.match_id = match_id
            self.captured_at = captured_at
            self.odds_bf_json = odds_bf_json

    rows = [
        Row("m1", kickoff.replace(hour=10), {"1:0": 7.0}),
        Row("m1", kickoff.replace(hour=18), {"1:0": 8.0, "1:1": 6.0}),
        Row("m1", kickoff.replace(hour=21), {"1:0": 3.0}),
        Row("m2", kickoff.replace(hour=12), {}),
        Row("m2", kickoff.replace(hour=22), {"0:0": 9.0}),
    ]
    picked = pick_pre_match_bf(rows, {"m1": kickoff, "m2": kickoff})
    assert json_has_score(picked["m1"], "1:0", 8.0)
    assert "m2" not in picked


def test_enqueue_p0_and_backfill(monkeypatch):
    from services import job_queue

    monkeypatch.setattr(job_queue, "_queue_enabled", lambda: False)
    calls = []

    def fake_thread(kind, func, meta=None):
        calls.append(kind)
        return {"mode": "thread", "job_id": f"local-{kind}-test", "status": "started", **(meta or {})}

    monkeypatch.setattr(job_queue, "_enqueue_thread", fake_thread)

    p0 = job_queue.enqueue_p0(stats_limit_per_league=10, env_limit=50, train=False)
    assert p0["job_id"] == "local-p0-test"
    assert "p0" in calls

    bf = job_queue.enqueue_stats_backfill(limit_per_league=20, prefer_older=True)
    assert bf["job_id"] == "local-stats_backfill-test"
    assert "stats_backfill" in calls

    en = job_queue.enqueue_enrich_priority(include_history=False, seasons_back=1)
    assert en["job_id"] == "local-enrich-test"
    assert "enrich" in calls

    uel = job_queue.enqueue_uel_catchup(include_history=False, seasons_back=1, stats_limit=20, train=False)
    assert uel["job_id"] == "local-uel-test"
    assert "uel" in calls


def test_crawl_injuries_delegates(monkeypatch):
    from services.crawler_service import crawler_service

    monkeypatch.setattr(
        "services.injury_crawler_service.injury_crawler_service.crawl_priority_injuries",
        lambda crawl_type="scheduled": {"status": "success", "alerts_upserted": 0, "crawl_type": crawl_type},
    )
    out = crawler_service.crawl_injuries(crawl_type="manual")
    assert out["status"] == "success"
    assert out["crawl_type"] == "manual"


def test_p0_status_shared_store_roundtrip(monkeypatch):
    from services import p0_status_store

    store = {}

    class FakeRedis:
        def get(self, key):
            return store.get(key)

        def set(self, key, value, ex=None):
            store[key] = value
            return True

    monkeypatch.setattr(p0_status_store, "get_redis_client", lambda: FakeRedis())
    payload = {"running": True, "phase": "stats", "job_id": "abc"}
    assert p0_status_store.save_shared_p0_status(payload) is True
    got = p0_status_store.load_shared_p0_status()
    assert got["phase"] == "stats"
    assert got["job_id"] == "abc"


def test_get_p0_status_reads_shared_when_idle(monkeypatch):
    from services.crawler_service import crawler_service

    crawler_service._p0_status = crawler_service._empty_p0_status()
    monkeypatch.setattr(
        "services.p0_status_store.load_shared_p0_status",
        lambda: {
            "running": True,
            "status": "running",
            "phase": "train",
            "message": "worker training",
            "started_at": "2026-01-01T00:00:00",
            "finished_at": None,
            "error": None,
            "progress": {},
            "result": None,
            "job_id": "rq-1",
            "job_mode": "rq",
        },
    )
    st = crawler_service.get_p0_status()
    assert st["running"] is True
    assert st["phase"] == "train"
    assert st["job_id"] == "rq-1"


def test_run_uel_catchup_orchestrates(monkeypatch):
    from services.crawler_service import crawler_service

    monkeypatch.setattr(
        crawler_service,
        "enrich_league",
        lambda *a, **k: {"status": "success", "league_id": "UEL"},
    )
    monkeypatch.setattr(
        crawler_service,
        "crawl_match_player_stats",
        lambda **k: {"status": "success", "espn_hits": 2, "saved_matches": 2},
    )
    monkeypatch.setattr(crawler_service, "_save_crawl_log", lambda **k: None)

    out = crawler_service.run_uel_catchup(include_history=False, stats_limit=10, train=False)
    assert out["league_id"] == "UEL"
    assert out["stats"]["saved_matches"] == 2
    assert out["train"]["status"] == "skipped"
