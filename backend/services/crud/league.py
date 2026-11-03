from services.crud._common import *
from services.league_parent import resolve_parent_id, infer_parent_id


class LeagueService:
    @staticmethod
    def get_all(db: Session):
        return db.query(League).all()

    @staticmethod
    def get_active(db: Session):
        return db.query(League).filter(League.is_active == True).all()

    @staticmethod
    def get_by_id(db: Session, league_id: str):
        return db.query(League).filter(League.id == league_id).first()

    @staticmethod
    def _apply_parent_id(db: Session, data: dict, league_id: str = None) -> dict:
        data = dict(data)
        if "parent_id" in data and data["parent_id"] == "":
            data["parent_id"] = None
        if data.get("parent_id"):
            parent = LeagueService.get_by_id(db, data["parent_id"])
            if not parent:
                data["parent_id"] = None
            elif league_id and data["parent_id"] == league_id:
                data["parent_id"] = None
            return data
        if "parent_id" not in data or data.get("parent_id") is None:
            name = data.get("name")
            country = data.get("country")
            level = data.get("level", 1)
            category = data.get("category", "international")
            if name is not None:
                data["parent_id"] = resolve_parent_id(
                    db, name, country, level, category, league_id
                )
            elif league_id:
                existing = LeagueService.get_by_id(db, league_id)
                if existing:
                    data["parent_id"] = resolve_parent_id(
                        db, existing.name, existing.country, existing.level,
                        existing.category or "international", league_id
                    )
        return data

    @staticmethod
    def create(db: Session, data: dict):
        data = LeagueService._apply_parent_id(db, data)
        if data.get("level", 1) <= 1:
            data["parent_id"] = None
        league = League(**data)
        db.add(league)
        db.commit()
        db.refresh(league)
        return league

    @staticmethod
    def update(db: Session, league_id: str, data: dict):
        league = db.query(League).filter(League.id == league_id).first()
        if league:
            merged = {
                "name": data.get("name", league.name),
                "country": data.get("country", league.country),
                "level": data.get("level", league.level),
                "category": data.get("category", league.category),
            }
            if "parent_id" in data:
                merged["parent_id"] = data["parent_id"]
            applied = LeagueService._apply_parent_id(db, merged, league_id)
            if data.get("level", league.level) <= 1:
                applied["parent_id"] = None
            for key, value in data.items():
                setattr(league, key, value)
            if "parent_id" in applied:
                league.parent_id = applied["parent_id"]
            elif data.get("level", league.level) <= 1:
                league.parent_id = None
            elif any(k in data for k in ("name", "country", "level", "category")):
                league.parent_id = applied.get("parent_id")
            db.commit()
            db.refresh(league)
        return league

    @staticmethod
    def toggle_active(db: Session, league_id: str):
        league = db.query(League).filter(League.id == league_id).first()
        if league:
            league.is_active = not league.is_active
            db.commit()
            db.refresh(league)
        return league

    @staticmethod
    def delete(db: Session, league_id: str):
        league = db.query(League).filter(League.id == league_id).first()
        if league:
            db.query(UserFollowedLeague).filter(UserFollowedLeague.league_id == league_id).delete(
                synchronize_session=False
            )
            db.query(UserPreference).filter(UserPreference.default_league_id == league_id).update(
                {UserPreference.default_league_id: None}, synchronize_session=False
            )
            db.query(League).filter(League.parent_id == league_id).update(
                {League.parent_id: None}, synchronize_session=False
            )
            db.delete(league)
            db.commit()
        return league

    @staticmethod
    def _build_query(db: Session, category=None, country=None, region=None, is_active=None, keyword=None):
        query = db.query(League)
        if category:
            query = query.filter(League.category == category)
        if country:
            query = query.filter(League.country == country)
        if region:
            query = query.filter(League.region == region)
        if is_active is not None:
            query = query.filter(League.is_active == is_active)
        if keyword:
            query = query.filter(League.name.contains(keyword))
        return query

    @staticmethod
    def to_dict(league, teams_count=0, matches_count=0, children_count=0, parent_name=None):
        return {
            "id": league.id,
            "name": league.name,
            "icon": league.icon,
            "region": league.region,
            "category": league.category,
            "country": league.country,
            "flag": league.flag,
            "level": league.level,
            "parent_id": league.parent_id,
            "parent_name": parent_name,
            "avg_goals": float(league.avg_goals) if league.avg_goals is not None else None,
            "is_active": bool(league.is_active),
            "source_url": league.source_url,
            "logo": league.logo,
            "teams_count": int(teams_count or 0),
            "matches_count": int(matches_count or 0),
            "children_count": int(children_count or 0),
        }

    @staticmethod
    def _duplicate_ids():
        try:
            from services.real_team_crawler import FIVE00_TO_CANONICAL
            return list(FIVE00_TO_CANONICAL.keys())
        except Exception:
            return []

    @staticmethod
    def _counts_query(db: Session):
        team_sub = db.query(
            Team.league_id.label("league_id"),
            func.count(Team.id).label("teams_count"),
        ).group_by(Team.league_id).subquery()
        match_sub = db.query(
            Match.league_id.label("league_id"),
            func.count(Match.id).label("matches_count"),
        ).group_by(Match.league_id).subquery()
        child_sub = db.query(
            League.parent_id.label("parent_id"),
            func.count(League.id).label("children_count"),
        ).filter(League.parent_id.isnot(None)).group_by(League.parent_id).subquery()
        query = db.query(
            League,
            func.coalesce(team_sub.c.teams_count, 0).label("teams_count"),
            func.coalesce(match_sub.c.matches_count, 0).label("matches_count"),
            func.coalesce(child_sub.c.children_count, 0).label("children_count"),
        ).outerjoin(team_sub, League.id == team_sub.c.league_id).outerjoin(
            match_sub, League.id == match_sub.c.league_id
        ).outerjoin(child_sub, League.id == child_sub.c.parent_id)
        return query, team_sub, match_sub

    @staticmethod
    def _apply_list_filters(query, team_sub, match_sub, category=None, country=None, region=None,
                            is_active=None, keyword=None, has_data=None, hide_duplicates=True,
                            level=None, parent_id=None, roots_only=False):
        if category:
            query = query.filter(League.category == category)
        if country:
            query = query.filter(League.country == country)
        if region:
            query = query.filter(League.region == region)
        if is_active is not None:
            query = query.filter(League.is_active == is_active)
        if keyword:
            query = query.filter(League.name.contains(keyword))
        if level is not None:
            query = query.filter(League.level == level)
        if parent_id is not None:
            query = query.filter(League.parent_id == parent_id)
        if roots_only:
            query = query.filter(League.parent_id.is_(None))
        if hide_duplicates:
            dups = LeagueService._duplicate_ids()
            if dups:
                query = query.filter(~League.id.in_(dups))
        if has_data:
            query = query.filter(
                (func.coalesce(team_sub.c.teams_count, 0) > 0) |
                (func.coalesce(match_sub.c.matches_count, 0) > 0)
            )
        return query

    @staticmethod
    def get_paginated(db: Session, page=1, page_size=20, category=None, country=None, region=None,
                      is_active=None, keyword=None, has_data=None, hide_duplicates=True,
                      level=None, parent_id=None, roots_only=False):
        query, team_sub, match_sub = LeagueService._counts_query(db)
        query = LeagueService._apply_list_filters(
            query, team_sub, match_sub, category=category, country=country, region=region,
            is_active=is_active, keyword=keyword, has_data=has_data, hide_duplicates=hide_duplicates,
            level=level, parent_id=parent_id, roots_only=roots_only,
        )
        query = query.order_by(
            desc(func.coalesce(team_sub.c.teams_count, 0)),
            desc(func.coalesce(match_sub.c.matches_count, 0)),
            League.level.asc(),
            League.name.asc(),
        )
        offset = (page - 1) * page_size
        rows = query.offset(offset).limit(page_size).all()
        return [
            LeagueService.to_dict(league, teams_count, matches_count, children_count)
            for league, teams_count, matches_count, children_count in rows
        ]

    @staticmethod
    def count(db: Session, category=None, country=None, region=None, is_active=None, keyword=None,
              has_data=None, hide_duplicates=True, level=None, parent_id=None, roots_only=False):
        query, team_sub, match_sub = LeagueService._counts_query(db)
        query = LeagueService._apply_list_filters(
            query, team_sub, match_sub, category=category, country=country, region=region,
            is_active=is_active, keyword=keyword, has_data=has_data, hide_duplicates=hide_duplicates,
            level=level, parent_id=parent_id, roots_only=roots_only,
        )
        return query.count()

    @staticmethod
    def get_children(db: Session, league_id: str, page=1, page_size=50):
        parent = LeagueService.get_by_id(db, league_id)
        if not parent:
            return None, 0
        query, team_sub, match_sub = LeagueService._counts_query(db)
        query = query.filter(League.parent_id == league_id)
        query = query.order_by(League.level.asc(), League.name.asc())
        total = query.count()
        offset = (page - 1) * page_size
        rows = query.offset(offset).limit(page_size).all()
        leagues = [
            LeagueService.to_dict(league, teams_count, matches_count, children_count, parent.name)
            for league, teams_count, matches_count, children_count in rows
        ]
        return leagues, total

    @staticmethod
    def get_categories(db: Session):
        from sqlalchemy import func
        results = db.query(League.category, func.count(League.id)).group_by(League.category).order_by(League.category).all()
        return [{"category": r[0], "count": r[1]} for r in results]

    @staticmethod
    def get_countries(db: Session, category=None):
        from sqlalchemy import func
        query = db.query(League.country, League.flag, func.count(League.id))
        if category:
            query = query.filter(League.category == category)
        query = query.filter(League.country.isnot(None))
        results = query.group_by(League.country, League.flag).order_by(League.country).all()
        return [{"country": r[0], "flag": r[1], "count": r[2]} for r in results]

    @staticmethod
    def get_root_options(db: Session):
        """供表单选择上级联赛：所有顶级（无 parent）联赛。"""
        rows = (
            db.query(League)
            .filter(League.parent_id.is_(None))
            .order_by(League.country.asc(), League.name.asc())
            .all()
        )
        return [{"id": r.id, "name": r.name, "country": r.country} for r in rows]
