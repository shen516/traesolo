"""预测API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from db.database import get_db
from services import PredictionService, MatchService, TeamService, ModelService
from services.subscription_service import mask_prediction, mask_prediction_list
from api.deps import get_current_entitlements
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Set
import json
import time
from api.authz import (
    RequireMatchRead, RequireMatchWrite, RequirePredictionCalc, RequirePredictionBatch,
)

router = APIRouter()

# 同步 def 会进线程池，事件循环不被蒙特卡洛占住。整批另设墙钟上限。
_BATCH_DEADLINE_SECONDS = 100
_RECALC_DEADLINE_SECONDS = 180


def _budget_exceeded(deadline: float) -> bool:
    return time.monotonic() >= deadline


from services.ensemble_registry import get_ensemble


class PredictionRequest(BaseModel):
    home_team: str
    away_team: str
    match_id: Optional[str] = None


class BatchPredictRequest(BaseModel):
    match_ids: List[str]
    recalculate: bool = False


class RecalculateRequest(BaseModel):
    """按新模型批量重算预测，补齐旧 meta_json / 版本滞后。"""
    scope: Literal["upcoming", "ids"] = "upcoming"
    match_ids: Optional[List[str]] = None
    only_stale: bool = True
    include_unpredicted: bool = True
    league_id: Optional[str] = None
    limit: int = Field(150, ge=1, le=300)


class PredictionCreate(BaseModel):
    match_id: str
    model_version: str = "v5.0.0"
    lambda_home: Optional[float] = None
    lambda_away: Optional[float] = None
    home_win_prob: Optional[float] = None
    draw_prob: Optional[float] = None
    away_win_prob: Optional[float] = None
    main_score: Optional[str] = None
    alt_scores: Optional[list] = None
    total_goals: Optional[str] = None
    tendency: Optional[str] = None
    confidence: Optional[str] = None
    risk_level: Optional[str] = None
    key_variables: Optional[list] = None
    analysis: Optional[str] = None
    score_matrix: Optional[list] = None


@router.get("/", dependencies=[RequireMatchRead])
async def get_predictions(
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    rows = PredictionService.get_all(db)
    return {"predictions": [mask_prediction(PredictionService.to_api_dict(p), entitlements) for p in rows]}


@router.get("/match/{match_id}", dependencies=[RequireMatchRead])
async def get_prediction_by_match(
    match_id: str,
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    prediction = PredictionService.get_by_match(db, match_id)
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return mask_prediction(PredictionService.to_api_dict(prediction), entitlements)


@router.post("/", dependencies=[RequireMatchWrite])
async def create_prediction(data: PredictionCreate, db: Session = Depends(get_db)):
    match = MatchService.get_by_id(db, data.match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    payload = data.model_dump()
    if isinstance(payload.get("alt_scores"), list):
        payload["alt_scores"] = json.dumps(payload["alt_scores"])
    if isinstance(payload.get("key_variables"), list):
        payload["key_variables"] = json.dumps(payload["key_variables"])
    if isinstance(payload.get("score_matrix"), list):
        payload["score_matrix"] = json.dumps(payload["score_matrix"])

    return PredictionService.create(db, payload)


@router.put("/match/{match_id}", dependencies=[RequireMatchWrite])
async def update_prediction(match_id: str, data: PredictionCreate, db: Session = Depends(get_db)):
    match = MatchService.get_by_id(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    payload = data.model_dump(exclude_unset=True)
    payload.pop("match_id", None)
    if isinstance(payload.get("alt_scores"), list):
        payload["alt_scores"] = json.dumps(payload["alt_scores"])
    if isinstance(payload.get("key_variables"), list):
        payload["key_variables"] = json.dumps(payload["key_variables"])
    if isinstance(payload.get("score_matrix"), list):
        payload["score_matrix"] = json.dumps(payload["score_matrix"])

    return PredictionService.create_or_update(db, match_id, payload, append_history=False)


@router.post("/calculate", dependencies=[RequirePredictionCalc])
def calculate_prediction(
    req: PredictionRequest,
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    home_team = TeamService.get_by_id(db, req.home_team)
    away_team = TeamService.get_by_id(db, req.away_team)

    if not home_team or not away_team:
        raise HTTPException(status_code=404, detail="Team not found")

    from services.prediction_runner import predict_teams
    from services.metrics_service import record_prediction
    from services.odds_analysis import PredictionSkipped

    try:
        out = predict_teams(
            db, req.home_team, req.away_team, match_id=req.match_id, save=bool(req.match_id)
        )
    except PredictionSkipped as e:
        raise HTTPException(status_code=400, detail=e.reason) from e
    record_prediction("api")
    return mask_prediction(out, entitlements)


def _current_model_version(db) -> str:
    try:
        current = ModelService.get_current(db)
        if current and current.version:
            return current.version
    except Exception:
        pass
    return "v5.0.3"


def _payload_from_result(result: dict, db=None) -> dict:
    meta = {
        "xg_home": result.get("xg_home"),
        "xg_away": result.get("xg_away"),
        "xg_coverage": result.get("xg_coverage"),
        "weights_used": result.get("weights_used"),
        "weight_source": result.get("weight_source"),
        "league_id": result.get("league_id"),
        "elo_home": result.get("elo_home"),
        "elo_away": result.get("elo_away"),
        "hyperparams_used": result.get("hyperparams_used"),
        "env_adjust": result.get("env_adjust"),
        "soft_priors": result.get("soft_priors"),
    }
    return {
        "model_version": _current_model_version(db) if db is not None else "v5.0.3",
        "lambda_home": result["lambda_home"],
        "lambda_away": result["lambda_away"],
        "home_win_prob": result["home_win_prob"],
        "draw_prob": result["draw_prob"],
        "away_win_prob": result["away_win_prob"],
        "main_score": result["main_score"],
        "alt_scores": result["alt_scores"],
        "total_goals": result["total_goals"],
        "tendency": result["tendency"],
        "confidence": result["confidence"],
        "risk_level": result["risk_level"],
        "key_variables": result["key_variables"],
        "analysis": result["analysis"],
        "score_matrix": result["score_matrix"],
        "meta_json": meta,
    }


def _prediction_is_stale(prediction, current_version: str) -> bool:
    """与 prediction_runner.prediction_is_stale 保持一致。"""
    from services.prediction_runner import prediction_is_stale
    return prediction_is_stale(prediction, current_version)


class ScenarioLockRequest(BaseModel):
    scenario_id: str = Field(..., description="ensemble|elo|poisson|xg|monte_carlo")
    lock: bool = Field(True, description="true=锁定为主结论；false=仅切换不锁定")


@router.post("/match/{match_id}/scenario", dependencies=[RequirePredictionCalc])
async def set_match_scenario(
    match_id: str,
    req: ScenarioLockRequest,
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    """切换/锁定本场主结论场景（基于已有 scenarios，不重跑模型）。"""
    match = MatchService.get_by_id(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    from services.prediction_runner import lock_match_scenario
    try:
        return mask_prediction(lock_match_scenario(db, match_id, req.scenario_id.strip(), lock=bool(req.lock)), entitlements)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _run_predict_and_save(db, match, model, *, recalculate: bool = False) -> dict:
    from services.prediction_runner import predict_for_match
    from services.metrics_service import record_prediction
    out = predict_for_match(db, match, recalculate=recalculate, model=model)
    record_prediction("batch")
    return out


@router.post("/batch", dependencies=[RequirePredictionBatch])
def batch_calculate(
    req: BatchPredictRequest,
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    """批量计算本页赛事预测。默认跳过已有结果；recalculate=true 时追加新预测记录（保留历史）。"""
    from services.odds_analysis import PredictionSkipped

    ids = list(dict.fromkeys(req.match_ids or []))[:50]
    model = get_ensemble()
    items = []
    skipped = 0
    gated = 0
    failed = []
    calculated = 0
    deadline = time.monotonic() + _BATCH_DEADLINE_SECONDS
    for index, match_id in enumerate(ids):
        if _budget_exceeded(deadline):
            for mid in ids[index:]:
                failed.append({
                    "match_id": mid,
                    "error": "批量计算超时，已停止剩余场次",
                    "code": "TIMEOUT",
                })
            break
        match = MatchService.get_by_id(db, match_id)
        if not match:
            failed.append({"match_id": match_id, "error": "赛事不存在"})
            continue
        if not req.recalculate:
            existing = PredictionService.get_by_match(db, match_id)
            if existing:
                skipped += 1
                items.append(PredictionService.to_api_dict(existing))
                continue
        try:
            items.append(_run_predict_and_save(db, match, model, recalculate=req.recalculate))
            calculated += 1
        except PredictionSkipped as e:
            gated += 1
            skipped += 1
            failed.append({"match_id": match_id, "error": e.reason, "code": e.code, "gated": True})
        except Exception as e:
            failed.append({"match_id": match_id, "error": str(e)})
    return {
        "predictions": mask_prediction_list(items, entitlements),
        "calculated": calculated,
        "skipped": skipped,
        "gated": gated,
        "failed": failed,
        "total": len(ids),
    }


@router.post("/recalculate", dependencies=[RequirePredictionBatch])
def recalculate_predictions(
    req: RecalculateRequest,
    db: Session = Depends(get_db),
    entitlements: Set[str] = Depends(get_current_entitlements),
):
    """
    一键按当前模型重算：
    - scope=upcoming：未开赛赛事（可 only_stale / 含未预测）
    - scope=ids：指定本页 match_ids
    """
    current_version = _current_model_version(db)
    model = get_ensemble()
    limit = int(req.limit or 80)

    matches = []
    if req.scope == "ids":
        ids = list(dict.fromkeys(req.match_ids or []))[:limit]
        if not ids:
            raise HTTPException(status_code=400, detail="scope=ids 时需要提供 match_ids")
        for mid in ids:
            m = MatchService.get_by_id(db, mid)
            if m:
                matches.append(m)
    else:
        # 多取一些再按 stale 过滤；分页 upcoming 默认按日期升序
        fetch_n = min(max(limit * 3, limit), 400)
        page_size = min(100, fetch_n)
        collected = []
        page = 1
        while len(collected) < fetch_n:
            chunk = MatchService.get_paginated_upcoming(
                db, page=page, page_size=page_size, league_id=req.league_id, keyword=None
            )
            if not chunk:
                break
            collected.extend(chunk)
            if len(chunk) < page_size:
                break
            page += 1
        matches = collected

    from services.odds_analysis import PredictionSkipped

    items = []
    skipped = 0
    gated = 0
    failed = []
    calculated = 0
    deadline = time.monotonic() + _RECALC_DEADLINE_SECONDS
    for index, match in enumerate(matches):
        if _budget_exceeded(deadline):
            for left in matches[index:]:
                failed.append({
                    "match_id": left.id,
                    "error": "批量重算超时，已停止剩余场次",
                    "code": "TIMEOUT",
                })
            break
        if req.scope == "upcoming" and calculated >= limit:
            break

        existing = PredictionService.get_by_match(db, match.id)
        if existing is None:
            if not req.include_unpredicted:
                skipped += 1
                continue
        elif req.only_stale and not _prediction_is_stale(existing, current_version):
            skipped += 1
            continue

        try:
            items.append(_run_predict_and_save(db, match, model, recalculate=True))
            calculated += 1
        except PredictionSkipped as e:
            gated += 1
            skipped += 1
            failed.append({"match_id": match.id, "error": e.reason, "code": e.code, "gated": True})
        except Exception as e:
            failed.append({"match_id": match.id, "error": str(e)})

    return {
        "predictions": mask_prediction_list(items, entitlements),
        "calculated": calculated,
        "skipped": skipped,
        "gated": gated,
        "failed": failed,
        "total_candidates": len(matches),
        "model_version": current_version,
        "only_stale": req.only_stale,
        "scope": req.scope,
    }


@router.get("/stale-stats", dependencies=[RequirePredictionBatch])
async def stale_prediction_stats(
    limit: int = Query(200, ge=1, le=500),
    league_id: str = Query(None),
    db: Session = Depends(get_db),
):
    """未赛预测过期统计（缺 meta / 版本落后），供管理页展示。"""
    current_version = _current_model_version(db)
    page_size = min(100, limit)
    collected = []
    page = 1
    while len(collected) < limit:
        chunk = MatchService.get_paginated_upcoming(
            db, page=page, page_size=page_size, league_id=league_id, keyword=None
        )
        if not chunk:
            break
        collected.extend(chunk)
        if len(chunk) < page_size:
            break
        page += 1
    collected = collected[:limit]

    upcoming = len(collected)
    with_pred = 0
    stale = 0
    missing = 0
    missing_scenarios = 0
    for m in collected:
        pred = PredictionService.get_by_match(db, m.id)
        if pred is None:
            missing += 1
            continue
        with_pred += 1
        meta = PredictionService.meta_dict(pred)
        if not meta.get("scenarios") or not meta.get("primary_scenario"):
            missing_scenarios += 1
        if _prediction_is_stale(pred, current_version):
            stale += 1

    return {
        "model_version": current_version,
        "scanned": upcoming,
        "upcoming": upcoming,
        "with_prediction": with_pred,
        "missing_prediction": missing,
        "stale_prediction": stale,
        "missing_scenarios": missing_scenarios,
        "needs_recalc": missing + stale,
    }


@router.delete("/{prediction_id}", dependencies=[RequireMatchWrite])
async def delete_prediction(prediction_id: int, db: Session = Depends(get_db)):
    prediction = PredictionService.get_by_id(db, prediction_id)
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return {"message": "Prediction deleted"}
