"""P1：补采策略、训练门槛、队名别名。"""
import json


def test_ucl_gets_extra_stats_quota():
    from services.crawler_service import crawler_service

    assert crawler_service._stats_limit_for_league("UCL", 150) == 230
    assert crawler_service._stats_limit_for_league("EPL", 150) == 150
    assert crawler_service._stats_limit_for_league("laliga", 50) == 50


def test_prefer_older_flips_after_scheduled_batch(monkeypatch):
    import sys
    from services.crawler_service import crawler_service

    class FakeLog:
        crawled_data = json.dumps({"prefer_older": True})

    class Query:
        def filter(self, * _a, **_k):
            return self

        def order_by(self, *_a):
            return self

        def first(self):
            return FakeLog()

    class FakeDB:
        def query(self, *_a):
            return Query()

        def close(self):
            pass

    monkeypatch.setattr(sys.modules["services.crawler_service"], "SessionLocal", lambda: FakeDB())
    assert crawler_service._stats_prefer_older_flag() is False


def test_skip_train_when_stats_delta_small(monkeypatch):
    class FakeDQ:
        def summary(self, _db):
            return {"training_lag": {"is_stale": False, "last_train_samples": 4000}}

    monkeypatch.setattr("services.data_quality_service.data_quality_service", FakeDQ())
    from services.crawler_service import crawler_service

    ok, reason = crawler_service._should_run_train_after_crawl(3)
    assert ok is False
    assert "跳过" in reason
    ok2, _ = crawler_service._should_run_train_after_crawl(80)
    assert ok2 is True


def test_train_when_no_prior_record(monkeypatch):
    class FakeDQ:
        def summary(self, _db):
            return {"training_lag": {"is_stale": False, "last_train_samples": None}}

    monkeypatch.setattr("services.data_quality_service.data_quality_service", FakeDQ())
    from services.crawler_service import crawler_service

    ok, reason = crawler_service._should_run_train_after_crawl(0)
    assert ok is True
    assert "训练记录" in reason


def test_resolve_team_alias_uses_db(monkeypatch):
    monkeypatch.setattr(
        "services.team_alias_service.lookup_confirmed_team_id",
        lambda name: "XYZ" if "zzzfc" in (name or "").lower() else None,
    )
    from services.real_team_crawler import resolve_team_alias

    assert resolve_team_alias("ZZZFC United") == "XYZ"
    assert resolve_team_alias("arsenal") == "ARS"
