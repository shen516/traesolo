"""Tests for match deduplication helpers."""
from datetime import date
from types import SimpleNamespace

from services.match_dedup import (
    canonical_match_id,
    choose_keeper,
    dedup_crawled_matches,
    is_legacy_match_id,
)


def test_canonical_match_id_truncates_to_50_chars():
    mid = canonical_match_id("EPL", date(2026, 3, 15), "MCI", "ARS")
    assert mid == "EPL-2026-03-15-MCI-ARS"
    assert len(mid) <= 50


def test_is_legacy_match_id():
    assert is_legacy_match_id("F123456")
    assert is_legacy_match_id("曼城-阿森纳")
    assert not is_legacy_match_id("EPL-2026-03-15-MCI-ARS")


def test_dedup_crawled_matches_prefers_fixture_id():
    rows = [
        {
            "id": "EPL-2026-03-15-MCI-ARS",
            "fixture_id": "9001",
            "home_team_id": "MCI",
            "away_team_id": "ARS",
        },
        {
            "id": "EPL-2026-03-14-MCI-ARS",
            "fixture_id": "9001",
            "odds_spf_win": 1.85,
        },
    ]
    out = dedup_crawled_matches(rows)
    assert len(out) == 1
    assert out[0]["fixture_id"] == "9001"
    assert out[0]["odds_spf_win"] == 1.85


def test_choose_keeper_prefers_canonical_id():
    canonical = SimpleNamespace(
      id="EPL-2026-03-15-MCI-ARS",
      fixture_id="9001",
      home_team_id="MCI",
      away_team_id="ARS",
    )
    legacy = SimpleNamespace(
      id="F9001",
      fixture_id=None,
      home_team_id="T12345",
      away_team_id="T67890",
    )
    keeper = choose_keeper([legacy, canonical])
    assert keeper.id == canonical.id
