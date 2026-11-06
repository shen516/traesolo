"""融合权重网格搜索与子模型分量预计算。"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Tuple


def validation_slice(matches: list, max_n: int = 40) -> list:
    if not matches:
        return []
    n = len(matches)
    take = min(max_n, max(8, n // 5))
    return matches[-take:]


def match_model_components(match, ensemble, hyperparams: dict = None) -> dict:
    home_id = match.home_team_id
    away_id = match.away_team_id
    home = ensemble.team_params.get(home_id) or ensemble._get_team_params(home_id)
    away = ensemble.team_params.get(away_id) or ensemble._get_team_params(away_id)
    lid = match.league_id or home.get("league")
    avg = ensemble.league_avg.get(lid, ensemble.league_avg.get(home.get("league"), 2.70))
    if avg is None or float(avg) <= 0:
        avg = 2.70

    hp = hyperparams or ensemble.get_hyperparams_for_league(lid)
    poisson_ha = float(hp.get("poisson_home_advantage", getattr(ensemble, "home_advantage", 1.15)))
    elo_ha = float(hp.get("elo_home_advantage", ensemble.elo.home_advantage))

    ensemble._hydrate_xg_from_params(home_id, home, lid)
    ensemble._hydrate_xg_from_params(away_id, away, lid)

    lambda_home = ensemble.poisson.calculate_lambda(
        float(home["attack"]), float(away["defense"]), float(avg),
        is_home=True, home_adv=poisson_ha,
    )
    lambda_away = ensemble.poisson.calculate_lambda(
        float(away["attack"]), float(home["defense"]), float(avg),
        is_home=False, home_adv=poisson_ha,
    )
    poisson = ensemble.poisson.predict(lambda_home, lambda_away)
    elo = ensemble.elo.predict_prob(
        home_id, away_id,
        rating_a=ensemble.elo.get_rating(home_id),
        rating_b=ensemble.elo.get_rating(away_id),
        home_advantage=elo_ha,
    )
    mc = ensemble.monte_carlo.simulate(lambda_home, lambda_away)

    old_xg_ha = ensemble.xg.home_advantage
    try:
        x_cfg = (ensemble.config or {}).get("xg") or {}
        base_p = float(((ensemble.config or {}).get("poisson") or {}).get("home_advantage", 1.15)) or 1.15
        base_x = float(x_cfg.get("home_advantage", 1.08))
        ensemble.xg.home_advantage = max(1.0, base_x * (poisson_ha / base_p))
        xg = ensemble.xg.predict_prob(
            home_id, away_id, league_id=lid, poisson_model=ensemble.poisson
        )
    finally:
        ensemble.xg.home_advantage = old_xg_ha

    return {
        "elo": {
            "home": elo["home_win_prob"],
            "draw": elo["draw_prob"],
            "away": elo["away_win_prob"],
        },
        "poisson": {
            "home": poisson["home_win_prob"],
            "draw": poisson.get("draw_prob", 0),
            "away": poisson["away_win_prob"],
        },
        "xg": {
            "home": xg["home_win_prob"],
            "draw": xg.get("draw_prob", 0),
            "away": xg["away_win_prob"],
        },
        "xg_coverage": float(xg.get("coverage") or 0),
        "monte_carlo": {
            "home": mc["home_win_prob"],
            "draw": mc["draw_prob"],
            "away": mc["away_win_prob"],
        },
        "league_id": lid,
    }


def precompute_components(matches: list, ensemble, hyperparams: dict = None) -> list:
    """预计算各子模型概率，网格搜索时只做加权，避免重复蒙特卡洛。"""
    from services.eval_metrics import decay_weight

    cache = []
    old_sims = ensemble.monte_carlo.simulations
    ensemble.monte_carlo.simulations = min(old_sims, 2000)
    td = getattr(ensemble, "time_decay", {}) or {}
    ref_date = matches[-1].match_date if matches else date.today()
    try:
        for match in matches:
            home_goals = match.home_goals
            away_goals = match.away_goals
            if home_goals is None or away_goals is None:
                continue
            actual = "home" if home_goals > away_goals else ("away" if home_goals < away_goals else "draw")
            try:
                comps = match_model_components(match, ensemble, hyperparams=hyperparams)
                if not comps:
                    continue
                comps["actual"] = actual
                comps["match_date"] = match.match_date
                comps["sample_weight"] = decay_weight(
                    match.match_date,
                    ref_date=ref_date,
                    half_life_days=float(td.get("half_life_days", 180) or 180),
                    enabled=bool(td.get("enabled", True)),
                )
                cache.append(comps)
            except Exception:
                continue
    finally:
        ensemble.monte_carlo.simulations = old_sims
    return cache


def grid_search_weights(
    cache: list,
    weight_options: list,
    ensemble=None,
) -> Tuple[Dict[str, float], float, Dict[str, Any]]:
    from services.eval_metrics import (
        average_metrics,
        is_better,
        score_cache,
        walk_forward_slices,
    )

    if ensemble is None:
        from services.ensemble_registry import get_ensemble
        ensemble = get_ensemble()

    ev = getattr(ensemble, "evaluation", {}) or {}
    primary = str(ev.get("primary_metric") or "brier").lower()
    folds = int(ev.get("walk_forward_folds") or 3)
    bins = int(ev.get("calibration_bins") or 5)
    max_mc = float(getattr(ensemble, "max_monte_carlo_weight", 0.28) or 0.28)
    min_mc = float(getattr(ensemble, "min_monte_carlo_weight", 0.05) or 0.05)

    best_weights = ensemble._normalize_weights(
        {"elo": 0.30, "poisson": 0.30, "xg": 0.22, "monte_carlo": 0.18}
    )
    best_metrics = {"n": 0, "accuracy": -1.0, "brier": 9e9}
    if not cache:
        return best_weights, 0.0, best_metrics

    slices = walk_forward_slices(cache, folds=folds)

    for elo_w in weight_options:
        for poisson_w in weight_options:
            for xg_w in weight_options:
                mc_w = 1.0 - elo_w - poisson_w - xg_w
                if mc_w < min_mc - 1e-9 or mc_w > max_mc + 1e-9:
                    continue
                temp = {
                    "elo": elo_w,
                    "poisson": poisson_w,
                    "xg": xg_w,
                    "monte_carlo": mc_w,
                }
                temp = ensemble._normalize_weights(temp)
                fold_metrics = [
                    score_cache(sl, temp, calibration_bins=bins) for sl in slices
                ]
                metrics = average_metrics(fold_metrics)
                if is_better(metrics, best_metrics, primary=primary):
                    best_metrics = metrics
                    best_weights = temp

    final_metrics = score_cache(cache, best_weights, calibration_bins=bins)
    final_metrics["folds"] = best_metrics.get("folds") or len(slices)
    final_metrics["primary_metric"] = primary
    return best_weights, float(final_metrics.get("accuracy") or 0), final_metrics


def score_weights(cache: list, weights: dict) -> float:
    from services.eval_metrics import score_cache
    return float(score_cache(cache, weights).get("accuracy") or 0)


def validate_weights(weights: dict, matches: list, ensemble, db=None) -> float:
    """兼容旧调用：预计算后评分。"""
    cache = precompute_components(matches, ensemble)
    return score_weights(cache, weights)
