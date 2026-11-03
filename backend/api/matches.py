"""赛事API"""
from typing import Literal, Optional, Set
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from db.database import get_db
from services import MatchService, PredictionService, MatchPlayerStatService, PlayerService
from services.crawler_service import CrawlerService
from services.subscription_service import (
    FEATURE_HISTORY_DEEP,
    mask_match_list,
    mask_prediction,
    mask_prediction_list,
    mask_odds_bf,
    mask_risk_alerts,
    mask_score_top3_list,
)
from pydantic import BaseModel
from datetime import date, timedelta
import json
from api.authz import (
    RequireMatchRead, RequireMatchWrite, RequireScheduleManage, RequirePredictionCalc,
    RequireModelManage, RequireJingcaiConfig,
)
from api.deps import get_current_entitlements, require_feature

router = APIRouter()


def _parse_league_ids(raw: Optional[str]):
    """league_ids 查询参数：None=不过滤；空串=无匹配；逗号分隔=IN。"""
    if raw is None:
        return None
    return [part.strip() for part in raw.split(",") if part.strip()]


class MatchCreate(BaseModel):
    id: str
    league_id: Optional[str] = None
    home_team_id: str
    away_team_id: str
    match_date: date
    match_time: Optional[str] = None
    venue: Optional[str] = None
    weather: Optional[str] = None
    temperature: Optional[str] = None
    pitch_condition: Optional[str] = None
    status: str = "upcoming"
    stage: str = "league"
    group: Optional[str] = None
    round: Optional[str] = None


class MatchUpdate(BaseModel):
    league_id: Optional[str] = None
    match_date: Optional[date] = None
    match_time: Optional[str] = None
    venue: Optional[str] = None
    weather: Optional[str] = None
    temperature: Optional[str] = None
    pitch_condition: Optional[str] = None
    status: Optional[str] = None
    stage: Optional[str] = None
    group: Optional[str] = None
    round: Optional[str] = None


class MatchResult(BaseModel):
    home_goals: int
    away_goals: int


class JingcaiConfigUpdate(BaseModel):
    recommend_score_count: int


@router.get("/", dependencies=[RequireMatchRead])
async def get_matches(db: Session = Depends(get_db)):
    return {"matches": MatchService.get_all(db)}


@router.get("/upcoming", dependencies=[RequireMatchRead])
async def get_upcoming_matches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    league_id: str = Query(None),
    league_ids: str = Query(None, description="逗号分隔的联赛ID，空串表示无匹配"),
    keyword: str = Query(None),
    match_date: date = Query(None, description="按比赛日期筛选 YYYY-MM-DD"),
    view: Literal["full", "summary"] = Query("full", description="full=完整预测字段；summary=列表紧凑模式"),
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    ids = _parse_league_ids(league_ids)
    matches = MatchService.get_paginated_upcoming(
        db, page, page_size, league_id, keyword, match_date=match_date, league_ids=ids
    )
    total = MatchService.count_upcoming(db, league_id, keyword, match_date=match_date, league_ids=ids)
    available_dates = MatchService.list_match_dates(
        db, status='upcoming', league_id=league_id, keyword=keyword, league_ids=ids
    )
    serialize = MatchService.serialize_summary if view == "summary" else MatchService.serialize_with_predictions
    return {
        "matches": mask_match_list(serialize(db, matches), entitlements),
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size if page_size else 0
        },
        "available_dates": available_dates,
        "view": view,
    }


@router.get("/finished", dependencies=[RequireMatchRead])
async def get_finished_matches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    league_id: str = Query(None),
    league_ids: str = Query(None, description="逗号分隔的联赛ID，空串表示无匹配"),
    keyword: str = Query(None),
    match_date: date = Query(None, description="按比赛日期筛选 YYYY-MM-DD"),
    view: Literal["full", "summary"] = Query("full", description="full=完整预测字段；summary=列表紧凑模式"),
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    # 查询级门控：无 history:deep 权益仅可看近 7 天历史赛事
    date_from = None
    history_limited = False
    if FEATURE_HISTORY_DEEP not in entitlements:
        date_from = date.today() - timedelta(days=7)
        history_limited = True
        if match_date and match_date < date_from:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "FEATURE_LOCKED",
                    "feature": FEATURE_HISTORY_DEEP,
                    "message": "免费版仅支持查看近 7 天历史赛事，升级专业版解锁全部历史",
                },
            )
    ids = _parse_league_ids(league_ids)
    matches = MatchService.get_paginated_finished(
        db, page, page_size, league_id, keyword, match_date=match_date, date_from=date_from, league_ids=ids
    )
    total = MatchService.count_finished(db, league_id, keyword, match_date=match_date, date_from=date_from, league_ids=ids)
    available_dates = MatchService.list_match_dates(
        db, status='finished', league_id=league_id, keyword=keyword, date_from=date_from, league_ids=ids
    )
    serialize = MatchService.serialize_summary if view == "summary" else MatchService.serialize_with_predictions
    return {
        "matches": mask_match_list(serialize(db, matches, prefer="pre_match"), entitlements),
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size if page_size else 0
        },
        "available_dates": available_dates,
        "view": view,
        "history_limited": history_limited,
    }


@router.get("/jingcai", dependencies=[RequireMatchRead])
async def get_jingcai_matches(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    league_id: str = Query(None),
    league_ids: str = Query(None, description="逗号分隔的联赛ID，空串表示无匹配"),
    keyword: str = Query(None),
    match_date: date = Query(None, description="按比赛日期筛选 YYYY-MM-DD"),
    status: str = Query(None, description="upcoming|finished|live，空=全部"),
    view: Literal["full", "summary"] = Query("summary", description="列表默认 summary"),
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    """竞彩胜平负/让球列表（trade.500.com/jczq 采集入库的场次）。"""
    if status and status not in ("upcoming", "finished", "live"):
        raise HTTPException(status_code=400, detail="status 仅支持 upcoming/finished/live")
    ids = _parse_league_ids(league_ids)
    matches = MatchService.get_paginated_jingcai(
        db, page, page_size, league_id, keyword, match_date=match_date, status=status, league_ids=ids
    )
    total = MatchService.count_jingcai(
        db, league_id, keyword, match_date=match_date, status=status, league_ids=ids
    )
    available_dates = MatchService.list_jingcai_dates(
        db, league_id=league_id, keyword=keyword, status=status, league_ids=ids
    )
    serialize = MatchService.serialize_summary if view == "summary" else MatchService.serialize_with_predictions
    prefer = "pre_match" if status == "finished" else "latest"
    return {
        "matches": mask_match_list(serialize(db, matches, prefer=prefer), entitlements),
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size if page_size else 0,
        },
        "available_dates": available_dates,
        "view": view,
        "disclaimer": "仅供分析，不构成投注建议",
    }


@router.post("/jingcai/refresh", dependencies=[RequireScheduleManage])
async def refresh_jingcai_matches(
    days_ahead: int = Query(7, ge=1, le=14, description="向前采集天数"),
):
    """立即从 trade.500.com/jczq 刷新胜平负/让球赔率。"""
    crawler = CrawlerService()
    return crawler.crawl_jingcai_odds(days_ahead=days_ahead, crawl_type="manual")


@router.get("/jingcai/bf", dependencies=[RequireMatchRead])
async def get_jingcai_bf_matches(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    league_id: str = Query(None),
    league_ids: str = Query(None, description="逗号分隔的联赛ID，空串表示无匹配"),
    keyword: str = Query(None),
    match_date: date = Query(None, description="按比赛日期筛选 YYYY-MM-DD"),
    status: str = Query(None, description="upcoming|finished|live，空=全部"),
    view: Literal["full", "summary"] = Query("summary", description="列表默认 summary"),
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    """竞彩比分页列表（trade.500.com/jczq?playid=271 投注区 SP）。"""
    if status and status not in ("upcoming", "finished", "live"):
        raise HTTPException(status_code=400, detail="status 仅支持 upcoming/finished/live")
    ids = _parse_league_ids(league_ids)
    matches = MatchService.get_paginated_jingcai_bf(
        db, page, page_size, league_id, keyword, match_date=match_date, status=status, league_ids=ids
    )
    total = MatchService.count_jingcai_bf(
        db, league_id, keyword, match_date=match_date, status=status, league_ids=ids
    )
    available_dates = MatchService.list_jingcai_bf_dates(
        db, league_id=league_id, keyword=keyword, status=status, league_ids=ids
    )
    serialize = MatchService.serialize_summary if view == "summary" else MatchService.serialize_with_predictions
    prefer = "pre_match" if status == "finished" else "latest"
    return {
        "matches": mask_match_list(serialize(db, matches, prefer=prefer), entitlements),
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size if page_size else 0,
        },
        "available_dates": available_dates,
        "view": view,
        "disclaimer": "仅供分析，不构成投注建议",
    }


@router.post("/jingcai/bf/refresh", dependencies=[RequireScheduleManage])
async def refresh_jingcai_bf_matches(
    days_ahead: int = Query(7, ge=1, le=14, description="向前采集天数"),
    days_back: int = Query(0, ge=0, le=90, description="向后回补历史天数（竞彩分析历史比分）"),
):
    """立即从 trade.500.com/jczq 比分页刷新投注区 SP（可选历史回补）。"""
    crawler = CrawlerService()
    return crawler.crawl_jingcai_bf_odds(
        days_ahead=days_ahead, days_back=days_back, crawl_type="manual"
    )


@router.get("/jingcai/live", dependencies=[RequireMatchRead])
async def get_jingcai_live_matches(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    league_id: str = Query(None),
    league_ids: str = Query(None, description="逗号分隔的联赛ID，空串表示无匹配"),
    keyword: str = Query(None),
    match_date: date = Query(None, description="按比赛日期筛选 YYYY-MM-DD"),
    status: str = Query(None, description="upcoming|finished|live，空=全部"),
    view: Literal["full", "summary"] = Query("summary", description="列表默认 summary"),
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    """竞彩比分列表（live.500.com/jczq.php 采集入库的场次）。"""
    if status and status not in ("upcoming", "finished", "live"):
        raise HTTPException(status_code=400, detail="status 仅支持 upcoming/finished/live")
    ids = _parse_league_ids(league_ids)
    matches = MatchService.get_paginated_jingcai_live(
        db, page, page_size, league_id, keyword, match_date=match_date, status=status, league_ids=ids
    )
    total = MatchService.count_jingcai_live(
        db, league_id, keyword, match_date=match_date, status=status, league_ids=ids
    )
    available_dates = MatchService.list_jingcai_live_dates(
        db, league_id=league_id, keyword=keyword, status=status, league_ids=ids
    )
    serialize = MatchService.serialize_summary if view == "summary" else MatchService.serialize_with_predictions
    prefer = "pre_match" if status == "finished" else "latest"
    return {
        "matches": mask_match_list(serialize(db, matches, prefer=prefer), entitlements),
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size if page_size else 0,
        },
        "available_dates": available_dates,
        "view": view,
        "disclaimer": "仅供分析，不构成投注建议",
    }


@router.post("/jingcai/live/refresh", dependencies=[RequireScheduleManage])
async def refresh_jingcai_live_matches(
    days_ahead: int = Query(1, ge=1, le=7, description="向前采集天数"),
):
    """立即从 live.500.com/jczq.php 刷新竞彩比分列表。"""
    crawler = CrawlerService()
    return crawler.crawl_live_jingcai(days_ahead=days_ahead, crawl_type="manual")


@router.get("/jingcai/expired", dependencies=[RequireMatchRead])
async def get_jingcai_expired_matches(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    league_id: str = Query(None),
    league_ids: str = Query(None, description="逗号分隔的联赛ID，空串表示无匹配"),
    keyword: str = Query(None),
    match_date: date = Query(None, description="按比赛日期筛选 YYYY-MM-DD"),
    missing_score: bool = Query(False, description="仅看缺比分/未完赛回写"),
    view: Literal["full", "summary"] = Query("summary"),
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    """过期竞彩胜平负列表（已过开赛时间），用于赛果回写与核对。"""
    ids = _parse_league_ids(league_ids)
    matches = MatchService.get_paginated_jingcai_expired(
        db,
        page,
        page_size,
        league_id,
        keyword,
        match_date=match_date,
        missing_score=missing_score,
        league_ids=ids,
    )
    total = MatchService.count_jingcai_expired(
        db, league_id, keyword, match_date=match_date, missing_score=missing_score, league_ids=ids
    )
    available_dates = MatchService.list_jingcai_expired_dates(
        db, league_id=league_id, keyword=keyword, missing_score=missing_score, league_ids=ids
    )
    serialize = MatchService.serialize_summary if view == "summary" else MatchService.serialize_with_predictions
    return {
        "matches": mask_match_list(serialize(db, matches, prefer="pre_match"), entitlements),
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size if page_size else 0,
        },
        "available_dates": available_dates,
        "view": view,
        "missing_score_total": MatchService.count_jingcai_expired(
            db, league_id, keyword, match_date=match_date, missing_score=True
        ),
        "disclaimer": "仅供分析，不构成投注建议",
    }


@router.get("/jingcai/bf/expired", dependencies=[RequireMatchRead])
async def get_jingcai_expired_bf_matches(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    league_id: str = Query(None),
    league_ids: str = Query(None, description="逗号分隔的联赛ID，空串表示无匹配"),
    keyword: str = Query(None),
    match_date: date = Query(None, description="按比赛日期筛选 YYYY-MM-DD"),
    missing_score: bool = Query(False, description="仅看缺比分/未完赛回写"),
    view: Literal["full", "summary"] = Query("summary"),
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    """历史竞彩比分列表（已过开赛时间且有比分投注区 SP），用于赛果核对。"""
    ids = _parse_league_ids(league_ids)
    matches = MatchService.get_paginated_jingcai_expired_bf(
        db,
        page,
        page_size,
        league_id,
        keyword,
        match_date=match_date,
        missing_score=missing_score,
        league_ids=ids,
    )
    total = MatchService.count_jingcai_expired_bf(
        db, league_id, keyword, match_date=match_date, missing_score=missing_score, league_ids=ids
    )
    available_dates = MatchService.list_jingcai_expired_bf_dates(
        db, league_id=league_id, keyword=keyword, missing_score=missing_score, league_ids=ids
    )
    serialize = MatchService.serialize_summary if view == "summary" else MatchService.serialize_with_predictions
    return {
        "matches": mask_match_list(serialize(db, matches, prefer="pre_match"), entitlements),
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size if page_size else 0,
        },
        "available_dates": available_dates,
        "view": view,
        "missing_score_total": MatchService.count_jingcai_expired_bf(
            db, league_id, keyword, match_date=match_date, missing_score=True, league_ids=ids
        ),
        "disclaimer": "仅供分析，不构成投注建议",
    }


@router.get("/jingcai/bf/monthly-summary", dependencies=[RequireMatchRead])
async def get_jingcai_bf_monthly_summary(
    league_id: str = Query(None),
    league_ids: str = Query(None, description="逗号分隔的联赛ID，空串表示无匹配"),
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    """历史比分自然月汇总：上月完整月，以及本月已过开赛场次。仅供分析。"""
    from services.jingcai_bf_summary import build_monthly_summary_from_db

    return build_monthly_summary_from_db(
        db,
        league_id=league_id,
        league_ids=_parse_league_ids(league_ids),
        entitlements=entitlements,
    )


@router.post("/jingcai/expired/refresh-scores", dependencies=[RequireScheduleManage])
async def refresh_jingcai_expired_scores(
    days_back: int = Query(7, ge=1, le=30, description="回查最近 N 天赛果"),
    match_date: date = Query(None, description="只回写指定日期"),
):
    """从 trade.500.com/jczq 赛果回查页回写比分/状态。"""
    crawler = CrawlerService()
    return crawler.crawl_jingcai_scores(
        days_back=days_back, match_date=match_date, crawl_type="manual"
    )


@router.get("/jingcai/config", dependencies=[RequireJingcaiConfig])
async def get_jingcai_config(db: Session = Depends(get_db)):
    """竞彩足球配置：历史相似盘口比分推荐个数。"""
    from services.jingcai_score_top3 import (
        DEFAULT_RECOMMEND_COUNT,
        DISCLAIMER,
        RECOMMEND_COUNT_MAX,
        RECOMMEND_COUNT_MIN,
        load_recommend_count,
    )

    return {
        "recommend_score_count": load_recommend_count(db),
        "default": DEFAULT_RECOMMEND_COUNT,
        "min": RECOMMEND_COUNT_MIN,
        "max": RECOMMEND_COUNT_MAX,
        "disclaimer": DISCLAIMER,
    }


@router.put("/jingcai/config", dependencies=[RequireJingcaiConfig])
async def update_jingcai_config(body: JingcaiConfigUpdate, db: Session = Depends(get_db)):
    """保存推荐比分数量。只影响历史相似盘口比分推荐的返回个数。"""
    from services.jingcai_score_top3 import save_recommend_count

    try:
        n = save_recommend_count(db, body.recommend_score_count)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "已保存", "recommend_score_count": n}


@router.get("/jingcai/score-top3", dependencies=[RequireMatchRead])
async def get_jingcai_score_top3(
    match_ids: str = Query(..., description="逗号分隔的赛事ID"),
    nspf: str = Query("any", description="胜平负方向：any=不约束 / auto=看盘倾向 / model=模型倾向 / H / D / A"),
    spf: str = Query("any", description="让球方向：any=不约束 / auto=看盘倾向 / model=模型倾向 / H / D / A"),
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    """历史相似盘口比分分布 Top3（按需请求，仅供分析对照）。"""
    from services.jingcai_score_top3 import (
        DIRECTION_CHOICES, DISCLAIMER, get_config, load_recommend_count, recommend_for_matches,
    )

    ids = list(dict.fromkeys(part.strip() for part in match_ids.split(",") if part.strip()))
    if not ids:
        raise HTTPException(status_code=400, detail="match_ids 不能为空")
    max_batch = int(get_config()["max_batch"])
    if len(ids) > max_batch:
        raise HTTPException(status_code=400, detail=f"单次最多 {max_batch} 场")
    if nspf not in DIRECTION_CHOICES or spf not in DIRECTION_CHOICES:
        raise HTTPException(status_code=400, detail="方向参数仅支持 any / auto / model / H / D / A")
    items = recommend_for_matches(db, ids, nspf=nspf, spf=spf)
    return {
        "items": mask_score_top3_list(items, entitlements),
        "disclaimer": DISCLAIMER,
        "recommend_count": load_recommend_count(db),
    }


@router.get("/jingcai/score-top3/backtest", dependencies=[RequireModelManage])
async def get_jingcai_score_top3_backtest(
    days: int = Query(60, ge=7, le=365, description="回测最近 N 天完赛场次"),
    db: Session = Depends(get_db),
):
    """比分 Top3 滚动回测（每场只用其开赛前已完赛样本）。"""
    from services.jingcai_score_top3 import backtest

    return backtest(db, days=days)


@router.get("/date/{match_date}", dependencies=[RequireMatchRead])
async def get_matches_by_date(
    match_date: date,
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    matches = MatchService.get_by_date(db, match_date)
    return {"matches": mask_match_list(MatchService.serialize_with_predictions(db, matches), entitlements)}


@router.get("/league/{league_id}", dependencies=[RequireMatchRead])
async def get_matches_by_league(league_id: str, db: Session = Depends(get_db)):
    return {"matches": MatchService.get_by_league(db, league_id)}


@router.get("/status/{status}", dependencies=[RequireMatchRead])
async def get_matches_by_status(status: str, db: Session = Depends(get_db)):
    return {"matches": MatchService.get_by_status(db, status)}


@router.get("/search/{keyword}", dependencies=[RequireMatchRead])
async def search_matches(keyword: str, db: Session = Depends(get_db)):
    return {"matches": MatchService.search(db, keyword)}


@router.get("/{match_id}", dependencies=[RequireMatchRead])
async def get_match(
    match_id: str,
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    from fastapi.encoders import jsonable_encoder
    match = MatchService.get_by_id(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    # 仅序列化表字段，再挂嵌套精简关系（避免 relationship 全量展开）
    data = jsonable_encoder({c.name: getattr(match, c.name) for c in match.__table__.columns})
    MatchService.attach_relation_briefs(data, match)
    data["head_to_head"] = MatchService.get_head_to_head(
        db, match.home_team_id, match.away_team_id, limit=8
    )
    from services import RiskService
    alerts = RiskService.get_by_match(db, match_id) or []
    data["risk_alerts"] = mask_risk_alerts(jsonable_encoder(alerts), entitlements)
    # 竞彩比分 SP 门控
    odds_bf_raw = data.pop("odds_bf_json", None)
    masked_bf, bf_locked = mask_odds_bf(MatchService._parse_odds_bf(odds_bf_raw), entitlements)
    data["odds_bf"] = masked_bf
    if bf_locked:
        data["odds_bf_locked"] = True
    # 挂最新预测概率，便于赔率隐含概率对照
    latest_pred = None
    try:
        history = PredictionService.get_history_by_match(db, match_id, 1) or []
        latest_pred = history[0] if history else None
    except Exception:
        latest_pred = None
    from services.odds_analysis import attach_odds_analysis
    attach_odds_analysis(data, match=match, prediction=latest_pred, compact=False)
    return data


@router.post("/", dependencies=[RequireMatchWrite])
async def create_match(data: MatchCreate, db: Session = Depends(get_db)):
    return MatchService.create(db, data.model_dump())


@router.put("/{match_id}", dependencies=[RequireMatchWrite])
async def update_match(match_id: str, data: MatchUpdate, db: Session = Depends(get_db)):
    match = MatchService.update(db, match_id, data.model_dump(exclude_unset=True))
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    return match


@router.put("/{match_id}/result", dependencies=[RequireMatchWrite])
async def update_match_result(match_id: str, data: MatchResult, db: Session = Depends(get_db)):
    match = MatchService.update_result(db, match_id, data.home_goals, data.away_goals)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    return {"message": "Result updated", "home_goals": match.home_goals, "away_goals": match.away_goals}


@router.delete("/{match_id}", dependencies=[RequireMatchWrite])
async def delete_match(match_id: str, db: Session = Depends(get_db)):
    match = MatchService.delete(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    return {"message": "Match deleted"}


@router.get("/{match_id}/prediction", dependencies=[RequirePredictionCalc])
def get_match_prediction(
    match_id: str,
    recalculate: bool = Query(False, description="是否重新计算预测"),
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    """获取赛事预测（如无则实时计算并保存）"""
    match = MatchService.get_by_id(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    from services.prediction_runner import predict_for_match
    from services.metrics_service import record_prediction
    from services.odds_analysis import PredictionSkipped

    try:
        api = predict_for_match(db, match, recalculate=recalculate)
    except PredictionSkipped as e:
        raise HTTPException(status_code=400, detail=e.reason) from e
    if recalculate or not api.get("from_cache"):
        record_prediction("cache_miss" if not api.get("from_cache") else "cache_hit")
    return mask_prediction(api, entitlements)


@router.get("/{match_id}/prediction/history", dependencies=[RequireMatchRead])
async def get_match_prediction_history(
    match_id: str,
    limit: int = Query(10, description="返回记录数量"),
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    """获取赛事预测历史记录"""
    match = MatchService.get_by_id(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    history = PredictionService.get_history_by_match(db, match_id, limit)
    return {"history": mask_prediction_list(history, entitlements)}


@router.get("/{match_id}/odds-snapshots", dependencies=[RequireMatchRead, Depends(require_feature("odds:snapshot"))])
async def get_match_odds_snapshots(
    match_id: str,
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
    db: Session = Depends(get_db),
):
    """赔率时序快照（分析/展示用，非投注建议）。"""
    match = MatchService.get_by_id(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    from services.odds_snapshot_service import list_snapshots

    return {"match_id": match_id, "snapshots": list_snapshots(db, match_id, limit=limit)}


@router.get("/{match_id}/player-stats", dependencies=[RequireMatchRead])
async def get_match_player_stats(match_id: str, db: Session = Depends(get_db)):
    """获取赛事球员统计数据"""
    match = MatchService.get_by_id(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    stats = MatchPlayerStatService.get_by_match(db, match_id)
    enriched = []
    for s in stats:
        player = PlayerService.get_by_id(db, s.player_id)
        enriched.append({
            "id": s.id,
            "match_id": s.match_id,
            "player_id": s.player_id,
            "player_name": player.name if player else None,
            "jersey_number": player.jersey_number if player else None,
            "team_id": s.team_id,
            "is_home": s.is_home,
            "position": s.position,
            "goals": s.goals,
            "assists": s.assists,
            "shots": s.shots,
            "shots_on_target": s.shots_on_target,
            "passes": s.passes,
            "pass_accuracy": float(s.pass_accuracy) if s.pass_accuracy is not None else None,
            "tackles": s.tackles,
            "interceptions": s.interceptions,
            "clearances": s.clearances,
            "dribbles": s.dribbles,
            "dribble_success": s.dribble_success,
            "fouls_committed": s.fouls_committed,
            "fouls_suffered": s.fouls_suffered,
            "yellow_cards": s.yellow_cards,
            "red_cards": s.red_cards,
            "minutes_played": s.minutes_played,
            "rating": float(s.rating) if s.rating is not None else None,
        })
    return {"player_stats": enriched}


@router.post("/crawl/all", dependencies=[RequireScheduleManage])
async def crawl_all_matches(
    days_ahead: int = Query(7, description="采集未来多少天的赛事")
):
    """采集所有联赛的赛事数据"""
    crawler = CrawlerService()
    result = crawler.crawl_all_leagues(days_ahead)
    return result


@router.post("/crawl/historical", dependencies=[RequireScheduleManage])
async def crawl_historical_matches(
    league_id: str = Query(None, description="联赛ID，为空则采集五大联赛+欧冠"),
    days_back: int = Query(30, description="采集过去多少天的历史赛事"),
    seasons_back: int = Query(2, ge=0, le=5, description="回溯赛季数"),
    crawl_type: str = Query('manual', description="采集类型：manual/scheduled")
):
    """采集历史赛事数据"""
    crawler = CrawlerService()

    if league_id:
        result = crawler.crawl_historical_league(
            league_id, days_back, crawl_type, seasons_back=seasons_back
        )
    else:
        result = crawler.crawl_all_historical(
            days_back, crawl_type, seasons_back=seasons_back
        )

    return result


@router.post("/crawl/toggle-real", dependencies=[RequireScheduleManage])
async def toggle_real_crawler(enable: bool = Query(True, description="已废弃：仅真实爬虫")):
    """已移除模拟爬虫；始终使用真实源。"""
    if not enable:
        raise HTTPException(status_code=400, detail="模拟爬虫已移除，无法关闭真实采集")
    crawler = CrawlerService()
    crawler.use_real_crawler(True)
    return {"success": True, "message": "已使用真实爬虫（模拟模式已移除）"}
