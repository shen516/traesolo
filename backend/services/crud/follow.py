"""用户关注联赛 CRUD。"""
from services.crud._common import *
from services.crud.league import LeagueService

MAX_FOLLOWED_LEAGUES = 20


class FollowService:
    @staticmethod
    def get_ids(db: Session, user_id: int):
        rows = (
            db.query(UserFollowedLeague.league_id)
            .filter(UserFollowedLeague.user_id == user_id)
            .order_by(UserFollowedLeague.sort_order, UserFollowedLeague.id)
            .all()
        )
        return [r[0] for r in rows if r[0]]

    @staticmethod
    def child_map(db: Session, parent_ids, active_only=True):
        """parent_id -> 直接下级联赛 id。子项不计入关注上限。"""
        if not parent_ids:
            return {}
        query = db.query(League.id, League.parent_id).filter(League.parent_id.in_(parent_ids))
        if active_only:
            query = query.filter(League.is_active.is_(True))
        mapping = {}
        for child_id, parent_id in query.all():
            if not child_id or not parent_id:
                continue
            mapping.setdefault(parent_id, []).append(child_id)
        return mapping

    @staticmethod
    def expand_ids(db: Session, ids, include_children=False, active_only=True):
        """直接关注展开为赛事/风控过滤 id。空列表保持空，不回退全量。"""
        base = [lid for lid in (ids or []) if lid]
        if not base:
            return []
        if active_only:
            active = {
                row[0]
                for row in db.query(League.id).filter(League.id.in_(base), League.is_active.is_(True)).all()
            }
            base = [lid for lid in base if lid in active]
        if not include_children or not base:
            return base
        mapping = FollowService.child_map(db, base, active_only=active_only)
        seen = set()
        out = []
        for lid in base:
            if lid not in seen:
                out.append(lid)
                seen.add(lid)
            for child_id in mapping.get(lid, []):
                if child_id not in seen:
                    out.append(child_id)
                    seen.add(child_id)
        return out

    @staticmethod
    def get_filter_ids(db: Session, user_id: int, include_children=False):
        return FollowService.expand_ids(
            db, FollowService.get_ids(db, user_id), include_children, active_only=True
        )

    @staticmethod
    def serialize_state(db: Session, user_id: int, include_children=False):
        leagues = FollowService.list_followed(db, user_id)
        ids = [item["id"] for item in leagues]
        mapping = FollowService.child_map(db, ids, active_only=True)
        filter_ids = FollowService.expand_ids(db, ids, include_children, active_only=True)
        return {
            "leagues": leagues,
            "ids": ids,
            "filter_ids": filter_ids,
            "child_map": mapping,
            "include_children": bool(include_children),
        }

    @staticmethod
    def get_row(db: Session, user_id: int, league_id: str):
        return db.query(UserFollowedLeague).filter(
            UserFollowedLeague.user_id == user_id,
            UserFollowedLeague.league_id == league_id,
        ).first()

    @staticmethod
    def _league_payload(db: Session, league: League, follow: UserFollowedLeague = None):
        teams_count = db.query(func.count(Team.id)).filter(Team.league_id == league.id).scalar() or 0
        upcoming_count = db.query(func.count(Match.id)).filter(
            Match.league_id == league.id,
            Match.status == "upcoming",
            Match.match_date >= date.today(),
        ).scalar() or 0
        payload = LeagueService.to_dict(
            league,
            teams_count=teams_count,
            matches_count=upcoming_count,
        )
        payload["upcoming_count"] = int(upcoming_count)
        payload["child_ids"] = []
        if follow:
            payload["sort_order"] = follow.sort_order or 0
            payload["followed_at"] = follow.created_at.isoformat() if follow.created_at else None
        return payload

    @staticmethod
    def list_followed(db: Session, user_id: int):
        rows = (
            db.query(UserFollowedLeague, League)
            .join(League, UserFollowedLeague.league_id == League.id)
            .filter(UserFollowedLeague.user_id == user_id)
            .order_by(UserFollowedLeague.sort_order, UserFollowedLeague.id)
            .all()
        )
        payloads = [FollowService._league_payload(db, league, follow) for follow, league in rows]
        mapping = FollowService.child_map(db, [item["id"] for item in payloads], active_only=True)
        for item in payloads:
            item["child_ids"] = mapping.get(item["id"], [])
        return payloads

    @staticmethod
    def follow(db: Session, user_id: int, league_id: str):
        existing = FollowService.get_row(db, user_id, league_id)
        if existing:
            league = LeagueService.get_by_id(db, league_id)
            return existing, FollowService._league_payload(db, league, existing) if league else None

        league = LeagueService.get_by_id(db, league_id)
        if not league:
            raise ValueError("联赛不存在")
        if not league.is_active:
            raise ValueError("联赛已停用，无法关注")

        current = db.query(func.count(UserFollowedLeague.id)).filter(
            UserFollowedLeague.user_id == user_id
        ).scalar() or 0
        if current >= MAX_FOLLOWED_LEAGUES:
            raise ValueError(f"最多关注 {MAX_FOLLOWED_LEAGUES} 个联赛")

        next_order = current
        row = UserFollowedLeague(
            user_id=user_id,
            league_id=league_id,
            sort_order=next_order,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row, FollowService._league_payload(db, league, row)

    @staticmethod
    def unfollow(db: Session, user_id: int, league_id: str):
        row = FollowService.get_row(db, user_id, league_id)
        if row:
            db.delete(row)
            db.commit()
        return row

    @staticmethod
    def replace(db: Session, user_id: int, league_ids: list):
        ids = []
        seen = set()
        for raw in league_ids or []:
            lid = str(raw or "").strip()
            if not lid or lid in seen:
                continue
            seen.add(lid)
            ids.append(lid)

        if len(ids) > MAX_FOLLOWED_LEAGUES:
            raise ValueError(f"最多关注 {MAX_FOLLOWED_LEAGUES} 个联赛")

        existing = set(FollowService.get_ids(db, user_id))
        for lid in ids:
            league = LeagueService.get_by_id(db, lid)
            if not league:
                raise ValueError(f"联赛不存在：{lid}")
            if not league.is_active and lid not in existing:
                raise ValueError(f"联赛已停用，无法关注：{league.name}")

        db.query(UserFollowedLeague).filter(UserFollowedLeague.user_id == user_id).delete(
            synchronize_session=False
        )
        for idx, lid in enumerate(ids):
            db.add(UserFollowedLeague(user_id=user_id, league_id=lid, sort_order=idx))
        db.commit()
        return FollowService.list_followed(db, user_id)

    @staticmethod
    def build_summary(
        db: Session,
        user_id: int,
        entitlements=None,
        match_limit: int = 8,
        per_league_matches: int = 0,
        standings_limit: int = 8,
        scorers_limit: int = 5,
        include_alerts: bool = False,
        include_children: bool = False,
    ):
        """首页 / 关注页聚合：关注列表 + 未赛 + 积分榜/射手 + 可选风控。"""
        from fastapi.encoders import jsonable_encoder
        from services.crud.match import MatchService
        from services.crud.risk import RiskService
        from services.crud.scorer import ScorerService
        from services.crud.standing import StandingService
        from services.subscription_service import mask_match_list, mask_risk_alerts

        state = FollowService.serialize_state(db, user_id, include_children)
        leagues = state["leagues"]
        ids = state["ids"]
        filter_ids = state["filter_ids"]
        mapping = state["child_map"]
        empty = {
            **state,
            "matches": [],
            "boards": [],
            "alerts": [],
        }
        if not ids:
            return empty

        matches = []
        if per_league_matches > 0:
            seen = set()
            for lid in ids:
                query_ids = [lid]
                if include_children:
                    query_ids = [lid] + mapping.get(lid, [])
                rows = MatchService.get_paginated_upcoming(
                    db, page=1, page_size=per_league_matches, league_ids=query_ids
                )
                for row in rows:
                    if row.id in seen:
                        continue
                    seen.add(row.id)
                    matches.append(row)
        else:
            matches = MatchService.get_paginated_upcoming(
                db, page=1, page_size=match_limit, league_ids=filter_ids
            )

        serialized = MatchService.serialize_summary(db, matches)
        if entitlements is not None:
            serialized = mask_match_list(serialized, entitlements)

        boards = []
        for lid in ids:
            meta = next((item for item in leagues if item["id"] == lid), None)
            standings = StandingService.get_by_league(db, lid)[:standings_limit]
            scorers = ScorerService.get_by_league(db, lid)[:scorers_limit]
            season = None
            if standings:
                season = standings[0].season
            elif scorers:
                season = scorers[0].season
            boards.append({
                "league_id": lid,
                "league_name": (meta or {}).get("name") or lid,
                "league_logo": (meta or {}).get("logo") or "",
                "league_icon": (meta or {}).get("icon") or "🏆",
                "season": season,
                "is_active": (meta or {}).get("is_active", True),
                "child_ids": mapping.get(lid, []),
                "standings": jsonable_encoder(standings),
                "scorers": jsonable_encoder(scorers),
            })

        alerts = []
        if include_alerts:
            raw_alerts = RiskService.list_filtered(db, league_ids=filter_ids)
            alerts = RiskService.serialize(db, raw_alerts)
            if entitlements is not None:
                alerts = mask_risk_alerts(alerts, entitlements)

        return {
            **state,
            "matches": serialized,
            "boards": boards,
            "alerts": alerts,
        }
