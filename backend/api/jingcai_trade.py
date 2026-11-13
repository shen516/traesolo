"""竞彩足球全玩法数据 API（只读，无投注功能）。

仅供学习研究与数据分析；任何接口/文案不构成投注建议。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import User
from api.deps import get_current_user, require_permissions
from services import jingcai_trade_service as svc

router = APIRouter()

# 玩法 key → 允许值
PLAY_KEYS = ("dg", "spf", "hhgg", "bf", "jqs", "bqc")
# 可用于选号的玩法 key（dg/hhgg 是视图，不落库）
SELECT_PLAY_KEYS = ("spf", "nspf", "bf", "jqs", "bqc")


class SelectionIn(BaseModel):
    """单个选号。"""

    process_id: str = Field(..., description="500 场次 process_id")
    process_date: str = Field(..., description="销售日 YYYY-MM-DD")
    play: str = Field(..., description="玩法: spf/nspf/bf/jqs/bqc")
    option: str = Field(..., description="选项值，如 3/1/0、1:0、0..7、3-3")


class CalculateIn(BaseModel):
    """奖金计算入参。"""

    selections: List[SelectionIn] = Field(default_factory=list, max_length=200)
    pass_types: Optional[List[str]] = Field(
        default=None,
        description='过关方式: ["single"] 单关；["3x1"] 3串1；["2x1","3x1"] 组合',
    )
    times: int = Field(1, ge=1, le=999, description="倍数")
    single_amount: float = Field(2.0, ge=1, le=1000, description="单注金额（元）")


@router.get("/matches", dependencies=[Depends(require_permissions("jingcai:config", "jingcai:manage", "match:jingcai_bf"))])
async def jingcai_matches(
    play: str = Query("dg", description="玩法: dg/spf/hhgg/bf/jqs/bqc"),
    process_date: Optional[str] = Query(None, description="销售日 YYYY-MM-DD"),
    league_name: Optional[str] = Query(None),
    only_single: bool = Query(False, description="只看可单关"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if play not in PLAY_KEYS:
        raise HTTPException(status_code=400, detail=f"无效玩法: {play}")

    rows = svc.query_matches(
        db,
        play=play,
        process_date=process_date,
        league_name=league_name,
        only_single=only_single,
    )
    return {
        "play": play,
        "count": len(rows),
        "matches": rows,
        "option_order": svc.option_order(play if play in ("spf", "bf", "jqs", "bqc") else "spf"),
        "dates": svc.list_dates(db),
    }


@router.get("/dates", dependencies=[Depends(require_permissions("jingcai:config", "jingcai:manage", "match:jingcai_bf"))])
async def jingcai_dates(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return {"dates": svc.list_dates(db)}


@router.get("/pass-types", dependencies=[Depends(require_permissions("jingcai:config", "jingcai:manage", "match:jingcai_bf"))])
async def jingcai_pass_types(current: User = Depends(get_current_user)):
    """返回支持的过关方式（按场次数分组），供前端下拉使用。"""
    ordered = list(svc.PASS_STRUCT.keys())
    return {"pass_types": ordered, "single": True, "note": svc.BET_NOTE}


@router.post("/calculate", dependencies=[Depends(require_permissions("jingcai:config", "jingcai:manage", "match:jingcai_bf"))])
async def jingcai_calculate(
    payload: CalculateIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """根据选号计算注数 / 总金额 / 预计奖金区间 / 明细（只读计算，不产生任何投注）。"""
    bad = [s.play for s in payload.selections if s.play not in SELECT_PLAY_KEYS]
    if bad:
        raise HTTPException(status_code=400, detail=f"无效玩法: {','.join(set(bad))}")
    result = svc.calculate_bet(
        db,
        selections=[s.model_dump() for s in payload.selections],
        pass_types=payload.pass_types,
        times=payload.times,
        single_amount=payload.single_amount,
    )
    return result


@router.post("/refresh", dependencies=[Depends(require_permissions("jingcai:manage", "schedule:manage"))])
async def jingcai_refresh(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """手动触发一次全玩法采集（管理用）。"""
    from services.jingcai_trade_crawler import JingcaiTradeCrawler

    crawler = JingcaiTradeCrawler()
    rows = crawler.crawl(days_ahead=7)
    stats = svc.upsert_crawl_result(db, rows)
    return {"message": "竞彩全玩法刷新完成", "stats": stats}


@router.post("/history", dependencies=[Depends(require_permissions("jingcai:manage", "schedule:manage"))])
async def jingcai_history(
    days_back: int = Query(30, ge=1, le=60, description="向后回补天数"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """历史数据回补：抓取近 days_back 个销售日的全玩法 SP 与赛果并回填。

    仅供分析对照，不构成投注建议。
    """
    from services.crawler_service import CrawlerService

    svc2 = CrawlerService()
    result = svc2.crawl_jingcai_trade_history(days_back=days_back, crawl_type="manual")
    return result


@router.post("/verify", dependencies=[Depends(require_permissions("jingcai:manage", "schedule:manage"))])
async def jingcai_verify(
    days_back: int = Query(30, ge=1, le=60, description="向后对照天数"),
    current: User = Depends(get_current_user),
):
    """赛果校验：对比 jingcai_match_odds 与开奖数据，返回一致性统计。

    只读校验，不改写 DB；仅供分析对照，不构成投注建议。
    """
    from services.crawler_service import CrawlerService

    svc2 = CrawlerService()
    result = svc2.crawl_jingcai_trade_verify(days_back=days_back, crawl_type="manual")
    return result


@router.get("/sp-changes", dependencies=[Depends(require_permissions("jingcai:config", "jingcai:manage", "match:jingcai_bf"))])
async def jingcai_sp_changes(
    play: Optional[str] = Query(None, description="玩法过滤: spf/nspf/bf/jqs/bqc"),
    only_alert: bool = Query(False, description="只看告警"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """最近 SP 异动记录（仅供分析，不构成投注建议）。"""
    if play and play not in SELECT_PLAY_KEYS:
        raise HTTPException(status_code=400, detail=f"无效玩法: {play}")
    changes = svc.query_sp_changes(db, play=play, only_alert=only_alert, limit=limit)
    return {"changes": changes, "count": len(changes), "threshold": svc.SP_ALERT_THRESHOLD, "note": svc.BET_NOTE}


@router.get("/export", dependencies=[Depends(require_permissions("jingcai:config", "jingcai:manage", "match:jingcai_bf"))])
async def jingcai_export(
    process_date: Optional[str] = Query(None, description="销售日 YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """导出全玩法数据为 CSV（仅供分析，不构成投注建议）。"""
    import csv
    import io

    rows = svc.export_matches(db, process_date=process_date)
    buf = io.StringIO()
    writer = csv.writer(buf)
    header = [label for _, label in svc.EXPORT_COLUMNS]
    writer.writerow(header)
    for r in rows:
        writer.writerow([r.get(key, "") for key, _ in svc.EXPORT_COLUMNS])
    csv_text = "\ufeff" + buf.getvalue()  # BOM for Excel UTF-8
    filename = f"jingcai_trade_{process_date or 'latest'}.csv"
    from fastapi.responses import Response

    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/summary", dependencies=[Depends(require_permissions("jingcai:config", "jingcai:manage", "match:jingcai_bf"))])
async def jingcai_summary(
    process_date: Optional[str] = Query(None, description="销售日 YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """按销售日/玩法汇总统计报表（仅供分析，不构成投注建议）。"""
    return svc.summarize_matches(db, process_date=process_date)
