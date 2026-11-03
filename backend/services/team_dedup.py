"""球队去重与合并：同联赛同名球队归并到 canonical ID。"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from db.models import (
    Match,
    MatchPlayerStat,
    Player,
    Standing,
    Team,
    TopScorer,
    User,
    UserFavorite,
)


def _normalize_name(name: Optional[str]) -> str:
    return (name or "").strip().lower()


def _is_chinese_id(team_id: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in team_id)


def _is_t_numeric_id(team_id: str) -> bool:
    return bool(re.fullmatch(r"T\d+", team_id))


def _id_quality_score(team_id: str) -> int:
    """越高越适合作为保留 ID（短码优先于 T#### / 中文 ID）。"""
    if _is_chinese_id(team_id):
        return 0
    if _is_t_numeric_id(team_id):
        return 10
    if team_id.isascii() and 2 <= len(team_id) <= 8 and team_id.isupper():
        return 30
    if team_id.isascii():
        return 20
    return 5


def _ref_count(db: Session, team_id: str) -> int:
    total = 0
    total += db.query(Match).filter(
        or_(Match.home_team_id == team_id, Match.away_team_id == team_id)
    ).count()
    total += db.query(Player).filter(Player.team_id == team_id).count()
    total += db.query(MatchPlayerStat).filter(MatchPlayerStat.team_id == team_id).count()
    total += db.query(Standing).filter(Standing.team_id == team_id).count()
    total += db.query(TopScorer).filter(TopScorer.team_id == team_id).count()
    total += db.query(UserFavorite).filter(UserFavorite.team_id == team_id).count()
    total += db.query(User).filter(User.favorite_team_id == team_id).count()
    return total


def _pick_canonical(group: List[Team], db: Session) -> Team:
    def sort_key(t: Team) -> Tuple[int, int, float]:
        refs = _ref_count(db, t.id)
        quality = _id_quality_score(t.id)
        created = t.created_at.timestamp() if t.created_at else 0.0
        return (refs, quality, -created)

    return sorted(group, key=sort_key, reverse=True)[0]


def find_duplicate_groups(db: Session) -> List[Dict[str, Any]]:
    """按 league_id + name 查找重复球队组。"""
    teams = db.query(Team).all()
    buckets: Dict[Tuple[str, str], List[Team]] = defaultdict(list)
    for t in teams:
        if not (t.name or "").strip():
            continue
        buckets[(t.league_id or "", _normalize_name(t.name))].append(t)

    groups: List[Dict[str, Any]] = []
    for (league_id, norm_name), members in sorted(buckets.items()):
        if len(members) < 2:
            continue
        keep = _pick_canonical(members, db)
        drop = [t for t in members if t.id != keep.id]
        groups.append(
            {
                "league_id": league_id,
                "name": members[0].name,
                "keep_id": keep.id,
                "drop_ids": [t.id for t in drop],
                "members": [
                    {
                        "id": t.id,
                        "short_name": t.short_name,
                        "refs": _ref_count(db, t.id),
                        "id_quality": _id_quality_score(t.id),
                    }
                    for t in members
                ],
            }
        )
    return groups


def _merge_team_fields(keep: Team, drop: Team) -> None:
    """将 drop 的非空字段补全到 keep。"""
    for field in (
        "logo",
        "country",
        "home_ground",
        "founded_year",
        "short_name",
    ):
        if not getattr(keep, field) and getattr(drop, field):
            setattr(keep, field, getattr(drop, field))
    if (keep.elo_rating or 1500) == 1500 and (drop.elo_rating or 1500) != 1500:
        keep.elo_rating = drop.elo_rating


def _remap_standings(db: Session, keep_id: str, drop_id: str) -> Tuple[int, int]:
    updated = deleted = 0
    rows = db.query(Standing).filter(Standing.team_id == drop_id).all()
    for row in rows:
        conflict = (
            db.query(Standing)
            .filter(
                Standing.league_id == row.league_id,
                Standing.team_id == keep_id,
                Standing.season == row.season,
            )
            .first()
        )
        if conflict:
            if (row.played or 0) > (conflict.played or 0):
                conflict.rank = row.rank
                conflict.played = row.played
                conflict.won = row.won
                conflict.drawn = row.drawn
                conflict.lost = row.lost
                conflict.goals_for = row.goals_for
                conflict.goals_against = row.goals_against
                conflict.goal_diff = row.goal_diff
                conflict.points = row.points
                conflict.update_date = row.update_date
            db.delete(row)
            deleted += 1
        else:
            row.team_id = keep_id
            updated += 1
    return updated, deleted


def _remap_user_favorites(db: Session, keep_id: str, drop_id: str) -> Tuple[int, int]:
    updated = deleted = 0
    rows = db.query(UserFavorite).filter(UserFavorite.team_id == drop_id).all()
    for row in rows:
        conflict = (
            db.query(UserFavorite)
            .filter(
                UserFavorite.user_id == row.user_id,
                UserFavorite.team_id == keep_id,
            )
            .first()
        )
        if conflict:
            db.delete(row)
            deleted += 1
        else:
            row.team_id = keep_id
            updated += 1
    return updated, deleted


def _remap_simple(db: Session, model, column, keep_id: str, drop_id: str) -> int:
    return (
        db.query(model)
        .filter(column == drop_id)
        .update({column.key: keep_id}, synchronize_session=False)
    )


def merge_team_pair(db: Session, keep_id: str, drop_id: str) -> Dict[str, Any]:
    """将 drop_id 球队合并进 keep_id，并删除 drop 记录。"""
    if keep_id == drop_id:
        return {"keep_id": keep_id, "drop_id": drop_id, "skipped": True}

    keep = db.query(Team).filter(Team.id == keep_id).first()
    drop = db.query(Team).filter(Team.id == drop_id).first()
    if not keep or not drop:
        return {
            "keep_id": keep_id,
            "drop_id": drop_id,
            "skipped": True,
            "reason": "team_not_found",
        }

    stats: Dict[str, Any] = {
        "keep_id": keep_id,
        "drop_id": drop_id,
        "keep_name": keep.name,
        "drop_name": drop.name,
        "league_id": keep.league_id,
    }

    _merge_team_fields(keep, drop)

    stats["matches_home"] = _remap_simple(db, Match, Match.home_team_id, keep_id, drop_id)
    stats["matches_away"] = _remap_simple(db, Match, Match.away_team_id, keep_id, drop_id)
    stats["players"] = _remap_simple(db, Player, Player.team_id, keep_id, drop_id)
    stats["match_player_stats"] = _remap_simple(
        db, MatchPlayerStat, MatchPlayerStat.team_id, keep_id, drop_id
    )
    stats["top_scorers"] = _remap_simple(db, TopScorer, TopScorer.team_id, keep_id, drop_id)
    stats["users_favorite"] = _remap_simple(
        db, User, User.favorite_team_id, keep_id, drop_id
    )

    st_upd, st_del = _remap_standings(db, keep_id, drop_id)
    stats["standings_updated"] = st_upd
    stats["standings_deleted"] = st_del

    fav_upd, fav_del = _remap_user_favorites(db, keep_id, drop_id)
    stats["favorites_updated"] = fav_upd
    stats["favorites_deleted"] = fav_del

    db.delete(drop)
    stats["deleted"] = True
    return stats


def merge_all_duplicate_teams(db: Session, *, dry_run: bool = False) -> Dict[str, Any]:
    """合并全部同联赛同名重复球队。"""
    groups = find_duplicate_groups(db)
    result: Dict[str, Any] = {
        "dry_run": dry_run,
        "groups": len(groups),
        "teams_to_remove": sum(len(g["drop_ids"]) for g in groups),
        "plans": groups,
        "merges": [],
    }

    if dry_run:
        return result

    for group in groups:
        keep_id = group["keep_id"]
        for drop_id in group["drop_ids"]:
            merge_stats = merge_team_pair(db, keep_id, drop_id)
            result["merges"].append(merge_stats)

    db.commit()

    remaining = find_duplicate_groups(db)
    result["remaining_groups"] = len(remaining)
    result["finished_at"] = datetime.now().isoformat(timespec="seconds")
    return result
