"""模拟参数历史回测：用已完赛样本评估 overrides 下的命中率 / Brier（分析用，非投注）。"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from db.models import Match
from services import LeagueService, TeamService
from services.eval_metrics import _one_hot, predict_label
from services.simulation_service import _build_ensemble, _params_for

logger = logging.getLogger(__name__)


def _actual_outcome(match: Match) -> Optional[str]:
    r = (match.result or "").upper()
    if r == "H":
        return "home"
    if r == "A":
        return "away"
    if r == "D":
        return "draw"
    if match.home_goals is not None and match.away_goals is not None:
        if match.home_goals > match.away_goals:
            return "home"
        if match.home_goals < match.away_goals:
            return "away"
        return "draw"
    return None


def _overrides_dict(overrides) -> Dict[str, Any]:
    if overrides is None:
        return {}
    if hasattr(overrides, "model_dump"):
        raw = overrides.model_dump(exclude_none=True)
    elif isinstance(overrides, dict):
        raw = {k: v for k, v in overrides.items() if v is not None}
    else:
        return {}
    drop = {"sp_mode", "overround", "handicap", "manual_sp"}
    out = {k: v for k, v in raw.items() if k not in drop}
    if "weights" in out and hasattr(out["weights"], "model_dump"):
        out["weights"] = out["weights"].model_dump(exclude_none=True)
    elif "weights" in out and isinstance(out["weights"], dict):
        out["weights"] = {k: float(v) for k, v in out["weights"].items() if v is not None}
    return out


def run_parameter_backtest(
    db: Session,
    *,
    overrides=None,
    league_id: Optional[str] = None,
    days: int = 60,
    limit: int = 60,
    seed: Optional[int] = None,
    simulations: int = 2000,
) -> Dict[str, Any]:
    """对完赛场次用融合引擎 + overrides 重算胜平负，统计命中与 Brier。不写 predictions。"""
    days = max(7, min(int(days), 180))
    limit = max(10, min(int(limit), 120))
    simulations = max(500, min(int(simulations), 5000))
    since = date.today() - timedelta(days=days)
    ov = _overrides_dict(overrides)

    q = db.query(Match).filter(
        Match.status == "finished",
        Match.match_date >= since,
        Match.home_goals.isnot(None),
        Match.away_goals.isnot(None),
        Match.home_team_id.isnot(None),
        Match.away_team_id.isnot(None),
    )
    if league_id:
        q = q.filter(Match.league_id == str(league_id))
    matches: List[Match] = (
        q.order_by(Match.match_date.desc(), Match.id.desc()).limit(limit).all()
    )

    ensemble = _build_ensemble()
    correct = 0
    total = 0
    brier_sum = 0.0
    samples: List[dict] = []
    errors = 0

    weights = ov.get("weights")
    poisson_ha = ov.get("poisson_home_advantage")
    league_avg_ov = ov.get("league_avg_goals")
    lambda_override = None
    if ov.get("lambda_home") is not None or ov.get("lambda_away") is not None:
        lambda_override = {"home": ov.get("lambda_home"), "away": ov.get("lambda_away")}
    xg_lambda_override = None
    if ov.get("xg_lambda_home") is not None or ov.get("xg_lambda_away") is not None:
        xg_lambda_override = {
            "home": ov.get("xg_lambda_home"),
            "away": ov.get("xg_lambda_away"),
        }

    for match in matches:
        actual = _actual_outcome(match)
        if not actual:
            continue
        home = TeamService.get_by_id(db, match.home_team_id)
        away = TeamService.get_by_id(db, match.away_team_id)
        if not home or not away:
            continue
        league = LeagueService.get_by_id(db, match.league_id) if match.league_id else None
        league_avg = league_avg_ov
        if league_avg is None and league and league.avg_goals:
            league_avg = float(league.avg_goals)
        try:
            result = ensemble.predict(
                home.name,
                away.name,
                home_params=_params_for(home),
                away_params=_params_for(away),
                elo_home=home.elo_rating,
                elo_away=away.elo_rating,
                league_avg=league_avg,
                league_id=match.league_id,
                weather=ov.get("weather") or match.weather,
                temperature=ov.get("temperature") or match.temperature,
                pitch_condition=ov.get("pitch_condition") or match.pitch_condition,
                weights=weights,
                lambda_override=lambda_override,
                xg_lambda_override=xg_lambda_override,
                poisson_home_advantage=poisson_ha,
                simulations=simulations,
                seed=seed,
                detailed_mc=False,
            )
        except Exception as e:
            errors += 1
            logger.debug("backtest skip %s: %s", match.id, e)
            continue

        ens = result.get("ensemble_probs") or {}
        h = float(ens.get("home_win_prob") or result.get("home_win_prob") or 0)
        d = float(ens.get("draw_prob") or result.get("draw_prob") or 0)
        a = float(ens.get("away_win_prob") or result.get("away_win_prob") or 0)
        s = h + d + a
        if s <= 0:
            continue
        probs = (h / s, d / s, a / s)
        y = _one_hot(actual)
        brier_sum += sum((probs[i] - y[i]) ** 2 for i in range(3)) / 3.0
        pred_label = predict_label(probs)
        hit = pred_label == actual
        total += 1
        correct += int(hit)
        if len(samples) < 12:
            samples.append({
                "match_id": match.id,
                "match_date": str(match.match_date),
                "league_id": match.league_id,
                "home_team_id": match.home_team_id,
                "away_team_id": match.away_team_id,
                "actual": actual,
                "predicted": pred_label,
                "hit": hit,
                "probs": {
                    "home": round(probs[0], 4),
                    "draw": round(probs[1], 4),
                    "away": round(probs[2], 4),
                },
            })

    return {
        "period_days": days,
        "league_id": league_id,
        "requested": len(matches),
        "evaluated": total,
        "errors": errors,
        "simulations": simulations,
        "hit_rate": round(correct / total, 4) if total else None,
        "brier": round(brier_sum / total, 4) if total else None,
        "overrides": ov,
        "samples": samples,
        "disclaimer": "仅用于参数校准与学习研究，不构成投注建议。",
    }
