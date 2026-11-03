"""赛事去重：采集入库查找、字段合并、历史重复数据归并。"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from db.models import (
    Match,
    MatchPlayerStat,
    MatchTeamStat,
    MatchPrediction,
    OddsSnapshot,
    RiskAlert,
    UserFavorite,
    UserHistory,
)
from services.crud_service import TeamService

logger = logging.getLogger(__name__)

RemapTeamFn = Callable[..., Optional[str]]

MATCH_MERGE_FIELDS = (
    "fixture_id",
    "process_id",
    "handicap",
    "odds_nspf_win",
    "odds_nspf_draw",
    "odds_nspf_lose",
    "odds_spf_win",
    "odds_spf_draw",
    "odds_spf_lose",
    "is_single",
    "buy_end_time",
    "venue",
    "weather",
    "temperature",
    "pitch_condition",
    "round_name",
    "match_time",
    "status",
    "home_goals",
    "away_goals",
    "result",
    "stage",
    "group_name",
)

ENV_FIELDS = frozenset({"venue", "weather", "temperature", "pitch_condition"})


def canonical_match_id(
    league_id: str,
    match_date,
    home_team_id: str,
    away_team_id: str,
) -> str:
    if hasattr(match_date, "strftime"):
        date_s = match_date.strftime("%Y-%m-%d")
    else:
        date_s = str(match_date)[:10]
    return f"{league_id}-{date_s}-{home_team_id}-{away_team_id}"[:50]


def is_legacy_match_id(match_id: Optional[str]) -> bool:
    if not match_id:
        return True
    if any("\u4e00" <= c <= "\u9fff" for c in match_id):
        return True
    return bool(re.fullmatch(r"F\d+", match_id))


def _is_transient_team_id(team_id: Optional[str]) -> bool:
    if not team_id:
        return True
    s = str(team_id)
    return bool(
        re.fullmatch(r"T\d{2,}", s)
        or re.fullmatch(r"ESPN\d+", s)
        or re.fullmatch(r"PE\d+", s)
    )


def resolve_ingest_teams(
    db: Session,
    league_id: str,
    home_team_id: Optional[str],
    away_team_id: Optional[str],
    home_team_name: Optional[str],
    away_team_name: Optional[str],
    remap_team_fn: RemapTeamFn,
) -> Optional[Tuple[str, str]]:
    from services.real_team_crawler import is_clean_team_id, resolve_team_alias

    resolved: List[str] = []
    for tid, tname in ((home_team_id, home_team_name), (away_team_id, away_team_name)):
        cand = tid
        if not is_clean_team_id(cand):
            cand = resolve_team_alias(tname or tid or "") or None
        if not is_clean_team_id(cand):
            cand = remap_team_fn(
                db, league_id, team_id=tid, team_name=tname, allow_global=True
            )
        if not is_clean_team_id(cand):
            return None
        if not TeamService.get_by_id(db, cand):
            return None
        resolved.append(cand)
    if len(resolved) != 2:
        return None
    return resolved[0], resolved[1]


def canonical_team_pair(
    db: Session,
    league_id: Optional[str],
    home_team_id: Optional[str],
    away_team_id: Optional[str],
    remap_team_fn: RemapTeamFn,
) -> Tuple[str, str]:
    from services.real_team_crawler import is_clean_team_id, resolve_team_alias

    lid = league_id or ""
    out: List[str] = []
    for tid in (home_team_id, away_team_id):
        cand = tid
        if not is_clean_team_id(cand):
            cand = resolve_team_alias(str(tid or "")) or None
        if not is_clean_team_id(cand):
            cand = remap_team_fn(db, lid, team_id=tid, team_name=tid, allow_global=True)
        if not is_clean_team_id(cand):
            cand = str(tid or "")
        out.append(cand)
    return out[0], out[1]


def match_identity_key(
    db: Session,
    match: Match,
    remap_team_fn: RemapTeamFn,
) -> Tuple:
    home, away = canonical_team_pair(
        db, match.league_id, match.home_team_id, match.away_team_id, remap_team_fn
    )
    return match.league_id, match.match_date, home, away


def find_existing_match(
    db: Session,
    *,
    league_id: str,
    match_date,
    home_team_id: str,
    away_team_id: str,
    fixture_id: Optional[str] = None,
    remap_team_fn: Optional[RemapTeamFn] = None,
) -> Optional[Match]:
    canonical_id = canonical_match_id(league_id, match_date, home_team_id, away_team_id)
    existing = db.query(Match).filter(Match.id == canonical_id).first()
    if existing:
        return existing

    fid = str(fixture_id or "").strip()
    if fid:
        by_fixture = db.query(Match).filter(Match.fixture_id == fid).first()
        if by_fixture:
            return by_fixture

    existing = db.query(Match).filter(
        Match.league_id == league_id,
        Match.match_date == match_date,
        Match.home_team_id == home_team_id,
        Match.away_team_id == away_team_id,
    ).first()
    if existing:
        return existing

    if not remap_team_fn:
        return None

    candidates = db.query(Match).filter(
        Match.league_id == league_id,
        Match.match_date == match_date,
    ).all()
    for candidate in candidates:
        ch, ca = canonical_team_pair(
            db,
            league_id,
            candidate.home_team_id,
            candidate.away_team_id,
            remap_team_fn,
        )
        if ch == home_team_id and ca == away_team_id:
            return candidate
    return None


def copy_missing_match_fields(keeper: Match, donor: Match) -> bool:
    changed = False
    for key in MATCH_MERGE_FIELDS:
        new_val = getattr(donor, key, None)
        if new_val in (None, ""):
            continue
        if key in ENV_FIELDS and new_val == "":
            continue
        old_val = getattr(keeper, key, None)
        if old_val in (None, "") and old_val != new_val:
            setattr(keeper, key, new_val)
            changed = True
    return changed


def _keeper_rank(match: Match) -> Tuple:
    canonical = not is_legacy_match_id(match.id)
    stable_teams = not _is_transient_team_id(match.home_team_id) and not _is_transient_team_id(
        match.away_team_id
    )
    has_fixture = bool(str(match.fixture_id or "").strip())
    return (
        int(canonical),
        int(stable_teams),
        int(has_fixture),
        len(match.id or ""),
    )


def choose_keeper(matches: List[Match]) -> Match:
    return max(matches, key=_keeper_rank)


def reassign_match_foreign_keys(db: Session, from_id: str, to_id: str) -> None:
    if from_id == to_id:
        return
    db.query(MatchPrediction).filter(MatchPrediction.match_id == from_id).update(
        {"match_id": to_id}, synchronize_session=False
    )
    db.query(MatchPlayerStat).filter(MatchPlayerStat.match_id == from_id).update(
        {"match_id": to_id}, synchronize_session=False
    )
    db.query(MatchTeamStat).filter(MatchTeamStat.match_id == from_id).update(
        {"match_id": to_id}, synchronize_session=False
    )
    db.query(OddsSnapshot).filter(OddsSnapshot.match_id == from_id).update(
        {"match_id": to_id}, synchronize_session=False
    )
    db.query(RiskAlert).filter(RiskAlert.match_id == from_id).update(
        {"match_id": to_id}, synchronize_session=False
    )
    db.query(UserFavorite).filter(UserFavorite.match_id == from_id).update(
        {"match_id": to_id}, synchronize_session=False
    )
    db.query(UserHistory).filter(UserHistory.match_id == from_id).update(
        {"match_id": to_id}, synchronize_session=False
    )


def delete_match_cascade(db: Session, match_id: str) -> None:
    db.query(MatchPrediction).filter(MatchPrediction.match_id == match_id).delete(
        synchronize_session=False
    )
    db.query(MatchPlayerStat).filter(MatchPlayerStat.match_id == match_id).delete(
        synchronize_session=False
    )
    db.query(MatchTeamStat).filter(MatchTeamStat.match_id == match_id).delete(
        synchronize_session=False
    )
    db.query(OddsSnapshot).filter(OddsSnapshot.match_id == match_id).delete(
        synchronize_session=False
    )
    db.query(RiskAlert).filter(RiskAlert.match_id == match_id).delete(
        synchronize_session=False
    )
    db.query(UserFavorite).filter(UserFavorite.match_id == match_id).delete(
        synchronize_session=False
    )
    db.query(UserHistory).filter(UserHistory.match_id == match_id).delete(
        synchronize_session=False
    )
    db.query(Match).filter(Match.id == match_id).delete(synchronize_session=False)


def merge_match_records(
    db: Session,
    keeper: Match,
    duplicate: Match,
    *,
    reassign_fks: bool = True,
) -> bool:
    if keeper.id == duplicate.id:
        return False
    changed = copy_missing_match_fields(keeper, duplicate)
    if reassign_fks:
        reassign_match_foreign_keys(db, duplicate.id, keeper.id)
    delete_match_cascade(db, duplicate.id)
    return changed or True


def _union_find_groups(match_ids: List[str], links: List[Tuple[str, str]]) -> Dict[str, str]:
    parent = {mid: mid for mid in match_ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a, b in links:
        if a in parent and b in parent:
            union(a, b)
    return parent


def find_duplicate_groups(
    db: Session,
    remap_team_fn: RemapTeamFn,
    *,
    status: Optional[str] = None,
    upcoming_only: bool = False,
) -> List[List[Match]]:
    query = db.query(Match)
    if status:
        query = query.filter(Match.status == status)
    if upcoming_only:
        query = query.filter(Match.status == "upcoming", Match.match_date >= date.today())
    matches = query.all()
    if not matches:
        return []

    by_id = {m.id: m for m in matches}
    links: List[Tuple[str, str]] = []
    sig_index: Dict[Tuple, str] = {}
    fixture_index: Dict[str, str] = {}

    for match in matches:
        sig = match_identity_key(db, match, remap_team_fn)
        prev = sig_index.get(sig)
        if prev:
            links.append((prev, match.id))
        else:
            sig_index[sig] = match.id

        fid = str(match.fixture_id or "").strip()
        if fid:
            prev_f = fixture_index.get(fid)
            if prev_f:
                links.append((prev_f, match.id))
            else:
                fixture_index[fid] = match.id

    parent = _union_find_groups(list(by_id.keys()), links)
    grouped: Dict[str, List[Match]] = defaultdict(list)
    for mid, match in by_id.items():
        grouped[_root(parent, mid)].append(match)

    return [grp for grp in grouped.values() if len(grp) > 1]


def _root(parent: Dict[str, str], node: str) -> str:
    while parent[node] != node:
        parent[node] = parent[parent[node]]
        node = parent[node]
    return node


def merge_all_duplicate_matches(
    db: Session,
    remap_team_fn: RemapTeamFn,
    *,
    dry_run: bool = False,
    status: Optional[str] = None,
    upcoming_only: bool = False,
) -> Dict:
    groups = find_duplicate_groups(
        db, remap_team_fn, status=status, upcoming_only=upcoming_only
    )
    stats = {
        "groups": len(groups),
        "merged": 0,
        "deleted": 0,
        "keepers": [],
        "removed_ids": [],
        "dry_run": dry_run,
    }
    for group in groups:
        keeper = choose_keeper(group)
        duplicates = [m for m in group if m.id != keeper.id]
        target_id = canonical_match_id(
            keeper.league_id or "",
            keeper.match_date,
            *safe_canonical_team_pair(
                db,
                keeper.league_id,
                keeper.home_team_id,
                keeper.away_team_id,
                remap_team_fn,
            ),
        )
        stats["keepers"].append(
            {
                "keeper_id": keeper.id,
                "target_id": target_id,
                "duplicate_ids": [m.id for m in duplicates],
            }
        )
        if dry_run:
            stats["merged"] += len(duplicates)
            stats["deleted"] += len(duplicates)
            stats["removed_ids"].extend(m.id for m in duplicates)
            continue

        home, away = safe_canonical_team_pair(
            db,
            keeper.league_id,
            keeper.home_team_id,
            keeper.away_team_id,
            remap_team_fn,
        )
        if TeamService.get_by_id(db, home):
            keeper.home_team_id = home
        if TeamService.get_by_id(db, away):
            keeper.away_team_id = away

        for donor in duplicates:
            merge_match_records(db, keeper, donor, reassign_fks=True)
            stats["merged"] += 1
            stats["deleted"] += 1
            stats["removed_ids"].append(donor.id)

        new_id = canonical_match_id(
            keeper.league_id or "",
            keeper.match_date,
            keeper.home_team_id,
            keeper.away_team_id,
        )
        if keeper.id != new_id and not db.query(Match).filter(Match.id == new_id).first():
            old_id = keeper.id
            payload = {
                c.name: getattr(keeper, c.name)
                for c in keeper.__table__.columns
                if c.name not in ("id", "created_at", "updated_at")
            }
            payload["id"] = new_id
            payload["home_team_id"] = keeper.home_team_id
            payload["away_team_id"] = keeper.away_team_id
            db.add(Match(**payload))
            db.flush()
            reassign_match_foreign_keys(db, old_id, new_id)
            db.query(Match).filter(Match.id == old_id).delete(synchronize_session=False)
            keeper = db.query(Match).filter(Match.id == new_id).first()
        db.flush()

    if not dry_run:
        db.commit()
    return stats


def safe_canonical_team_pair(
    db: Session,
    league_id: Optional[str],
    home_team_id: Optional[str],
    away_team_id: Optional[str],
    remap_team_fn: RemapTeamFn,
) -> Tuple[str, str]:
    home, away = canonical_team_pair(db, league_id, home_team_id, away_team_id, remap_team_fn)
    if not TeamService.get_by_id(db, home):
        home = home_team_id if TeamService.get_by_id(db, home_team_id) else home
    if not TeamService.get_by_id(db, away):
        away = away_team_id if TeamService.get_by_id(db, away_team_id) else away
    return home, away


def dedup_crawled_matches(raw_matches: List[Dict]) -> List[Dict]:
    """采集结果内存去重：优先 fixture_id，否则按 id。"""
    merged: Dict[str, Dict] = {}
    order: List[str] = []

    def merge_dict(a: Dict, b: Dict) -> Dict:
        out = dict(a)
        for key, val in b.items():
            if val in (None, ""):
                continue
            if key in ENV_FIELDS and val == "":
                continue
            if out.get(key) in (None, ""):
                out[key] = val
        return out

    for item in raw_matches or []:
        fid = str(item.get("fixture_id") or "").strip()
        key = f"fid:{fid}" if fid else f"id:{item.get('id') or ''}"
        if not key or key == "id:":
            key = f"row:{len(order)}"
        if key in merged:
            merged[key] = merge_dict(merged[key], item)
        else:
            merged[key] = dict(item)
            order.append(key)
    return [merged[k] for k in order]
