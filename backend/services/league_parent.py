"""联赛父子关系推断 — 采集/回填/创建时统一使用。"""
from typing import Optional, List, Tuple

# 国家 → 规范顶级联赛 ID（与 init_db 种子一致，优先匹配）
COUNTRY_TOP_IDS = {
    "英格兰": "EPL",
    "西班牙": "LALIGA",
    "德国": "BUNDES",
    "意大利": "SERIEA",
    "法国": "LIGUE1",
    "韩国": "K1",
    "巴西": "BRA",
    "美国": "MLS",
    "瑞典": "SWE",
    "挪威": "NOR",
    "芬兰": "FIN",
}

# 国际/跨国家赛事：次级归属固定顶级
EXPLICIT_NAME_PARENT_IDS = [
    ("欧协联", "UCL"),
    ("欧联杯", "UCL"),
    ("欧联", "UCL"),
    ("欧冠", "UCL"),
    ("欧洲超级杯", "UCL"),
]

# 不应作为「国家顶级联赛」的名称特征（杯赛/青年/女足等）
_PARENT_SKIP_KEYWORDS = ("杯", "U1", "U2", "U17", "U19", "U21", "U23", "青年", "女足", "女超", "预备", "友谊")

_crawler = None
_name_parent_ids_cache: Optional[List[Tuple[str, str]]] = None


def _get_crawler():
    global _crawler
    if _crawler is None:
        from services.league_crawler import LeagueCrawler
        _crawler = LeagueCrawler()
    return _crawler


def _build_name_parent_ids() -> List[Tuple[str, str]]:
    """从 league_country_map 自动生成关键词 → 规范顶级 ID 映射。"""
    global _name_parent_ids_cache
    if _name_parent_ids_cache is not None:
        return _name_parent_ids_cache

    pairs: List[Tuple[str, str]] = list(EXPLICIT_NAME_PARENT_IDS)
    seen = {p[0] for p in pairs}

    for keyword, country in _get_crawler().league_country_map.items():
        if country in ("欧洲", "国际", "美洲", "非洲", "亚洲"):
            continue
        top_id = COUNTRY_TOP_IDS.get(country)
        if not top_id or keyword in seen:
            continue
        pairs.append((keyword, top_id))
        seen.add(keyword)

    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    _name_parent_ids_cache = pairs
    return pairs


def infer_country_from_name(name: str) -> Optional[str]:
    if not name:
        return None
    country = _get_crawler()._determine_country(name)
    if country in ("欧洲", "国际", "美洲", "非洲", "亚洲"):
        return None
    return country


def _parent_name_penalty(name: str) -> int:
    """数值越小越适合作为国家顶级父联赛。"""
    n = name or ""
    penalty = 0
    for kw in _PARENT_SKIP_KEYWORDS:
        if kw in n:
            penalty += 10
    if "乙" in n or "丙" in n or "2" in n or "3" in n:
        penalty += 20
    if "超" in n or "顶级" in n or "一级" in n or "甲级" in n:
        penalty -= 5
    return penalty


def _pick_db_parent(db, country: str, league_id: Optional[str]) -> Optional[str]:
    """在同国 level=1 联赛中选最合适的父级（优先有数据、名称像顶级联赛）。"""
    from db.models import League, Team, Match
    from sqlalchemy import func

    team_sub = (
        db.query(Team.league_id.label("lid"), func.count(Team.id).label("tc"))
        .group_by(Team.league_id).subquery()
    )
    match_sub = (
        db.query(Match.league_id.label("lid"), func.count(Match.id).label("mc"))
        .group_by(Match.league_id).subquery()
    )

    rows = (
        db.query(
            League,
            func.coalesce(team_sub.c.tc, 0).label("teams_count"),
            func.coalesce(match_sub.c.mc, 0).label("matches_count"),
        )
        .outerjoin(team_sub, League.id == team_sub.c.lid)
        .outerjoin(match_sub, League.id == match_sub.c.lid)
        .filter(
            League.country == country,
            League.level == 1,
            League.parent_id.is_(None),
        )
        .all()
    )
    if not rows:
        return None

    candidates = [
        (lg, int(tc or 0), int(mc or 0))
        for lg, tc, mc in rows
        if lg.id != league_id
    ]
    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (
            _parent_name_penalty(x[0].name),
            -(x[1] + x[2]),
            x[0].name or "",
        )
    )
    return candidates[0][0].id


def infer_parent_id(
    name: str,
    country: Optional[str],
    level: int,
    category: str = "international",
    league_id: Optional[str] = None,
) -> Optional[str]:
    """根据名称/国家/级别推断 parent_id；顶级或无法推断时返回 None。"""
    if level <= 1:
        return None

    league_name = (name or "").strip()
    if not country and league_name:
        country = infer_country_from_name(league_name)

    for keyword, parent_id in _build_name_parent_ids():
        if keyword in league_name:
            if league_id and parent_id == league_id:
                return None
            return parent_id

    if country and country in COUNTRY_TOP_IDS:
        parent_id = COUNTRY_TOP_IDS[country]
        if league_id and parent_id == league_id:
            return None
        return parent_id

    return None


def resolve_parent_id(
    db,
    name: str,
    country: Optional[str],
    level: int,
    category: str = "international",
    league_id: Optional[str] = None,
) -> Optional[str]:
    """推断 parent_id 并验证上级联赛存在于库中。"""
    from db.models import League

    if level <= 1:
        return None

    if not country and name:
        country = infer_country_from_name(name)

    candidate = infer_parent_id(name, country, level, category, league_id)
    if candidate and db.query(League.id).filter(League.id == candidate).first():
        return candidate

    if country:
        return _pick_db_parent(db, country, league_id)

    return None


def backfill_league_parents(db) -> int:
    """为已有联赛补齐 parent_id，返回更新条数。"""
    from db.models import League

    updated = 0
    leagues = db.query(League).order_by(League.level.asc()).all()
    for league in leagues:
        if league.level <= 1:
            if league.parent_id is not None:
                league.parent_id = None
                updated += 1
            continue
        country = league.country or infer_country_from_name(league.name)
        parent_id = resolve_parent_id(
            db, league.name, country, league.level,
            league.category or "international", league.id,
        )
        changed = False
        if parent_id and league.parent_id != parent_id:
            league.parent_id = parent_id
            changed = True
        if country and not league.country:
            league.country = country
            changed = True
        if changed:
            updated += 1
    if updated:
        db.commit()
    return updated
