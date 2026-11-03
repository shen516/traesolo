"""历史比分自然月汇总：窗口、完赛口径、比分归档、最低 SP 对照。"""

from datetime import date

from services.jingcai_bf_summary import (
    aggregate_rows,
    build_monthly_summary,
    is_finished_row,
    mask_summary,
    month_windows,
)
from services.jingcai_score_top3 import ALL_KEYS
from services.subscription_service import FEATURE_JINGCAI_BF

TODAY = date(2026, 10, 13)


def _sp(favorite="1:0", fav=3.2, second=None, second_sp=4.0, rest=9.0):
    data = {key: rest for key in ALL_KEYS}
    data[favorite] = fav
    if second:
        data[second] = second_sp
    return data


def _row(**kwargs):
    base = {
        "match_date": date(2026, 9, 6),
        "league_id": "EPL",
        "league_name": "英超",
        "status": "finished",
        "result": "H",
        "home_goals": 1,
        "away_goals": 0,
        "handicap": -1,
        "odds_bf": _sp("1:0"),
    }
    base.update(kwargs)
    return base


def test_month_windows_split_calendar_months():
    windows = month_windows(TODAY)
    assert windows[0]["key"] == "last_month"
    assert windows[0]["from"] == "2026-09-01"
    assert windows[0]["to"] == "2026-09-30"
    assert windows[0]["partial"] is False
    assert windows[1]["key"] == "this_month"
    assert windows[1]["from"] == "2026-10-01"
    assert windows[1]["to"] == "2026-10-13"
    assert windows[1]["partial"] is True


def test_unfinished_counts_as_missing_not_result():
    rows = [
        _row(),
        _row(status="upcoming", result=None, home_goals=0, away_goals=0),
        _row(status="finished", result=None, home_goals=2, away_goals=1),
    ]
    stats = aggregate_rows(rows)
    assert stats["coverage"]["matches"] == 3
    assert stats["coverage"]["finished"] == 1
    assert stats["coverage"]["missing"] == 2
    assert stats["results"]["sample"] == 1
    assert stats["results"]["H"]["count"] == 1
    assert stats["score_freq"][0]["score"] == "1:0"


def test_zero_zero_finished_is_kept():
    row = _row(result="D", home_goals=0, away_goals=0, handicap=0, odds_bf=_sp("0:0"))
    assert is_finished_row(row) is True
    stats = aggregate_rows([row])
    assert stats["results"]["D"]["count"] == 1
    assert stats["goals"]["avg_total"] == 0
    assert stats["goals"]["both_scored_count"] == 0
    assert stats["goals"]["clean_sheet_count"] == 1
    assert stats["handicap"]["D"]["count"] == 1


def test_score_other_and_goal_bucket():
    row = _row(home_goals=6, away_goals=0, result="H", handicap=-1, odds_bf=_sp("胜其它"))
    stats = aggregate_rows([row])
    assert stats["score_freq"][0]["score"] == "胜其它"
    assert stats["score_other"]["胜其它"] == 1
    assert stats["goals"]["distribution"][-1]["label"] == "5+"
    assert stats["goals"]["distribution"][-1]["count"] == 1
    assert stats["handicap"]["H"]["count"] == 1


def test_lowest_sp_top1_and_top3():
    hit = _row(home_goals=2, away_goals=1, odds_bf=_sp("2:1", second="1:0", second_sp=3.5))
    top3 = _row(
        home_goals=1,
        away_goals=0,
        odds_bf=_sp("2:1", fav=3.0, second="1:0", second_sp=3.4),
    )
    miss = _row(home_goals=0, away_goals=1, result="A", odds_bf=_sp("2:0"))
    incomplete = _row(home_goals=1, away_goals=1, result="D", odds_bf={"1:1": 6.5})
    stats = aggregate_rows([hit, top3, miss, incomplete])
    assert stats["sp_compare"]["sample"] == 3
    assert stats["sp_compare"]["top1_hits"] == 1
    assert stats["sp_compare"]["top3_hits"] == 2
    assert stats["score_freq"]
    assert any(item["score"] == "1:1" for item in stats["score_freq"])


def test_windows_drop_rows_outside_two_months():
    rows = [
        _row(match_date=date(2026, 8, 31)),
        _row(match_date=date(2026, 9, 30), league_id="L1", league_name="甲"),
        _row(match_date=date(2026, 10, 13), league_id="L2", league_name="乙", result="A", home_goals=0, away_goals=1),
        _row(match_date=date(2026, 10, 14)),
    ]
    payload = build_monthly_summary(rows, today=TODAY)
    last, current = payload["periods"]
    assert last["coverage"]["matches"] == 1
    assert last["by_league"][0]["league_name"] == "甲"
    assert current["coverage"]["matches"] == 1
    assert current["results"]["A"]["count"] == 1
    assert payload["disclaimer"]
    assert payload["as_of"] == "2026-10-13"


def test_empty_month_returns_zeros():
    payload = build_monthly_summary([], today=TODAY)
    last = payload["periods"][0]
    assert last["coverage"]["matches"] == 0
    assert last["results"]["H"]["rate"] is None
    assert last["goals"]["avg_total"] is None
    assert last["sp_compare"]["sample"] == 0
    assert last["score_freq"] == []
    assert last["by_league"] == []


def test_mask_hides_sp_without_jingcai_bf():
    payload = build_monthly_summary([_row()], today=TODAY)
    masked = mask_summary(payload, set())
    assert masked["sp_locked"] is True
    assert masked["periods"][0]["sp_compare"] == {"locked": True}
    assert masked["periods"][0]["sp_compare"].get("top1_rate") is None
    assert masked["periods"][0]["by_league"][0]["sp_top1_rate"] is None
    assert masked["periods"][0]["results"]["H"]["count"] == 1

    opened = build_monthly_summary([_row()], today=TODAY)
    kept = mask_summary(opened, {FEATURE_JINGCAI_BF})
    assert kept["sp_locked"] is False
    assert kept["periods"][0]["sp_compare"]["top1_hits"] == 1
