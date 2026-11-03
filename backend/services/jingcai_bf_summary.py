"""历史比分自然月汇总。

样本与历史比分页相同：已写入比分 SP，且已过开赛时间。
上月为完整自然月，本月只统计截至今天已开赛的场次。

完赛判定与比分 Top3 一致：status=finished、result 非空、主客进球都有值。
进球默认值是 0，不能只凭比分判断是否完赛。

文案仅供分析对照，不构成投注建议。
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set

from services.jingcai_score_top3 import ALL_KEYS, score_key
from services.subscription_service import FEATURE_JINGCAI_BF

DISCLAIMER = "仅供分析，不构成投注建议"

_KEY_INDEX = {key: i for i, key in enumerate(ALL_KEYS)}
_OTHER_KEYS = ("胜其它", "平其它", "负其它")
_GOAL_LABELS = ("0", "1", "2", "3", "4", "5+")
_OUTCOMES = ("H", "D", "A")


def month_windows(today: date) -> List[Dict[str, Any]]:
    """上月完整自然月 + 本月截至 today。"""
    first_this = today.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    return [
        {
            "key": "last_month",
            "label": first_prev.strftime("%Y-%m"),
            "from": first_prev.isoformat(),
            "to": last_prev.isoformat(),
            "partial": False,
        },
        {
            "key": "this_month",
            "label": first_this.strftime("%Y-%m"),
            "from": first_this.isoformat(),
            "to": today.isoformat(),
            "partial": True,
        },
    ]


def _enum_value(value: Any) -> Any:
    if value is None:
        return None
    return getattr(value, "value", value)


def _rate(count: int, sample: int) -> Optional[float]:
    if not sample:
        return None
    return round(count / sample, 4)


def _avg(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _outcome_block(counter: Counter, sample: int) -> Dict[str, Any]:
    block: Dict[str, Any] = {"sample": sample}
    for key in _OUTCOMES:
        count = int(counter.get(key, 0))
        block[key] = {"count": count, "rate": _rate(count, sample)}
    return block


def is_finished_row(row: Dict[str, Any]) -> bool:
    """已完赛且赛果、进球都已回写。"""
    if row.get("status") != "finished":
        return False
    if row.get("result") not in _OUTCOMES:
        return False
    if row.get("home_goals") is None or row.get("away_goals") is None:
        return False
    return True


def _sp_map(odds_bf: Any) -> Optional[Dict[str, float]]:
    """31 个比分 SP 都是正数才参与最低 SP 对照。"""
    if not isinstance(odds_bf, dict):
        return None
    parsed: Dict[str, float] = {}
    for key in ALL_KEYS:
        raw = odds_bf.get(key)
        if raw is None or raw == "":
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        if value <= 0:
            return None
        parsed[key] = value
    return parsed


def _ranked_scores(sp: Dict[str, float]) -> List[str]:
    """SP 从低到高；并列时按竞彩比分键顺序。"""
    return sorted(ALL_KEYS, key=lambda key: (sp[key], _KEY_INDEX[key]))


def _handicap_outcome(home: int, away: int, handicap: Any) -> Optional[str]:
    if handicap is None or handicap == "":
        return None
    try:
        hc = int(handicap)
    except (TypeError, ValueError):
        return None
    diff = int(home) - int(away) + hc
    if diff > 0:
        return "H"
    if diff == 0:
        return "D"
    return "A"


def _goal_label(total: int) -> str:
    if total >= 5:
        return "5+"
    return str(total)


def aggregate_rows(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """把一个时间窗内的场次收成覆盖、赛果、进球、比分频次、SP 对照和联赛表。"""
    items = list(rows)
    finished = [row for row in items if is_finished_row(row)]
    leagues = {row.get("league_id") or "" for row in items}

    result_counter: Counter = Counter()
    goal_counter: Counter = Counter()
    score_counter: Counter = Counter()
    handicap_counter: Counter = Counter()
    totals: List[float] = []
    homes: List[float] = []
    aways: List[float] = []
    both_scored = 0
    clean_sheet = 0
    sp_sample = 0
    sp_top1 = 0
    sp_top3 = 0

    league_buckets: Dict[str, Dict[str, Any]] = {}

    for row in finished:
        home = int(row["home_goals"])
        away = int(row["away_goals"])
        result = row["result"]
        result_counter[result] += 1
        total = home + away
        totals.append(total)
        homes.append(home)
        aways.append(away)
        goal_counter[_goal_label(total)] += 1
        if home > 0 and away > 0:
            both_scored += 1
        if home == 0 or away == 0:
            clean_sheet += 1
        key = score_key(home, away)
        score_counter[key] += 1

        league_id = row.get("league_id") or ""
        bucket = league_buckets.setdefault(league_id, {
            "league_id": league_id,
            "league_name": row.get("league_name") or league_id or "未分类",
            "matches": 0,
            "finished": 0,
            "missing": 0,
            "home_wins": 0,
            "scores": Counter(),
            "sp_sample": 0,
            "sp_top1_hits": 0,
        })
        bucket["finished"] += 1
        if result == "H":
            bucket["home_wins"] += 1
        bucket["scores"][key] += 1

        hc = _handicap_outcome(home, away, row.get("handicap"))
        if hc:
            handicap_counter[hc] += 1

        sp = _sp_map(row.get("odds_bf"))
        if sp:
            ranked = _ranked_scores(sp)
            sp_sample += 1
            bucket["sp_sample"] += 1
            if key == ranked[0]:
                sp_top1 += 1
                bucket["sp_top1_hits"] += 1
            if key in ranked[:3]:
                sp_top3 += 1

    for row in items:
        league_id = row.get("league_id") or ""
        bucket = league_buckets.setdefault(league_id, {
            "league_id": league_id,
            "league_name": row.get("league_name") or league_id or "未分类",
            "matches": 0,
            "finished": 0,
            "missing": 0,
            "home_wins": 0,
            "scores": Counter(),
            "sp_sample": 0,
            "sp_top1_hits": 0,
        })
        bucket["matches"] += 1
        if row.get("league_name") and bucket["league_name"] in ("", league_id, "未分类"):
            bucket["league_name"] = row["league_name"]

    finished_n = len(finished)
    by_league = []
    for bucket in league_buckets.values():
        bucket["missing"] = bucket["matches"] - bucket["finished"]
        top = None
        if bucket["scores"]:
            top = sorted(
                bucket["scores"].items(),
                key=lambda item: (-item[1], _KEY_INDEX.get(item[0], 99)),
            )[0][0]
        by_league.append({
            "league_id": bucket["league_id"],
            "league_name": bucket["league_name"],
            "matches": bucket["matches"],
            "finished": bucket["finished"],
            "missing": bucket["missing"],
            "home_rate": _rate(bucket["home_wins"], bucket["finished"]),
            "top_score": top,
            "sp_sample": bucket["sp_sample"],
            "sp_top1_hits": bucket["sp_top1_hits"],
            "sp_top1_rate": _rate(bucket["sp_top1_hits"], bucket["sp_sample"]),
        })
    by_league.sort(key=lambda item: (-item["matches"], item["league_name"]))

    ranked_scores = sorted(
        score_counter.items(),
        key=lambda item: (-item[1], _KEY_INDEX.get(item[0], 99)),
    )
    score_freq = [
        {"score": key, "count": count, "rate": _rate(count, finished_n)}
        for key, count in ranked_scores[:10]
    ]

    return {
        "coverage": {
            "matches": len(items),
            "finished": finished_n,
            "missing": len(items) - finished_n,
            "leagues": len(leagues),
        },
        "results": _outcome_block(result_counter, finished_n),
        "goals": {
            "sample": finished_n,
            "avg_total": _avg(totals),
            "avg_home": _avg(homes),
            "avg_away": _avg(aways),
            "both_scored_count": both_scored,
            "both_scored_rate": _rate(both_scored, finished_n),
            "clean_sheet_count": clean_sheet,
            "clean_sheet_rate": _rate(clean_sheet, finished_n),
            "distribution": [
                {
                    "label": label,
                    "count": int(goal_counter.get(label, 0)),
                    "rate": _rate(int(goal_counter.get(label, 0)), finished_n),
                }
                for label in _GOAL_LABELS
            ],
        },
        "score_freq": score_freq,
        "score_other": {key: int(score_counter.get(key, 0)) for key in _OTHER_KEYS},
        "sp_compare": {
            "locked": False,
            "sample": sp_sample,
            "top1_hits": sp_top1,
            "top1_rate": _rate(sp_top1, sp_sample),
            "top3_hits": sp_top3,
            "top3_rate": _rate(sp_top3, sp_sample),
        },
        "handicap": _outcome_block(handicap_counter, sum(handicap_counter.values())),
        "by_league": by_league,
    }


def build_monthly_summary(rows: Iterable[Dict[str, Any]], today: Optional[date] = None) -> Dict[str, Any]:
    """按自然月切开样本。日期落在两个窗口之外的行不计入。"""
    today = today or date.today()
    windows = month_windows(today)
    grouped: Dict[str, List[Dict[str, Any]]] = {window["key"]: [] for window in windows}
    for row in rows:
        match_date = row.get("match_date")
        if not isinstance(match_date, date):
            continue
        iso = match_date.isoformat()
        for window in windows:
            if window["from"] <= iso <= window["to"]:
                grouped[window["key"]].append(row)
                break
    periods = []
    for window in windows:
        period = dict(window)
        period.update(aggregate_rows(grouped[window["key"]]))
        periods.append(period)
    return {
        "disclaimer": DISCLAIMER,
        "as_of": today.isoformat(),
        "sp_locked": False,
        "periods": periods,
    }


def mask_summary(payload: Dict[str, Any], entitlements: Optional[Set[str]] = None) -> Dict[str, Any]:
    """免费版不返回由全表比分 SP 算出的对照。"""
    if FEATURE_JINGCAI_BF in (entitlements or set()):
        return payload
    payload["sp_locked"] = True
    for period in payload.get("periods") or []:
        period["sp_compare"] = {"locked": True}
        for row in period.get("by_league") or []:
            row["sp_sample"] = None
            row["sp_top1_hits"] = None
            row["sp_top1_rate"] = None
    return payload


def load_summary_rows(db, league_id=None, league_ids=None, today: Optional[date] = None) -> List[Dict[str, Any]]:
    """读取上月 1 日到今天、且已过开赛的历史比分场次。"""
    from db.models import Match
    from services import MatchService

    today = today or date.today()
    windows = month_windows(today)
    start = date.fromisoformat(windows[0]["from"])
    end = date.fromisoformat(windows[1]["to"])
    query = MatchService._build_jingcai_expired_bf_query(
        db, league_id=league_id, league_ids=league_ids
    )
    query = query.filter(Match.match_date >= start, Match.match_date <= end)
    rows = []
    for match in query.all():
        league = getattr(match, "league", None)
        rows.append({
            "match_date": match.match_date,
            "league_id": match.league_id,
            "league_name": getattr(league, "name", None) or match.league_id or "未分类",
            "status": _enum_value(match.status),
            "result": _enum_value(match.result),
            "home_goals": match.home_goals,
            "away_goals": match.away_goals,
            "handicap": match.handicap,
            "odds_bf": MatchService._parse_odds_bf(getattr(match, "odds_bf_json", None)),
        })
    return rows


def build_monthly_summary_from_db(
    db,
    league_id=None,
    league_ids=None,
    today: Optional[date] = None,
    entitlements: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    today = today or date.today()
    rows = load_summary_rows(db, league_id=league_id, league_ids=league_ids, today=today)
    payload = build_monthly_summary(rows, today=today)
    return mask_summary(payload, entitlements)
