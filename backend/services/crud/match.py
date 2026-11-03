from services.crud._common import *
from services.crud.prediction import PredictionService

class MatchService:
    @staticmethod
    def get_all(db: Session):
        return db.query(Match).join(League).filter(League.is_active == True).order_by(desc(Match.match_date), Match.match_time).all()

    @staticmethod
    def get_by_id(db: Session, match_id: str):
        from sqlalchemy.orm import joinedload
        return (
            db.query(Match)
            .options(
                joinedload(Match.league),
                joinedload(Match.home_team),
                joinedload(Match.away_team),
            )
            .filter(Match.id == match_id)
            .first()
        )

    @staticmethod
    def team_brief(team):
        """列表/详情嵌套球队精简字段，避免前端再拉全量 teams。"""
        if not team:
            return None
        return {
            "id": team.id,
            "name": team.name,
            "short_name": team.short_name,
            "logo": team.logo,
            "league_id": team.league_id,
            "elo_rating": team.elo_rating,
        }

    @staticmethod
    def league_brief(league):
        if not league:
            return None
        return {
            "id": league.id,
            "name": league.name,
            "icon": league.icon,
            "logo": league.logo,
            "category": getattr(league, "category", None) or "domestic",
            "country": getattr(league, "country", None) or "",
        }

    @staticmethod
    def attach_relation_briefs(item: dict, match) -> dict:
        item["home_team"] = MatchService.team_brief(getattr(match, "home_team", None))
        item["away_team"] = MatchService.team_brief(getattr(match, "away_team", None))
        item["league"] = MatchService.league_brief(getattr(match, "league", None))
        return item

    @staticmethod
    def get_head_to_head(db: Session, home_team_id: str, away_team_id: str, limit: int = 8):
        """两队历史交锋（完赛），按日期倒序。"""
        if not home_team_id or not away_team_id:
            return []
        rows = (
            db.query(Match)
            .filter(
                Match.status == "finished",
                or_(
                    and_(Match.home_team_id == home_team_id, Match.away_team_id == away_team_id),
                    and_(Match.home_team_id == away_team_id, Match.away_team_id == home_team_id),
                ),
            )
            .order_by(desc(Match.match_date), desc(Match.match_time))
            .limit(limit)
            .all()
        )
        out = []
        for m in rows:
            hg = int(m.home_goals or 0)
            ag = int(m.away_goals or 0)
            if hg > ag:
                result = "home"
            elif hg < ag:
                result = "away"
            else:
                result = "draw"
            out.append({
                "match_id": m.id,
                "date": m.match_date.isoformat() if m.match_date else None,
                "home_team_id": m.home_team_id,
                "away_team_id": m.away_team_id,
                "home_goals": hg,
                "away_goals": ag,
                "score": f"{hg}-{ag}",
                "result": result,
                "league_id": m.league_id,
            })
        return out

    @staticmethod
    def get_by_date(db: Session, match_date: date):
        return db.query(Match).join(League).filter(League.is_active == True, Match.match_date == match_date).order_by(Match.match_time).all()

    @staticmethod
    def get_by_league(db: Session, league_id: str):
        from sqlalchemy.orm import joinedload
        return db.query(Match).options(
            joinedload(Match.league),
            joinedload(Match.home_team),
            joinedload(Match.away_team)
        ).filter(Match.league_id == league_id).order_by(desc(Match.match_date)).all()

    @staticmethod
    def get_upcoming(db: Session, limit: int = 20):
        from sqlalchemy.orm import joinedload
        return db.query(Match).options(
            joinedload(Match.league),
            joinedload(Match.home_team),
            joinedload(Match.away_team)
        ).join(League).filter(
            League.is_active == True,
            Match.status == 'upcoming',
            Match.match_date >= date.today(),
        ).order_by(Match.match_date, Match.match_time).limit(limit).all()

    @staticmethod
    def get_finished(db: Session, limit: int = 50):
        from sqlalchemy.orm import joinedload
        return db.query(Match).options(
            joinedload(Match.league),
            joinedload(Match.home_team),
            joinedload(Match.away_team)
        ).join(League).filter(League.is_active == True, Match.status == 'finished').order_by(desc(Match.match_date), desc(Match.match_time)).limit(limit).all()

    @staticmethod
    def _normalize_league_ids(league_id=None, league_ids=None):
        """解析联赛过滤：None=不过滤；[]=无匹配；[id,...]=IN 过滤。

        同时传入 league_id 与 league_ids 时，单选优先；若单选不在关注集合内则返回空。
        """
        allowed = None
        if league_ids is not None:
            if isinstance(league_ids, str):
                allowed = [part.strip() for part in league_ids.split(",") if part.strip()]
            else:
                allowed = [str(part).strip() for part in league_ids if part]
        if league_id:
            if allowed is not None and league_id not in allowed:
                return []
            return [league_id]
        return allowed

    @staticmethod
    def _apply_league_filter(query, league_id=None, league_ids=None):
        resolved = MatchService._normalize_league_ids(league_id, league_ids)
        if resolved is None:
            return query
        if not resolved:
            return query.filter(False)
        if len(resolved) == 1:
            return query.filter(Match.league_id == resolved[0])
        return query.filter(Match.league_id.in_(resolved))

    @staticmethod
    def _build_match_query(db: Session, status=None, league_id=None, keyword=None, match_date=None, date_from=None, league_ids=None):
        from sqlalchemy.orm import joinedload
        query = db.query(Match).options(
            joinedload(Match.league),
            joinedload(Match.home_team),
            joinedload(Match.away_team)
        ).join(League).filter(League.is_active == True)
        if status:
            query = query.filter(Match.status == status)
            if status == 'upcoming':
                query = query.filter(Match.match_date >= date.today())
        query = MatchService._apply_league_filter(query, league_id=league_id, league_ids=league_ids)
        if match_date:
            query = query.filter(Match.match_date == match_date)
        if date_from:
            query = query.filter(Match.match_date >= date_from)
        if keyword:
            from db.models import Team
            HomeTeam = aliased(Team)
            AwayTeam = aliased(Team)
            query = query.join(HomeTeam, Match.home_team_id == HomeTeam.id).join(
                AwayTeam, Match.away_team_id == AwayTeam.id
            ).filter(
                HomeTeam.name.contains(keyword)
                | AwayTeam.name.contains(keyword)
                | Match.id.contains(keyword)
            )
        return query

    @staticmethod
    def list_match_dates(db: Session, status=None, league_id=None, keyword=None, date_from=None, league_ids=None):
        """Distinct match dates for filter dropdown (ignores match_date filter)."""
        query = (
            db.query(Match.match_date)
            .join(League)
            .filter(League.is_active == True, Match.match_date.isnot(None))
        )
        if status:
            query = query.filter(Match.status == status)
            if status == 'upcoming':
                query = query.filter(Match.match_date >= date.today())
        query = MatchService._apply_league_filter(query, league_id=league_id, league_ids=league_ids)
        if date_from:
            query = query.filter(Match.match_date >= date_from)
        if keyword:
            from db.models import Team
            HomeTeam = aliased(Team)
            AwayTeam = aliased(Team)
            query = query.join(HomeTeam, Match.home_team_id == HomeTeam.id).join(
                AwayTeam, Match.away_team_id == AwayTeam.id
            ).filter(
                HomeTeam.name.contains(keyword)
                | AwayTeam.name.contains(keyword)
                | Match.id.contains(keyword)
            )
        order = Match.match_date.asc() if status == 'upcoming' else Match.match_date.desc()
        rows = query.distinct().order_by(order).all()
        return [r[0].isoformat() for r in rows if r[0]]

    @staticmethod
    def get_paginated_upcoming(db: Session, page=1, page_size=20, league_id=None, keyword=None, match_date=None, league_ids=None):
        query = MatchService._build_match_query(
            db, status='upcoming', league_id=league_id, keyword=keyword, match_date=match_date, league_ids=league_ids
        )
        query = query.order_by(Match.match_date, Match.match_time)
        offset = (page - 1) * page_size
        return query.offset(offset).limit(page_size).all()

    @staticmethod
    def get_paginated_finished(db: Session, page=1, page_size=20, league_id=None, keyword=None, match_date=None, date_from=None, league_ids=None):
        query = MatchService._build_match_query(
            db, status='finished', league_id=league_id, keyword=keyword, match_date=match_date, date_from=date_from, league_ids=league_ids
        )
        query = query.order_by(desc(Match.match_date), desc(Match.match_time))
        offset = (page - 1) * page_size
        return query.offset(offset).limit(page_size).all()

    @staticmethod
    def count_upcoming(db: Session, league_id=None, keyword=None, match_date=None, league_ids=None):
        query = MatchService._build_match_query(
            db, status='upcoming', league_id=league_id, keyword=keyword, match_date=match_date, league_ids=league_ids
        )
        return query.count()

    @staticmethod
    def count_finished(db: Session, league_id=None, keyword=None, match_date=None, date_from=None, league_ids=None):
        query = MatchService._build_match_query(
            db, status='finished', league_id=league_id, keyword=keyword, match_date=match_date, date_from=date_from, league_ids=league_ids
        )
        return query.count()

    @staticmethod
    def _build_jingcai_query(db: Session, league_id=None, keyword=None, match_date=None, status=None, league_ids=None):
        """竞彩胜平负/让球列表：已写入让球或竞彩 SP 的场次。"""
        from sqlalchemy import or_
        query = MatchService._build_match_query(
            db, status=status, league_id=league_id, keyword=keyword, match_date=match_date, league_ids=league_ids
        )
        query = query.filter(
            or_(
                Match.handicap.isnot(None),
                Match.odds_nspf_win.isnot(None),
                Match.odds_nspf_draw.isnot(None),
                Match.odds_nspf_lose.isnot(None),
                Match.odds_spf_win.isnot(None),
                Match.odds_spf_draw.isnot(None),
                Match.odds_spf_lose.isnot(None),
            )
        )
        return query

    @staticmethod
    def get_paginated_jingcai(
        db: Session, page=1, page_size=50, league_id=None, keyword=None, match_date=None, status=None, league_ids=None
    ):
        query = MatchService._build_jingcai_query(
            db, league_id=league_id, keyword=keyword, match_date=match_date, status=status, league_ids=league_ids
        )
        query = query.order_by(Match.match_date.asc(), Match.match_time.asc(), Match.id.asc())
        offset = (page - 1) * page_size
        return query.offset(offset).limit(page_size).all()

    @staticmethod
    def count_jingcai(db: Session, league_id=None, keyword=None, match_date=None, status=None, league_ids=None):
        return MatchService._build_jingcai_query(
            db, league_id=league_id, keyword=keyword, match_date=match_date, status=status, league_ids=league_ids
        ).count()

    @staticmethod
    def list_jingcai_dates(db: Session, league_id=None, keyword=None, status=None, league_ids=None):
        from sqlalchemy import or_
        query = (
            db.query(Match.match_date)
            .join(League)
            .filter(League.is_active == True, Match.match_date.isnot(None))
            .filter(
                or_(
                    Match.handicap.isnot(None),
                    Match.odds_nspf_win.isnot(None),
                    Match.odds_spf_win.isnot(None),
                )
            )
        )
        if status:
            query = query.filter(Match.status == status)
            if status == 'upcoming':
                query = query.filter(Match.match_date >= date.today())
        query = MatchService._apply_league_filter(query, league_id=league_id, league_ids=league_ids)
        if keyword:
            from db.models import Team
            HomeTeam = aliased(Team)
            AwayTeam = aliased(Team)
            query = query.join(HomeTeam, Match.home_team_id == HomeTeam.id).join(
                AwayTeam, Match.away_team_id == AwayTeam.id
            ).filter(
                HomeTeam.name.contains(keyword)
                | AwayTeam.name.contains(keyword)
                | Match.id.contains(keyword)
            )
        rows = query.distinct().order_by(Match.match_date.asc()).all()
        return [r[0].isoformat() for r in rows if r[0]]

    @staticmethod
    def _build_jingcai_bf_query(db: Session, league_id=None, keyword=None, match_date=None, status=None, league_ids=None):
        """竞彩比分列表：已写入 odds_bf_json 的场次。"""
        query = MatchService._build_match_query(
            db, status=status, league_id=league_id, keyword=keyword, match_date=match_date, league_ids=league_ids
        )
        query = query.filter(
            Match.odds_bf_json.isnot(None),
            Match.odds_bf_json != '',
            Match.odds_bf_json != '{}',
        )
        return query

    @staticmethod
    def get_paginated_jingcai_bf(
        db: Session, page=1, page_size=50, league_id=None, keyword=None, match_date=None, status=None, league_ids=None
    ):
        query = MatchService._build_jingcai_bf_query(
            db, league_id=league_id, keyword=keyword, match_date=match_date, status=status, league_ids=league_ids
        )
        query = query.order_by(Match.match_date.asc(), Match.match_time.asc(), Match.id.asc())
        offset = (page - 1) * page_size
        return query.offset(offset).limit(page_size).all()

    @staticmethod
    def count_jingcai_bf(db: Session, league_id=None, keyword=None, match_date=None, status=None, league_ids=None):
        return MatchService._build_jingcai_bf_query(
            db, league_id=league_id, keyword=keyword, match_date=match_date, status=status, league_ids=league_ids
        ).count()

    @staticmethod
    def list_jingcai_bf_dates(db: Session, league_id=None, keyword=None, status=None, league_ids=None):
        query = (
            db.query(Match.match_date)
            .join(League)
            .filter(League.is_active == True, Match.match_date.isnot(None))
            .filter(
                Match.odds_bf_json.isnot(None),
                Match.odds_bf_json != '',
                Match.odds_bf_json != '{}',
            )
        )
        if status:
            query = query.filter(Match.status == status)
            if status == 'upcoming':
                query = query.filter(Match.match_date >= date.today())
        query = MatchService._apply_league_filter(query, league_id=league_id, league_ids=league_ids)
        if keyword:
            from db.models import Team
            HomeTeam = aliased(Team)
            AwayTeam = aliased(Team)
            query = query.join(HomeTeam, Match.home_team_id == HomeTeam.id).join(
                AwayTeam, Match.away_team_id == AwayTeam.id
            ).filter(
                HomeTeam.name.contains(keyword)
                | AwayTeam.name.contains(keyword)
                | Match.id.contains(keyword)
            )
        rows = query.distinct().order_by(Match.match_date.asc()).all()
        return [r[0].isoformat() for r in rows if r[0]]

    @staticmethod
    def _build_jingcai_live_query(db: Session, league_id=None, keyword=None, match_date=None, status=None, league_ids=None):
        """竞彩比分列表：live.500.com/jczq.php 采集入库的场次（source=live_jingcai）。"""
        query = MatchService._build_match_query(
            db, status=status, league_id=league_id, keyword=keyword, match_date=match_date, league_ids=league_ids
        )
        query = query.filter(Match.source == 'live_jingcai')
        return query

    @staticmethod
    def get_paginated_jingcai_live(
        db: Session, page=1, page_size=50, league_id=None, keyword=None, match_date=None, status=None, league_ids=None
    ):
        query = MatchService._build_jingcai_live_query(
            db, league_id=league_id, keyword=keyword, match_date=match_date, status=status, league_ids=league_ids
        )
        query = query.order_by(Match.match_date.asc(), Match.match_time.asc(), Match.id.asc())
        offset = (page - 1) * page_size
        return query.offset(offset).limit(page_size).all()

    @staticmethod
    def count_jingcai_live(db: Session, league_id=None, keyword=None, match_date=None, status=None, league_ids=None):
        return MatchService._build_jingcai_live_query(
            db, league_id=league_id, keyword=keyword, match_date=match_date, status=status, league_ids=league_ids
        ).count()

    @staticmethod
    def list_jingcai_live_dates(db: Session, league_id=None, keyword=None, status=None, league_ids=None):
        query = (
            db.query(Match.match_date)
            .join(League)
            .filter(League.is_active == True, Match.match_date.isnot(None))
            .filter(Match.source == 'live_jingcai')
        )
        if status:
            query = query.filter(Match.status == status)
            if status == 'upcoming':
                query = query.filter(Match.match_date >= date.today())
        query = MatchService._apply_league_filter(query, league_id=league_id, league_ids=league_ids)
        if keyword:
            from db.models import Team
            HomeTeam = aliased(Team)
            AwayTeam = aliased(Team)
            query = query.join(HomeTeam, Match.home_team_id == HomeTeam.id).join(
                AwayTeam, Match.away_team_id == AwayTeam.id
            ).filter(
                HomeTeam.name.contains(keyword)
                | AwayTeam.name.contains(keyword)
                | Match.id.contains(keyword)
            )
        rows = query.distinct().order_by(Match.match_date.asc()).all()
        return [r[0].isoformat() for r in rows if r[0]]

    @staticmethod
    def _parse_odds_bf(raw):
        if not raw:
            return None
        if isinstance(raw, dict):
            return raw
        try:
            import json
            data = json.loads(raw)
            return data if isinstance(data, dict) and data else None
        except Exception:
            return None

    @staticmethod
    def _jingcai_odds_filter(query):
        from sqlalchemy import or_
        return query.filter(
            or_(
                Match.handicap.isnot(None),
                Match.odds_nspf_win.isnot(None),
                Match.odds_nspf_draw.isnot(None),
                Match.odds_nspf_lose.isnot(None),
                Match.odds_spf_win.isnot(None),
                Match.odds_spf_draw.isnot(None),
                Match.odds_spf_lose.isnot(None),
            )
        )

    @staticmethod
    def _build_jingcai_expired_query(
        db: Session, league_id=None, keyword=None, match_date=None, missing_score: bool = False, league_ids=None
    ):
        """过期竞彩场次：有赔率且已开赛（开赛时间已过，或状态为进行中/已完赛）。"""
        from sqlalchemy import or_, and_
        now = datetime.now()
        query = MatchService._build_match_query(
            db, status=None, league_id=league_id, keyword=keyword, match_date=match_date, league_ids=league_ids
        )
        query = MatchService._jingcai_odds_filter(query)
        query = query.filter(
            or_(
                Match.match_date < now.date(),
                and_(
                    Match.match_date == now.date(),
                    or_(
                        Match.status.in_(["live", "finished"]),
                        and_(
                            Match.match_time.isnot(None),
                            Match.match_time <= now.time(),
                        ),
                    ),
                ),
            )
        )
        if missing_score:
            query = query.filter(
                or_(
                    Match.status != "finished",
                    Match.result.is_(None),
                    and_(Match.home_goals.is_(None), Match.away_goals.is_(None)),
                )
            )
        return query

    @staticmethod
    def get_paginated_jingcai_expired(
        db: Session,
        page=1,
        page_size=50,
        league_id=None,
        keyword=None,
        match_date=None,
        missing_score: bool = False,
        league_ids=None,
    ):
        query = MatchService._build_jingcai_expired_query(
            db,
            league_id=league_id,
            keyword=keyword,
            match_date=match_date,
            missing_score=missing_score,
            league_ids=league_ids,
        )
        query = query.order_by(desc(Match.match_date), desc(Match.match_time), Match.id.asc())
        offset = (page - 1) * page_size
        return query.offset(offset).limit(page_size).all()

    @staticmethod
    def count_jingcai_expired(
        db: Session, league_id=None, keyword=None, match_date=None, missing_score: bool = False, league_ids=None
    ):
        return MatchService._build_jingcai_expired_query(
            db,
            league_id=league_id,
            keyword=keyword,
            match_date=match_date,
            missing_score=missing_score,
            league_ids=league_ids,
        ).count()

    @staticmethod
    def list_jingcai_expired_dates(db: Session, league_id=None, keyword=None, missing_score: bool = False, league_ids=None):
        query = MatchService._build_jingcai_expired_query(
            db, league_id=league_id, keyword=keyword, missing_score=missing_score, league_ids=league_ids
        )
        rows = (
            query.with_entities(Match.match_date)
            .filter(Match.match_date.isnot(None))
            .distinct()
            .order_by(desc(Match.match_date))
            .all()
        )
        return [r[0].isoformat() for r in rows if r[0]]

    @staticmethod
    def _build_jingcai_expired_bf_query(
        db: Session, league_id=None, keyword=None, match_date=None, missing_score: bool = False, league_ids=None
    ):
        """历史比分：已过开赛时间且已写入 odds_bf_json 的场次。"""
        from sqlalchemy import or_, and_
        now = datetime.now()
        query = MatchService._build_match_query(
            db, status=None, league_id=league_id, keyword=keyword, match_date=match_date, league_ids=league_ids
        )
        query = query.filter(
            Match.odds_bf_json.isnot(None),
            Match.odds_bf_json != '',
            Match.odds_bf_json != '{}',
        )
        query = query.filter(
            or_(
                Match.match_date < now.date(),
                and_(
                    Match.match_date == now.date(),
                    or_(
                        Match.status.in_(["live", "finished"]),
                        and_(
                            Match.match_time.isnot(None),
                            Match.match_time <= now.time(),
                        ),
                    ),
                ),
            )
        )
        if missing_score:
            query = query.filter(
                or_(
                    Match.status != "finished",
                    Match.result.is_(None),
                    and_(Match.home_goals.is_(None), Match.away_goals.is_(None)),
                )
            )
        return query

    @staticmethod
    def get_paginated_jingcai_expired_bf(
        db: Session,
        page=1,
        page_size=50,
        league_id=None,
        keyword=None,
        match_date=None,
        missing_score: bool = False,
        league_ids=None,
    ):
        query = MatchService._build_jingcai_expired_bf_query(
            db,
            league_id=league_id,
            keyword=keyword,
            match_date=match_date,
            missing_score=missing_score,
            league_ids=league_ids,
        )
        query = query.order_by(desc(Match.match_date), desc(Match.match_time), Match.id.asc())
        offset = (page - 1) * page_size
        return query.offset(offset).limit(page_size).all()

    @staticmethod
    def count_jingcai_expired_bf(
        db: Session, league_id=None, keyword=None, match_date=None, missing_score: bool = False, league_ids=None
    ):
        return MatchService._build_jingcai_expired_bf_query(
            db,
            league_id=league_id,
            keyword=keyword,
            match_date=match_date,
            missing_score=missing_score,
            league_ids=league_ids,
        ).count()

    @staticmethod
    def list_jingcai_expired_bf_dates(db: Session, league_id=None, keyword=None, missing_score: bool = False, league_ids=None):
        query = MatchService._build_jingcai_expired_bf_query(
            db, league_id=league_id, keyword=keyword, missing_score=missing_score, league_ids=league_ids
        )
        rows = (
            query.with_entities(Match.match_date)
            .filter(Match.match_date.isnot(None))
            .distinct()
            .order_by(desc(Match.match_date))
            .all()
        )
        return [r[0].isoformat() for r in rows if r[0]]

    @staticmethod
    def get_by_status(db: Session, status: str):
        return db.query(Match).join(League).filter(League.is_active == True, Match.status == status).order_by(desc(Match.match_date)).all()

    @staticmethod
    def create(db: Session, data: dict):
        match = Match(**data)
        db.add(match)
        db.commit()
        db.refresh(match)
        return match

    @staticmethod
    def update(db: Session, match_id: str, data: dict):
        """更新赛事基础信息（仅允许 Match 表存在的字段）。"""
        match = db.query(Match).filter(Match.id == match_id).first()
        if match:
            for key, value in data.items():
                if hasattr(match, key):
                    setattr(match, key, value)
            db.commit()
            db.refresh(match)
        return match

    @staticmethod
    def delete(db: Session, match_id: str):
        """删除赛事并级联清理关联数据（预测 / 球员统计 / 球队统计 / 风控 / 收藏 / 历史 / 赔率快照）。"""
        match = db.query(Match).filter(Match.id == match_id).first()
        if not match:
            return None
        db.query(MatchPrediction).filter(MatchPrediction.match_id == match_id).delete(synchronize_session=False)
        db.query(MatchPlayerStat).filter(MatchPlayerStat.match_id == match_id).delete(synchronize_session=False)
        db.query(MatchTeamStat).filter(MatchTeamStat.match_id == match_id).delete(synchronize_session=False)
        db.query(RiskAlert).filter(RiskAlert.match_id == match_id).delete(synchronize_session=False)
        db.query(OddsSnapshot).filter(OddsSnapshot.match_id == match_id).delete(synchronize_session=False)
        db.query(UserFavorite).filter(UserFavorite.match_id == match_id).delete(synchronize_session=False)
        db.query(UserHistory).filter(UserHistory.match_id == match_id).delete(synchronize_session=False)
        db.delete(match)
        db.commit()
        return match

    @staticmethod
    def update_result(db: Session, match_id: str, home_goals: int, away_goals: int):
        match = db.query(Match).filter(Match.id == match_id).first()
        if match:
            match.home_goals = home_goals
            match.away_goals = away_goals
            match.status = 'finished'
            if home_goals > away_goals:
                match.result = 'H'
            elif home_goals < away_goals:
                match.result = 'A'
            else:
                match.result = 'D'
            db.commit()
            db.refresh(match)
        return match

    @staticmethod
    def search(db: Session, keyword: str):
        return db.query(Match).filter(
            Match.id.contains(keyword) | Match.venue.contains(keyword)
        ).all()

    @staticmethod
    def _group_predictions_by_match(db: Session, match_ids: list):
        if not match_ids:
            return {}
        rows = (
            db.query(MatchPrediction)
            .filter(MatchPrediction.match_id.in_(match_ids))
            .order_by(asc(MatchPrediction.created_at))
            .all()
        )
        grouped = {}
        for pred in rows:
            grouped.setdefault(pred.match_id, []).append(pred)
        return grouped

    @staticmethod
    def _choose_prediction(match, plist: list, prefer: str = "latest"):
        if not plist:
            return None, False
        if prefer == "earliest":
            return plist[0], False
        if prefer == "pre_match":
            kickoff = datetime.combine(
                match.match_date or date.today(),
                match.match_time or dt_time.max,
            )
            before = [p for p in plist if p.created_at and p.created_at <= kickoff]
            if before:
                return before[-1], False
            return plist[0], True
        return plist[-1], False

    @staticmethod
    def _match_time_str(match) -> str | None:
        if not match.match_time:
            return None
        if isinstance(match.match_time, str):
            return match.match_time[:5] if len(match.match_time) >= 5 else match.match_time
        return match.match_time.strftime("%H:%M")

    @staticmethod
    def serialize_with_predictions(db: Session, matches: list, prefer: str = "latest"):
        """把赛事转成可 JSON 的字典，并挂上预测。

        prefer:
          latest    最新一条（未来赛事）
          earliest  最早一条
          pre_match 开赛前最后一条；没有则用最早一条并标记 after_match
        """
        if not matches:
            return []
        ids = [m.id for m in matches]
        grouped = MatchService._group_predictions_by_match(db, ids)
        out = []
        for match in matches:
            item = jsonable_encoder({c.name: getattr(match, c.name) for c in match.__table__.columns})
            item["odds_bf"] = MatchService._parse_odds_bf(item.pop("odds_bf_json", None) or getattr(match, "odds_bf_json", None))
            plist = grouped.get(match.id) or []
            chosen, after_match = MatchService._choose_prediction(match, plist, prefer)
            if chosen:
                item["prediction"] = PredictionService.to_api_dict(chosen)
                item["prediction_after_match"] = after_match
            else:
                item["prediction"] = None
                item["prediction_after_match"] = False
            MatchService.attach_relation_briefs(item, match)
            from services.odds_analysis import attach_odds_analysis
            attach_odds_analysis(item, match=match, prediction=chosen, compact=False)
            out.append(item)
        return out

    @staticmethod
    def serialize_summary(db: Session, matches: list, prefer: str = "latest"):
        """列表紧凑模式：仅返回卡片所需字段，省略 meta / 矩阵等大 payload。"""
        if not matches:
            return []
        ids = [m.id for m in matches]
        grouped = MatchService._group_predictions_by_match(db, ids)
        out = []
        for match in matches:
            item = {
                "id": match.id,
                "league_id": match.league_id,
                "home_team_id": match.home_team_id,
                "away_team_id": match.away_team_id,
                "match_date": match.match_date.isoformat() if match.match_date else None,
                "match_time": MatchService._match_time_str(match),
                "status": match.status,
                "stage": match.stage,
                "round_name": match.round_name,
                "home_goals": match.home_goals,
                "away_goals": match.away_goals,
                "result": match.result,
                "handicap": match.handicap,
                "handicap_line": match.handicap_line,
                "fixture_id": match.fixture_id,
                "is_single": bool(match.is_single) if match.is_single is not None else False,
                "half_score": match.half_score,
                "match_no": match.match_no,
                "source": match.source,
                "buy_end_time": match.buy_end_time,
                "odds_nspf_win": float(match.odds_nspf_win) if match.odds_nspf_win is not None else None,
                "odds_nspf_draw": float(match.odds_nspf_draw) if match.odds_nspf_draw is not None else None,
                "odds_nspf_lose": float(match.odds_nspf_lose) if match.odds_nspf_lose is not None else None,
                "odds_spf_win": float(match.odds_spf_win) if match.odds_spf_win is not None else None,
                "odds_spf_draw": float(match.odds_spf_draw) if match.odds_spf_draw is not None else None,
                "odds_spf_lose": float(match.odds_spf_lose) if match.odds_spf_lose is not None else None,
                "odds_bf": MatchService._parse_odds_bf(getattr(match, "odds_bf_json", None)),
            }
            plist = grouped.get(match.id) or []
            chosen, after_match = MatchService._choose_prediction(match, plist, prefer)
            if chosen:
                meta = PredictionService.meta_dict(chosen)
                item["prediction"] = {
                    "main_score": chosen.main_score,
                    "tendency": chosen.tendency,
                    "confidence": chosen.confidence,
                    "risk_level": chosen.risk_level,
                    "home_win_prob": float(chosen.home_win_prob) if chosen.home_win_prob is not None else None,
                    "draw_prob": float(chosen.draw_prob) if chosen.draw_prob is not None else None,
                    "away_win_prob": float(chosen.away_win_prob) if chosen.away_win_prob is not None else None,
                    "total_goals": chosen.total_goals,
                    "weight_source": meta.get("weight_source"),
                    "xg_coverage": meta.get("xg_coverage"),
                    "model_version": chosen.model_version,
                    "primary_scenario": meta.get("primary_scenario"),
                    "scenario_locked": meta.get("scenario_locked"),
                    "scenario_reason": meta.get("scenario_reason"),
                }
                item["prediction_after_match"] = after_match
            else:
                item["prediction"] = None
                item["prediction_after_match"] = False
            MatchService.attach_relation_briefs(item, match)
            from services.odds_analysis import attach_odds_analysis
            attach_odds_analysis(item, match=match, prediction=chosen, compact=True)
            out.append(item)
        return out
