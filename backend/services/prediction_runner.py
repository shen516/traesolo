"""统一预测执行：DB 读取 → Redis 缓存 → 融合计算 → 落库。"""

from __future__ import annotations

from typing import Optional

from services import ModelService, PredictionService
from services.ensemble_registry import get_ensemble
from services import prediction_cache


def current_model_version(db) -> str:
    try:
        current = ModelService.get_current(db)
        if current and current.version:
            return current.version
    except Exception:
        pass
    return "v5.0.3"


def payload_from_result(result: dict, db=None) -> dict:
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
        "primary_scenario": result.get("primary_scenario"),
        "scenario_reason": result.get("scenario_reason"),
        "scenario_locked": result.get("scenario_locked"),
        "espn_pipeline": result.get("espn_pipeline"),
        "scenarios": result.get("scenarios"),
        "scenario_order": result.get("scenario_order"),
        "ensemble_probs": result.get("ensemble_probs"),
    }
    return {
        "model_version": current_model_version(db) if db is not None else "v5.0.3",
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


def prediction_is_stale(prediction, current_version: str) -> bool:
    """缺融合 meta、缺分析场景块、或模型版本落后 → 过期。"""
    if not prediction:
        return True
    version = getattr(prediction, "model_version", None) or ""
    if current_version and version != current_version:
        return True
    meta = PredictionService.meta_dict(prediction)
    if not meta:
        return True
    if meta.get("weights_used") is None and meta.get("weight_source") is None:
        return True
    # P0：旧预测无多场景结构，需重算写入
    if not meta.get("scenarios") or not meta.get("primary_scenario"):
        return True
    return False


def _prev_scenario_lock(db, match_id: str):
    existing = PredictionService.get_by_match(db, match_id)
    if not existing:
        return None, False
    meta = PredictionService.meta_dict(existing)
    locked = bool(meta.get("scenario_locked"))
    sid = meta.get("primary_scenario") if locked else None
    return sid, locked


def predict_for_match(db, match, *, recalculate: bool = False, use_cache: bool = True, model=None) -> dict:
    """单场预测：优先 DB / Redis，必要时重算并落库。

    计算与竞彩是否开售无关：无完整 odds_nspf_* 仍可融合并落库。
    """
    model = model or get_ensemble()
    version = current_model_version(db)

    if recalculate:
        prediction_cache.invalidate_match(match.id)
    elif use_cache:
        cached = prediction_cache.get(match.id, version)
        if cached:
            return {**cached, "from_cache": True, "cache_layer": "redis"}
        existing = PredictionService.get_by_match(db, match.id)
        if existing and not prediction_is_stale(existing, version):
            return PredictionService.to_api_dict(existing)

    locked_id, was_locked = _prev_scenario_lock(db, match.id)
    result = model.predict_from_db(db, match.home_team_id, match.away_team_id, match_id=match.id)
    if was_locked and locked_id:
        from services.analysis_scenarios import apply_scenario_override
        scenarios = result.get("scenarios") or {}
        pack = scenarios.get(locked_id) or {}
        # 不可用场景（如无 xG）不强制锁定
        if pack and pack.get("available", True) is not False:
            result = apply_scenario_override(result, locked_id, locked=True)

    payload = payload_from_result(result, db)
    saved = PredictionService.create_or_update(db, match.id, payload)
    api = PredictionService.to_api_dict(saved)
    prediction_cache.set(match.id, version, api)
    return api


def lock_match_scenario(db, match_id: str, scenario_id: str, *, lock: bool = True) -> dict:
    """在已有 scenarios 上切换/锁定主结论（不重新跑模型）。"""
    from services.analysis_scenarios import apply_scenario_override, SCENARIO_META

    existing = PredictionService.get_by_match(db, match_id)
    if not existing:
        raise ValueError("本场尚无预测，请先计算预测")
    api = PredictionService.to_api_dict(existing)
    scenarios = api.get("scenarios") or {}
    if not scenarios:
        raise ValueError("预测缺少场景数据，请先重新计算预测")
    pack = scenarios.get(scenario_id)
    if not pack:
        known = "、".join(SCENARIO_META.keys())
        raise ValueError(f"未知场景 {scenario_id}，可选：{known}")
    if pack.get("available") is False:
        raise ValueError(f"场景「{pack.get('label') or scenario_id}」当前不可用（数据不足）")

    # 用 ORM 行字段拼 result 形态
    result = {
        "lambda_home": api.get("lambda_home"),
        "lambda_away": api.get("lambda_away"),
        "home_win_prob": api.get("home_win_prob"),
        "draw_prob": api.get("draw_prob"),
        "away_win_prob": api.get("away_win_prob"),
        "main_score": api.get("main_score"),
        "alt_scores": api.get("alt_scores"),
        "total_goals": api.get("total_goals"),
        "tendency": api.get("tendency"),
        "confidence": api.get("confidence"),
        "risk_level": api.get("risk_level"),
        "key_variables": api.get("key_variables"),
        "analysis": api.get("analysis"),
        "score_matrix": api.get("score_matrix"),
        "xg_home": api.get("xg_home"),
        "xg_away": api.get("xg_away"),
        "xg_coverage": api.get("xg_coverage"),
        "weights_used": api.get("weights_used"),
        "weight_source": api.get("weight_source"),
        "league_id": api.get("league_id"),
        "elo_home": api.get("elo_home"),
        "elo_away": api.get("elo_away"),
        "hyperparams_used": api.get("hyperparams_used"),
        "env_adjust": api.get("env_adjust"),
        "soft_priors": api.get("soft_priors"),
        "primary_scenario": api.get("primary_scenario"),
        "scenario_reason": api.get("scenario_reason"),
        "espn_pipeline": api.get("espn_pipeline"),
        "scenarios": scenarios,
        "scenario_order": api.get("scenario_order"),
        "ensemble_probs": api.get("ensemble_probs"),
    }
    result = apply_scenario_override(result, scenario_id, locked=lock)
    if not lock:
        # 解锁：保留所选场景为主结论，但不持久锁定
        result["scenario_locked"] = False
        result["scenario_reason"] = (
            f"手动切换主结论为「{(scenarios.get(scenario_id) or {}).get('label') or scenario_id}」"
            "（未锁定，下次重算仍走自动规则）"
        )

    payload = payload_from_result(result, db)
    # 覆盖最新一条，避免锁定操作刷爆历史
    saved = PredictionService.create_or_update(db, match_id, payload, append_history=False)
    version = current_model_version(db)
    api_out = PredictionService.to_api_dict(saved)
    prediction_cache.invalidate_match(match_id)
    prediction_cache.set(match_id, version, api_out)
    return api_out


def predict_teams(
    db,
    home_team_id: str,
    away_team_id: str,
    *,
    match_id: Optional[str] = None,
    recalculate: bool = False,
    save: bool = True,
    model=None,
) -> dict:
    model = model or get_ensemble()
    version = current_model_version(db)

    if match_id and not recalculate:
        cached = prediction_cache.get(match_id, version)
        if cached:
            return {**cached, "from_cache": True}
        existing = PredictionService.get_by_match(db, match_id)
        if existing and not prediction_is_stale(existing, version):
            return PredictionService.to_api_dict(existing)

    if match_id and recalculate:
        prediction_cache.invalidate_match(match_id)

    locked_id, was_locked = (None, False)
    if match_id:
        locked_id, was_locked = _prev_scenario_lock(db, match_id)

    result = model.predict_from_db(db, home_team_id, away_team_id, match_id=match_id)
    if was_locked and locked_id:
        from services.analysis_scenarios import apply_scenario_override
        pack = (result.get("scenarios") or {}).get(locked_id) or {}
        if pack and pack.get("available", True) is not False:
            result = apply_scenario_override(result, locked_id, locked=True)

    payload = payload_from_result(result, db)
    prediction_id = None
    if match_id and save:
        saved = PredictionService.create_or_update(db, match_id, payload)
        prediction_id = saved.id
        api = PredictionService.to_api_dict(saved)
        prediction_cache.set(match_id, version, api)
    else:
        api = {**result, "model_version": version}

    return {
        **result,
        "model_version": payload.get("model_version"),
        "prediction_id": prediction_id,
        "message": "Prediction calculated successfully",
    }
