"""模拟预测编排层：对已排期未来赛事做只读推演。

- 校验赛事存在且 status='upcoming'
- 主客队/联赛/环境参数取自赛事与数据库
- 基线（默认参数）与模拟（覆盖参数）使用相同模拟次数与种子
- 不写 predictions 表、不写正式预测缓存、不触发正式预测流程
- 模拟历史（simulation_history）仅用于回看，独立于正式预测记录
"""

from __future__ import annotations

import copy
import json
import time
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import SimulationHistory
from services import MatchService, TeamService, LeagueService
from services.ensemble_registry import get_ensemble
from services.prize_calculator import calculate_prize

_SIM_TEMPLATE = None

HISTORY_LIMIT = 50
_LAMBDA_MIN, _LAMBDA_MAX = 0.05, 6.0


def _get_template():
    """模块级模板：EnsembleModel() 需读 config.yaml 并初始化四个子模型，仅首次构建。"""
    global _SIM_TEMPLATE
    if _SIM_TEMPLATE is None:
        from models.ensemble import EnsembleModel
        _SIM_TEMPLATE = EnsembleModel()
    return _SIM_TEMPLATE


def _build_ensemble():
    """轻量实例（方案 A）：共享模板子模型，权重/超参从全局单例复制。

    predict() 不修改权重/超参，xg.home_advantage 的临时切换有 try/finally 保护，
    因此跨请求共享子模型安全，避免每请求重建的高昂开销。
    """
    src = get_ensemble()
    ens = copy.copy(_get_template())
    ens.weights = dict(src.weights)
    ens.league_weights = {k: dict(v) for k, v in (src.league_weights or {}).items()}
    ens.league_hyperparams = {k: dict(v) for k, v in (src.league_hyperparams or {}).items()}
    ens.global_hyperparams = dict(src.global_hyperparams)
    return ens


def _team_payload(team) -> Dict[str, Any]:
    return {
        "id": team.id,
        "name": team.name,
        "league_id": team.league_id,
        "elo": team.elo_rating,
        "attack": float(team.attack_strength),
        "defense": float(team.defense_strength),
        "xg_for": float(team.xg_for),
        "xg_against": float(team.xg_against),
    }


def _params_for(team) -> Dict[str, Any]:
    return {
        "attack": float(team.attack_strength),
        "defense": float(team.defense_strength),
        "xg_for": float(team.xg_for),
        "xg_against": float(team.xg_against),
        "league": team.league_id,
        "name": team.name,
    }


def _result_payload(result: Dict[str, Any], mc_detailed: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ens = result["ensemble_probs"]
    payload = {
        "home_win_prob": ens["home_win_prob"],
        "draw_prob": ens["draw_prob"],
        "away_win_prob": ens["away_win_prob"],
        "lambda_home": result["lambda_home"],
        "lambda_away": result["lambda_away"],
        "xg_lambda_home": result.get("xg_home"),
        "xg_lambda_away": result.get("xg_away"),
        "main_score": result["main_score"],
        "alt_scores": result["alt_scores"],
        "weights_used": ens["weights_used"],
        "weight_source": ens["weight_source"],
        "components": result.get("components") or {},
        "scenarios": result.get("scenarios") or {},
    }
    if mc_detailed:
        payload["mc"] = {
            "simulations": mc_detailed.get("simulations"),
            "seed": mc_detailed.get("seed"),
            "top_scores": mc_detailed.get("top_scores"),
            "goal_distribution": mc_detailed.get("goal_distribution"),
            "total_goals_avg": mc_detailed.get("total_goals_avg"),
            "total_goals_std": mc_detailed.get("total_goals_std"),
            "over_2_5_prob": mc_detailed.get("over_2_5_prob"),
            "over_3_5_prob": mc_detailed.get("over_3_5_prob"),
            "btts_prob": mc_detailed.get("btts_prob"),
            "score_matrix": mc_detailed.get("score_matrix"),
            "score_matrix_size": mc_detailed.get("score_matrix_size"),
        }
    return payload


def _delta(baseline: Dict[str, Any], simulated: Dict[str, Any]) -> Dict[str, float]:
    return {
        "home_win_prob": round(simulated["home_win_prob"] - baseline["home_win_prob"], 4),
        "draw_prob": round(simulated["draw_prob"] - baseline["draw_prob"], 4),
        "away_win_prob": round(simulated["away_win_prob"] - baseline["away_win_prob"], 4),
        "lambda_home": round(simulated["lambda_home"] - baseline["lambda_home"], 4),
        "lambda_away": round(simulated["lambda_away"] - baseline["lambda_away"], 4),
    }


def _empty_overrides(overrides):
    """request.overrides 为 None 时返回同类型空实例（批量内部用简单对象，返回 None 即可）。"""
    if overrides is None:
        return None
    return type(overrides)()


def _prepare_match(db: Session, match_id: str) -> Dict[str, Any]:
    """校验赛事并取主客队/联赛，供模拟/敏感性/批量复用。"""
    match = MatchService.get_by_id(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="赛事不存在")
    if match.status != "upcoming":
        raise HTTPException(status_code=400, detail="仅支持对未开赛（upcoming）赛事进行模拟预测")
    home = TeamService.get_by_id(db, match.home_team_id)
    away = TeamService.get_by_id(db, match.away_team_id)
    if not home or not away:
        raise HTTPException(status_code=404, detail="赛事主客队信息缺失")
    league = LeagueService.get_by_id(db, match.league_id) if match.league_id else None
    return {"match": match, "home": home, "away": away, "league": league}


def _common_predict_kwargs(ctx: Dict[str, Any], overrides, request) -> Dict[str, Any]:
    home, away, match = ctx["home"], ctx["away"], ctx["match"]
    league = ctx["league"]
    league_avg = getattr(overrides, "league_avg_goals", None)
    if league_avg is None and league and league.avg_goals:
        league_avg = float(league.avg_goals)
    max_goals = getattr(overrides, "max_goals", None) or 8
    return dict(
        home_params=_params_for(home),
        away_params=_params_for(away),
        elo_home=home.elo_rating,
        elo_away=away.elo_rating,
        league_avg=league_avg,
        league_id=match.league_id,
        simulations=request.simulations,
        seed=request.seed,
        max_goals=max_goals,
    )


def simulate_match(db: Session, request) -> Dict[str, Any]:
    """执行模拟预测。request 为 api 层 SimulationRequest。"""
    started = time.monotonic()

    ctx = _prepare_match(db, request.match_id)
    match, home, away, league = ctx["match"], ctx["home"], ctx["away"], ctx["league"]

    overrides = request.overrides or _empty_overrides(request.overrides)
    applied = []

    # 环境：默认取赛事字段，可被覆盖
    weather = getattr(overrides, "weather", None) or match.weather
    temperature = getattr(overrides, "temperature", None) or match.temperature
    pitch_condition = getattr(overrides, "pitch_condition", None) or match.pitch_condition
    for key in ("weather", "temperature", "pitch_condition"):
        if getattr(overrides, key, None) is not None:
            applied.append(key)

    league_avg = getattr(overrides, "league_avg_goals", None)
    if league_avg is not None:
        applied.append("league_avg_goals")

    lambda_override = None
    lh, la = getattr(overrides, "lambda_home", None), getattr(overrides, "lambda_away", None)
    if lh is not None or la is not None:
        lambda_override = {"home": lh, "away": la}
        if lh is not None:
            applied.append("lambda_home")
        if la is not None:
            applied.append("lambda_away")

    xg_lambda_override = None
    xlh, xla = getattr(overrides, "xg_lambda_home", None), getattr(overrides, "xg_lambda_away", None)
    if xlh is not None or xla is not None:
        xg_lambda_override = {"home": xlh, "away": xla}
        if xlh is not None:
            applied.append("xg_lambda_home")
        if xla is not None:
            applied.append("xg_lambda_away")

    weights = getattr(overrides, "weights", None)
    if weights is not None:
        if hasattr(weights, "model_dump"):
            weights = {k: v for k, v in weights.model_dump().items() if v is not None}
        applied.append("weights")
    poisson_ha = getattr(overrides, "poisson_home_advantage", None)
    if poisson_ha is not None:
        applied.append("poisson_home_advantage")

    ensemble = _build_ensemble()
    common = _common_predict_kwargs(ctx, overrides, request)

    # 基线：默认参数（与请求同种子同次数）
    baseline_result = ensemble.predict(
        home.name, away.name,
        weather=match.weather, temperature=match.temperature,
        pitch_condition=match.pitch_condition,
        detailed_mc=True,
        **common,
    )

    # 模拟：应用覆盖参数。无任何覆盖时与基线完全等价，直接复用，避免重复蒙特卡洛。
    if applied:
        simulated_result = ensemble.predict(
            home.name, away.name,
            weather=weather, temperature=temperature, pitch_condition=pitch_condition,
            lambda_override=lambda_override,
            xg_lambda_override=xg_lambda_override,
            weights=weights,
            poisson_home_advantage=poisson_ha,
            detailed_mc=True,
            **common,
        )
    else:
        simulated_result = baseline_result

    baseline = _result_payload(baseline_result, baseline_result.get("mc_detailed"))
    simulated = _result_payload(simulated_result, simulated_result.get("mc_detailed"))

    warnings = list(dict.fromkeys(
        list(baseline_result.get("warnings") or []) + list(simulated_result.get("warnings") or [])
    ))

    manual_sp = getattr(overrides, "manual_sp", None)
    if manual_sp is not None and hasattr(manual_sp, "to_dict"):
        manual_sp = manual_sp.to_dict()

    prize = calculate_prize(
        db, match, simulated_result["mc_detailed"],
        sp_mode=getattr(overrides, "sp_mode", "auto") or "auto",
        overround=getattr(overrides, "overround", 0.13) or 0.13,
        handicap=getattr(overrides, "handicap", None),
        manual_sp=manual_sp,
    )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    result = {
        "match": {
            "id": match.id,
            "league_id": match.league_id,
            "league_name": league.name if league else None,
            "match_date": str(match.match_date) if match.match_date else None,
            "match_time": str(match.match_time) if match.match_time else None,
            "match_no": match.match_no,
            "status": match.status,
            "handicap": match.handicap,
            "home_team": {"id": home.id, "name": home.name},
            "away_team": {"id": away.id, "name": away.name},
        },
        "home": _team_payload(home),
        "away": _team_payload(away),
        "league": {
            "id": league.id if league else match.league_id,
            "name": league.name if league else None,
            "avg_goals": float(league.avg_goals) if league and league.avg_goals else None,
        },
        "baseline": baseline,
        "simulated": simulated,
        "delta": _delta(baseline, simulated),
        "prize": prize,
        "meta": {
            "elapsed_ms": elapsed_ms,
            "simulations": request.simulations,
            "seed": request.seed,
            "applied_overrides": applied,
            "warnings": warnings,
        },
    }
    save_history(db, request, result, elapsed_ms)
    return result


def _history_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    sim = result["simulated"]
    prize = result.get("prize") or {}
    spf = prize.get("spf") or {}
    flags = spf.get("value_flags") or {}
    return {
        "home_win_prob": sim["home_win_prob"],
        "draw_prob": sim["draw_prob"],
        "away_win_prob": sim["away_win_prob"],
        "lambda_home": sim["lambda_home"],
        "lambda_away": sim["lambda_away"],
        "main_score": sim["main_score"],
        "spf_value_flags": {k: v for k, v in flags.items() if v},
    }


def save_history(db: Session, request, result: Dict[str, Any], elapsed_ms: int) -> None:
    """保存模拟历史（最近 HISTORY_LIMIT 条）。失败不影响模拟结果返回。"""
    try:
        overrides = request.overrides
        if overrides is not None and hasattr(overrides, "model_dump"):
            params = overrides.model_dump(exclude_none=True)
        else:
            params = {}
        db.add(SimulationHistory(
            match_id=str(request.match_id),
            match_name=f'{result["match"]["home_team"]["name"]} vs {result["match"]["away_team"]["name"]}',
            simulations=request.simulations,
            seed=request.seed,
            params_json=json.dumps(params, ensure_ascii=False),
            summary_json=json.dumps(_history_summary(result), ensure_ascii=False),
            elapsed_ms=elapsed_ms,
        ))
        db.commit()
        _trim_history(db)
    except Exception:
        db.rollback()


def _trim_history(db: Session) -> None:
    count = db.query(func.count(SimulationHistory.id)).scalar() or 0
    excess = count - HISTORY_LIMIT
    if excess > 0:
        oldest = (
            db.query(SimulationHistory.id)
            .order_by(SimulationHistory.created_at.asc(), SimulationHistory.id.asc())
            .limit(excess)
            .all()
        )
        db.query(SimulationHistory).filter(SimulationHistory.id.in_([r[0] for r in oldest])).delete(
            synchronize_session=False
        )
        db.commit()


def list_history(db: Session, limit: int = 20, match_id: Optional[str] = None) -> List[Dict[str, Any]]:
    q = db.query(SimulationHistory)
    if match_id:
        q = q.filter(SimulationHistory.match_id == str(match_id))
    rows = q.order_by(SimulationHistory.created_at.desc(), SimulationHistory.id.desc()).limit(limit).all()
    out = []
    for r in rows:
        out.append({
            "id": r.id,
            "match_id": r.match_id,
            "match_name": r.match_name,
            "simulations": r.simulations,
            "seed": r.seed,
            "params": json.loads(r.params_json) if r.params_json else {},
            "summary": json.loads(r.summary_json) if r.summary_json else {},
            "elapsed_ms": r.elapsed_ms,
            "created_at": str(r.created_at) if r.created_at else None,
        })
    return out


def sensitivity_lambda(db: Session, request) -> Dict[str, Any]:
    """λ 敏感性扫描：对 lambda_home / lambda_away 在基准值 ±0.3（步长 0.1）逐点模拟。

    其余覆盖参数与 SimulationRequest 一致；用较低模拟次数控制成本。
    """
    ctx = _prepare_match(db, request.match_id)
    match, home, away = ctx["match"], ctx["home"], ctx["away"]
    overrides = request.overrides or _empty_overrides(request.overrides)

    ensemble = _build_ensemble()
    common = _common_predict_kwargs(ctx, overrides, request)

    weather = getattr(overrides, "weather", None) or match.weather
    temperature = getattr(overrides, "temperature", None) or match.temperature
    pitch_condition = getattr(overrides, "pitch_condition", None) or match.pitch_condition

    xg_lambda_override = None
    xlh, xla = getattr(overrides, "xg_lambda_home", None), getattr(overrides, "xg_lambda_away", None)
    if xlh is not None or xla is not None:
        xg_lambda_override = {"home": xlh, "away": xla}
    weights = getattr(overrides, "weights", None)
    if weights is not None and hasattr(weights, "model_dump"):
        weights = {k: v for k, v in weights.model_dump().items() if v is not None}
    poisson_ha = getattr(overrides, "poisson_home_advantage", None)

    # 基准点：先跑一次取基线 λ（含其它覆盖，但不含 λ 覆盖）
    base = ensemble.predict(
        home.name, away.name,
        weather=weather, temperature=temperature, pitch_condition=pitch_condition,
        xg_lambda_override=xg_lambda_override, weights=weights,
        poisson_home_advantage=poisson_ha, detailed_mc=False,
        **common,
    )
    base_lh = float(base["lambda_home"])
    base_la = float(base["lambda_away"])

    def clamp(v: float) -> float:
        return max(_LAMBDA_MIN, min(_LAMBDA_MAX, round(v, 4)))

    def scan(base_value: float, key: str) -> List[Dict[str, Any]]:
        points = []
        for delta in (-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3):
            lam = clamp(base_value + delta)
            lo = {"home": lam, "away": None} if key == "home" else {"home": None, "away": lam}
            r = ensemble.predict(
                home.name, away.name,
                weather=weather, temperature=temperature, pitch_condition=pitch_condition,
                lambda_override=lo,
                xg_lambda_override=xg_lambda_override, weights=weights,
                poisson_home_advantage=poisson_ha, detailed_mc=False,
                **common,
            )
            points.append({
                "lambda": lam,
                "delta": round(delta, 1),
                "home_win_prob": r["ensemble_probs"]["home_win_prob"],
                "draw_prob": r["ensemble_probs"]["draw_prob"],
                "away_win_prob": r["ensemble_probs"]["away_win_prob"],
            })
        return points

    series = {
        "lambda_home": {"base": base_lh, "points": scan(base_lh, "home")},
        "lambda_away": {"base": base_la, "points": scan(base_la, "away")},
    }
    return {
        "match": {"id": match.id, "home_team": home.name, "away_team": away.name},
        "meta": {
            "simulations": request.simulations,
            "seed": request.seed,
            "step": 0.1,
            "range": 0.3,
        },
        "series": series,
    }


def simulate_batch(db: Session, request) -> Dict[str, Any]:
    """批量模拟多场赛事并计算串关奖金。

    - 未传 legs：3^n 全展开（胜平负组合）分析，向后兼容。
    - 传了 legs：按指定选项（全玩法）做单组串关落单分析（§12-7）。
    """
    started = time.monotonic()
    match_ids = list(dict.fromkeys(request.match_ids))  # 去重保序
    results, errors = [], []
    legs = []
    for mid in match_ids:
        try:
            one = simulate_match(db, _SingleRequest(
                match_id=mid,
                simulations=request.simulations,
                seed=request.seed,
                sp_mode=request.sp_mode,
                overround=request.overround,
            ))
        except HTTPException as e:
            errors.append({"match_id": mid, "detail": e.detail})
            continue
        results.append(one)
        spf = (one.get("prize") or {}).get("spf") or {}
        legs.append({
            "match_id": mid,
            "match_name": f'{one["match"]["home_team"]["name"]} vs {one["match"]["away_team"]["name"]}',
            "probs": spf.get("probs") or {},
            "spf": spf.get("sp") or {},
        })

    parlay = None
    selected_legs = getattr(request, "legs", None)
    if selected_legs:
        parlay = _build_selected_parlay(results, selected_legs)
    elif len(legs) >= 2:
        from services.parlay_calculator import calculate_parlay
        parlay = calculate_parlay(legs)

    return {
        "results": results,
        "errors": errors,
        "parlay": parlay,
        "meta": {
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "requested": len(request.match_ids),
            "succeeded": len(results),
            "failed": len(errors),
            "simulations": request.simulations,
            "seed": request.seed,
        },
    }


def _build_selected_parlay(results: List[Dict[str, Any]], selected_legs) -> Optional[Dict[str, Any]]:
    """按用户选定选项（全玩法）构造单组串关落单分析（§12-7）。

    selected_legs: [{match_id, play_type, selection}]，须与 results 的 match_id 对应。
    从每场 prize.<play_type> 块提取 sp/probs，交给 parlay_calculator.calculate_parlay_picks。
    """
    from services.parlay_calculator import calculate_parlay_picks

    by_id = {r["match"]["id"]: r for r in results}
    picks = []
    for leg in selected_legs:
        mid = leg.match_id if hasattr(leg, "match_id") else leg.get("match_id")
        play_type = leg.play_type if hasattr(leg, "play_type") else leg.get("play_type")
        selection = leg.selection if hasattr(leg, "selection") else leg.get("selection")
        one = by_id.get(mid)
        if not one:
            continue
        prize = one.get("prize") or {}
        block = prize.get(play_type) or {}
        sp_map = block.get("sp") or {}
        prob_map = block.get("probs") or {}
        if selection not in sp_map or selection not in prob_map:
            continue
        picks.append({
            "match_id": mid,
            "match_name": f'{one["match"]["home_team"]["name"]} vs {one["match"]["away_team"]["name"]}',
            "play_type": play_type,
            "option": selection,
            "sp": sp_map[selection],
            "prob": prob_map[selection],
        })
    if len(picks) < 2:
        return None
    try:
        return calculate_parlay_picks(picks)
    except ValueError:
        return None


class _SingleRequest:
    """批量内部复用的轻量请求对象（与 SimulationRequest 字段兼容）。"""

    def __init__(self, match_id: str, simulations: int, seed: Optional[int],
                 sp_mode: str = "auto", overround: float = 0.13):
        from types import SimpleNamespace
        self.match_id = match_id
        self.simulations = simulations
        self.seed = seed
        # 仅承载 sp_mode/overround，其余覆盖属性缺省为 None（getattr 默认值生效）
        self.overrides = SimpleNamespace(sp_mode=sp_mode, overround=overround)
