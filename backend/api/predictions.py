"""预测API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from db.database import get_db
from services import PredictionService, MatchService, TeamService, ModelService
from services.subscription_service import mask_prediction, mask_prediction_list
from api.deps import get_current_entitlements
from pydantic import BaseModel, Field, model_validator
from typing import Dict, List, Optional, Literal, Set
import json
import logging
import threading
import time
from api.authz import (
    RequireMatchRead, RequireMatchWrite, RequirePredictionCalc, RequirePredictionBatch,
    RequireSimulation,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# 同步 def 会进线程池，事件循环不被蒙特卡洛占住。整批另设墙钟上限。
_BATCH_DEADLINE_SECONDS = 100
_RECALC_DEADLINE_SECONDS = 180

# /simulate 为 CPU 密集（最高 50000 次蒙特卡洛 × 基线/模拟两遍），
# 限制同时执行数，超出直接 429，避免线程池被长任务耗尽。
_SIMULATE_MAX_CONCURRENCY = 2
_SIMULATE_SEMAPHORE = threading.Semaphore(_SIMULATE_MAX_CONCURRENCY)


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
        logger.warning(
            "resolve current model version failed; fallback v5.0.3",
            exc_info=True,
        )
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


class SimulationWeights(BaseModel):
    elo: Optional[float] = Field(None, ge=0, le=1)
    poisson: Optional[float] = Field(None, ge=0, le=1)
    xg: Optional[float] = Field(None, ge=0, le=1)
    monte_carlo: Optional[float] = Field(None, ge=0, le=1)


class ManualSpThreeWay(BaseModel):
    """胜平负 / 让球胜平负的手动 SP：各项可选，传入须 > 0。"""
    win: Optional[float] = Field(None, gt=0)
    draw: Optional[float] = Field(None, gt=0)
    lose: Optional[float] = Field(None, gt=0)

    def to_dict(self) -> Dict[str, float]:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class ManualSp(BaseModel):
    """手动 SP 覆盖：按玩法分组，选项键须为合法竞彩选项名，SP 须 > 0。"""
    spf: Optional[ManualSpThreeWay] = None
    nspf: Optional[ManualSpThreeWay] = None
    bf: Optional[Dict[str, float]] = None
    tg: Optional[Dict[str, float]] = None

    @model_validator(mode="after")
    def _validate_option_keys(self):
        from services.prize_calculator import BF_ALL_KEYS, TG_KEYS
        for label, mapping, valid_keys in (
            ("比分", self.bf, BF_ALL_KEYS),
            ("总进球", self.tg, TG_KEYS),
        ):
            if not mapping:
                continue
            invalid = [k for k in mapping if k not in valid_keys]
            if invalid:
                raise ValueError(f"非法{label}选项: {', '.join(map(str, invalid[:5]))}")
            if any(v is None or float(v) <= 0 for v in mapping.values()):
                raise ValueError(f"{label} SP 必须大于 0")
        return self

    def to_dict(self) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        if self.spf and self.spf.to_dict():
            out["spf"] = self.spf.to_dict()
        if self.nspf and self.nspf.to_dict():
            out["nspf"] = self.nspf.to_dict()
        if self.bf:
            out["bf"] = {k: float(v) for k, v in self.bf.items()}
        if self.tg:
            out["tg"] = {k: float(v) for k, v in self.tg.items()}
        return out


class SimulationOverrides(BaseModel):
    """高级选项：全部可选，不传即等价于该赛事的只读重新计算。"""
    lambda_home: Optional[float] = Field(None, ge=0.05, le=6.0)
    lambda_away: Optional[float] = Field(None, ge=0.05, le=6.0)
    xg_lambda_home: Optional[float] = Field(None, ge=0.05, le=6.0)
    xg_lambda_away: Optional[float] = Field(None, ge=0.05, le=6.0)
    weights: Optional[SimulationWeights] = None
    poisson_home_advantage: Optional[float] = Field(None, ge=0.8, le=1.6)
    league_avg_goals: Optional[float] = Field(None, ge=1.5, le=4.5)
    max_goals: Optional[int] = Field(None, ge=5, le=10)
    # 枚举须与 environment_service / config.yaml 的 λ_factor 表一致，
    # 非法值会让系数静默为 1，故在 API 层直接 422。
    weather: Optional[Literal["晴", "多云", "阴", "小雨", "大雨", "雪"]] = None
    temperature: Optional[str] = Field(None, max_length=20)
    pitch_condition: Optional[Literal["优秀", "良好", "一般", "较差"]] = None
    # 奖金计算模式
    sp_mode: Optional[Literal["auto", "real", "synthetic"]] = "auto"
    overround: Optional[float] = Field(None, ge=0.05, le=0.30)
    handicap: Optional[int] = Field(None, ge=-10, le=10)
    manual_sp: Optional[ManualSp] = None


class SimulationRequest(BaseModel):
    match_id: str = Field(..., description="目标未来赛事，须 status=upcoming")
    simulations: int = Field(10000, ge=1000, le=50000)
    seed: Optional[int] = Field(None, ge=0, le=2**32 - 1)
    overrides: Optional[SimulationOverrides] = None


class SensitivityRequest(BaseModel):
    """λ 敏感性扫描：默认低模拟次数控制成本。"""
    match_id: str
    simulations: int = Field(2000, ge=1000, le=10000)
    seed: Optional[int] = Field(None, ge=0, le=2**32 - 1)
    overrides: Optional[SimulationOverrides] = None


class BatchSimulateRequest(BaseModel):
    """批量模拟 + 串关奖金：2~8 场未来赛事。"""
    match_ids: List[str] = Field(..., min_length=2, max_length=8)
    simulations: int = Field(5000, ge=1000, le=20000)
    seed: Optional[int] = Field(None, ge=0, le=2**32 - 1)
    sp_mode: Literal["auto", "real", "synthetic"] = "auto"
    overround: float = Field(0.13, ge=0.05, le=0.30)


def _check_weights_sum(req) -> None:
    if req.overrides and req.overrides.weights is not None:
        total = sum(
            v for v in req.overrides.weights.model_dump(exclude_none=True).values()
            if isinstance(v, (int, float))
        )
        if total <= 0:
            raise HTTPException(status_code=400, detail="融合权重之和必须大于 0")


@router.post("/simulate", dependencies=[RequireSimulation])
def simulate_prediction(req: SimulationRequest, db: Session = Depends(get_db)):
    """对已排期未来赛事做只读比分模拟预测（不写 predictions 表）。

    同步 def：进入线程池，避免蒙特卡洛阻塞事件循环。
    相同参数短时间内重复请求命中内存 TTL 缓存（meta.cache_hit 标记）。
    """
    from services import simulation_cache
    from services.simulation_service import simulate_match

    _check_weights_sum(req)

    cache_key = simulation_cache.make_key(
        req.match_id, req.simulations, req.seed,
        req.overrides.model_dump(exclude_none=True) if req.overrides else None,
    )
    cached = simulation_cache.get(cache_key)
    if cached is not None:
        cached["meta"] = dict(cached.get("meta") or {}, cache_hit=True)
        return cached

    if not _SIMULATE_SEMAPHORE.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="模拟任务繁忙，请稍后再试")
    try:
        result = simulate_match(db, req)
    finally:
        _SIMULATE_SEMAPHORE.release()

    simulation_cache.set(cache_key, result)
    result["meta"] = dict(result.get("meta") or {}, cache_hit=False)
    return result


@router.post("/simulate/sensitivity", dependencies=[RequireSimulation])
def simulate_sensitivity(req: SensitivityRequest, db: Session = Depends(get_db)):
    """λ 敏感性分析：主/客 λ 在基准值 ±0.3（步长 0.1）扫描的胜平负概率曲线数据。"""
    from services.simulation_service import sensitivity_lambda

    _check_weights_sum(req)
    if not _SIMULATE_SEMAPHORE.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="模拟任务繁忙，请稍后再试")
    try:
        return sensitivity_lambda(db, req)
    finally:
        _SIMULATE_SEMAPHORE.release()


@router.post("/simulate/batch", dependencies=[RequireSimulation])
def simulate_batch(req: BatchSimulateRequest, db: Session = Depends(get_db)):
    """批量模拟多场未来赛事，并计算 2串1~8串1 串关奖金（胜平负组合）。"""
    from services.simulation_service import simulate_batch as batch_run

    if not _SIMULATE_SEMAPHORE.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="模拟任务繁忙，请稍后再试")
    try:
        return batch_run(db, req)
    finally:
        _SIMULATE_SEMAPHORE.release()


@router.get("/simulate/history", dependencies=[RequireSimulation])
def simulate_history(
    limit: int = Query(20, ge=1, le=50),
    match_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """模拟历史：最近 N 次模拟的参数与结果摘要（仅回看，非正式预测记录）。"""
    from services.simulation_service import list_history
    return {"history": list_history(db, limit=limit, match_id=match_id)}


class BacktestRequest(BaseModel):
    """用当前 overrides 在完赛样本上评估命中率 / Brier（只读，不写 predictions）。"""
    overrides: Optional[SimulationOverrides] = None
    league_id: Optional[str] = None
    days: int = Field(60, ge=7, le=180)
    limit: int = Field(60, ge=10, le=120)
    simulations: int = Field(2000, ge=500, le=5000)
    seed: Optional[int] = Field(None, ge=0, le=2**32 - 1)


@router.post("/simulate/backtest", dependencies=[RequireSimulation])
def simulate_backtest(req: BacktestRequest, db: Session = Depends(get_db)):
    """历史回测联动：完赛样本上验证参数组合（分析用，非投注建议）。"""
    from services.simulation_backtest import run_parameter_backtest

    _check_weights_sum(req)
    if not _SIMULATE_SEMAPHORE.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="模拟任务繁忙，请稍后再试")
    try:
        return run_parameter_backtest(
            db,
            overrides=req.overrides,
            league_id=req.league_id,
            days=req.days,
            limit=req.limit,
            seed=req.seed,
            simulations=req.simulations,
        )
    finally:
        _SIMULATE_SEMAPHORE.release()


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
