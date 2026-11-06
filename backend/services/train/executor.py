"""训练执行层：样本筛选、ELO/泊松/xG 训练、参数落库、融合网格搜索。

由 training_service.TrainingService 门面委托；保持行为不变。
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import Match, MatchPlayerStat, Team
from services.train.hyperparam import (
    grid_search_weights,
    precompute_components,
    validation_slice,
)
from services.train.smoothing import blend_weights, soft_blend_beta, smooth_weights

logger = logging.getLogger(__name__)


def soft_league_sample_floor() -> int:
    """与融合 soft_league_samples 对齐：低于此场次的非重点联赛不入训练。"""
    try:
        from services.ensemble_registry import get_ensemble
        ensemble = get_ensemble()
        soft = getattr(ensemble, "soft_league_samples", 20) or 20
    except Exception:
        soft = 20
    return max(1, int(soft))

def priority_league_ids() -> set:
    try:
        from services.real_team_crawler import get_priority_leagues
        return set(get_priority_leagues()) | {"WC"}
    except Exception:
        return {"EPL", "LALIGA", "BUNDES", "SERIEA", "LIGUE1", "UCL", "UEL", "WC"}

def eligible_training_league_ids(db: Session) -> set:
    """
    训练联赛白名单：
    - 重点联赛（五大+欧冠+世界杯）始终保留
    - 其余联赛完赛（含比分）≥ soft_league_samples 才纳入
    - 未分类（league_id 为空）永远排除
    """
    priority = priority_league_ids()
    soft = soft_league_sample_floor()
    rows = (
        db.query(Match.league_id, func.count(Match.id))
        .filter(
            Match.status == "finished",
            Match.league_id.isnot(None),
            Match.home_goals.isnot(None),
            Match.away_goals.isnot(None),
        )
        .group_by(Match.league_id)
        .all()
    )
    allowed = set(priority)
    for lid, n in rows:
        if lid and int(n) >= soft:
            allowed.add(str(lid))
    return allowed

def get_training_data(db: Session, start_date: date = None, end_date: date = None) -> list:
    allowed = eligible_training_league_ids(db)
    if not allowed:
        logger.warning("训练白名单为空，未加载任何完赛样本")
        return []
    query = db.query(Match).filter(
        Match.status == "finished",
        Match.league_id.isnot(None),
        Match.home_goals.isnot(None),
        Match.away_goals.isnot(None),
        Match.league_id.in_(list(allowed)),
    )
    if start_date:
        query = query.filter(Match.match_date >= start_date)
    if end_date:
        query = query.filter(Match.match_date <= end_date)
    matches = query.order_by(Match.match_date, Match.match_time).all()
    logger.info(
        "训练样本过滤：白名单联赛 %s 个，加载完赛 %s 场",
        len(allowed),
        len(matches),
    )
    return matches

def train_elo_model(db: Session, matches: list) -> dict:
    """时序训练 ELO，并搜索全局/分联赛 K 与主场加成。"""
    from services.ensemble_registry import get_ensemble
    ensemble = get_ensemble()

    options_k = list(getattr(ensemble, "hyperparam_options", {}).get("elo_k") or [20, 24, 28, 32, 36, 40])
    options_ha = list(
        getattr(ensemble, "hyperparam_options", {}).get("elo_home_advantage")
        or [50, 75, 100, 125, 150]
    )
    min_league = getattr(ensemble, "min_league_samples", 40) or 40
    soft_league = getattr(ensemble, "soft_league_samples", 20) or 20
    soft_league = max(1, min(int(soft_league), int(min_league)))

    by_league = {}
    for m in matches:
        by_league.setdefault(m.league_id or "UNKNOWN", []).append(m)

    global_val = []
    for lid, lm in by_league.items():
        global_val.extend(validation_slice(lm))
    if len(global_val) < 5:
        global_val = matches[-min(40, max(5, len(matches) // 5)):]
    if len(global_val) > 120:
        from services.real_team_crawler import get_priority_leagues
        priority_set = set(get_priority_leagues()) | {"WC"}
        preferred = [m for m in global_val if (m.league_id or "") in priority_set]
        others = [m for m in global_val if (m.league_id or "") not in priority_set]
        global_val = (preferred + others)[:120]

    # —— 全局 K / 主场加成 ——
    best_global = {
        "elo_k": float(ensemble.elo.k),
        "elo_home_advantage": float(ensemble.elo.home_advantage),
    }
    best_global_acc = -1.0
    best_ratings = None
    for k in options_k:
        for ha in options_ha:
            ratings = simulate_elo_ratings(
                matches, ensemble, {}, {}, default_k=k, default_ha=ha
            )
            acc = score_elo_predictions(
                global_val, ratings, ensemble, {}, default_ha=ha
            )
            if acc > best_global_acc:
                best_global_acc = acc
                best_global = {"elo_k": float(k), "elo_home_advantage": float(ha)}
                best_ratings = ratings

    # —— 分联赛坐标下降：逐联赛搜 K/主场 ——
    k_map = {}
    ha_map = {}
    league_hp_meta = {}
    for lid, lm in by_league.items():
        sample_n = len(lm)
        soft_mode = soft_league <= sample_n < min_league
        min_val = 5 if soft_mode else 8
        if sample_n < soft_league:
            league_hp_meta[lid] = {
                "elo_k": best_global["elo_k"],
                "elo_home_advantage": best_global["elo_home_advantage"],
                "source": "global_fallback",
                "train_matches": sample_n,
                "validation_accuracy": None,
                "blend_beta": None,
            }
            continue
        val_slice = validation_slice(lm)
        if len(val_slice) < min_val:
            league_hp_meta[lid] = {
                "elo_k": best_global["elo_k"],
                "elo_home_advantage": best_global["elo_home_advantage"],
                "source": "global_fallback",
                "train_matches": sample_n,
                "validation_accuracy": None,
                "blend_beta": None,
            }
            continue

        baseline_ratings = simulate_elo_ratings(
            matches, ensemble, k_map, ha_map,
            default_k=best_global["elo_k"], default_ha=best_global["elo_home_advantage"],
        )
        baseline_acc = score_elo_predictions(
            val_slice, baseline_ratings, ensemble, ha_map,
            default_ha=best_global["elo_home_advantage"],
        )
        best_k = best_global["elo_k"]
        best_ha = best_global["elo_home_advantage"]
        best_acc = baseline_acc
        for k in options_k:
            for ha in options_ha:
                trial_k = {**k_map, lid: float(k)}
                trial_ha = {**ha_map, lid: float(ha)}
                ratings = simulate_elo_ratings(
                    matches, ensemble, trial_k, trial_ha,
                    default_k=best_global["elo_k"],
                    default_ha=best_global["elo_home_advantage"],
                )
                acc = score_elo_predictions(
                    val_slice, ratings, ensemble, trial_ha,
                    default_ha=best_global["elo_home_advantage"],
                )
                if acc > best_acc + 0.005:
                    best_acc = acc
                    best_k = float(k)
                    best_ha = float(ha)

        blend_beta = None
        if best_k != best_global["elo_k"] or best_ha != best_global["elo_home_advantage"]:
            if best_acc + 0.01 < baseline_acc:
                source = "global_better"
                best_k = best_global["elo_k"]
                best_ha = best_global["elo_home_advantage"]
                best_acc = baseline_acc
            else:
                source = "league"
                if soft_mode:
                    blend_beta = soft_blend_beta(ensemble, sample_n)
                    best_k = blend_beta * best_k + (1.0 - blend_beta) * best_global["elo_k"]
                    best_ha = blend_beta * best_ha + (1.0 - blend_beta) * best_global["elo_home_advantage"]
                    source = "league_blended"
                k_map[lid] = best_k
                ha_map[lid] = best_ha
        else:
            source = "global_better" if best_acc >= 0 else "global_fallback"

        league_hp_meta[lid] = {
            "elo_k": best_k,
            "elo_home_advantage": best_ha,
            "source": source,
            "train_matches": sample_n,
            "validation_matches": len(val_slice),
            "validation_accuracy": round(best_acc, 4),
            "blend_beta": round(float(blend_beta), 4) if blend_beta is not None else None,
        }

    # 最终以搜到的超参重放一遍评级
    final_ratings = simulate_elo_ratings(
        matches, ensemble, k_map, ha_map,
        default_k=best_global["elo_k"],
        default_ha=best_global["elo_home_advantage"],
    )
    ensemble.elo.ratings = final_ratings
    poisson_ha = float(getattr(ensemble, "home_advantage", 1.15) or 1.15)
    ensemble.set_global_hyperparams({
        **best_global,
        "poisson_home_advantage": poisson_ha,
    })
    # 先写入 ELO 相关分联赛超参；泊松主场在融合阶段补全
    league_hp = {}
    for lid, meta in league_hp_meta.items():
        league_hp[lid] = {
            "elo_k": meta["elo_k"],
            "elo_home_advantage": meta["elo_home_advantage"],
            "poisson_home_advantage": poisson_ha,
        }
    ensemble.set_league_hyperparams(league_hp)

    top_id = max(final_ratings, key=final_ratings.get) if final_ratings else None
    top_team = db.query(Team).filter(Team.id == top_id).first() if top_id else None
    return {
        "status": "success",
        "trained_teams": len(final_ratings),
        "avg_rating": round(sum(final_ratings.values()) / len(final_ratings), 1) if final_ratings else 0,
        "top_team_id": top_id,
        "top_team": top_team.name if top_team else top_id,
        "top_rating": round(final_ratings[top_id], 1) if top_id else 0,
        "global_hyperparams": {
            **best_global,
            "poisson_home_advantage": poisson_ha,
        },
        "global_elo_validation_accuracy": round(max(0.0, best_global_acc), 4),
        "by_league_hyperparams": league_hp_meta,
        "leagues_optimized": sum(1 for m in league_hp_meta.values() if m.get("source") == "league"),
    }

def simulate_elo_ratings(matches: list,
    ensemble,
    k_by_league: dict,
    ha_by_league: dict,
    default_k: float = 32,
    default_ha: float = 100,
) -> dict:
    """按时间序重放 ELO；k/ha 可按联赛覆盖。"""
    ratings = {}
    for match in matches:
        home_team = match.home_team_id
        away_team = match.away_team_id
        if not home_team or not away_team:
            continue
        if home_team not in ratings:
            ratings[home_team] = float(ensemble.elo.get_rating(home_team))
        if away_team not in ratings:
            ratings[away_team] = float(ensemble.elo.get_rating(away_team))
        lid = match.league_id or "UNKNOWN"
        k = float(k_by_league.get(lid, default_k))
        ha = float(ha_by_league.get(lid, default_ha))
        ensemble.elo.update_match(
            ratings,
            home_team,
            away_team,
            int(match.home_goals or 0),
            int(match.away_goals or 0),
            k_factor=k,
            home_advantage=ha,
        )
    return ratings

def score_elo_predictions(matches: list,
    ratings: dict,
    ensemble,
    ha_by_league: dict,
    default_ha: float = 100,
) -> float:
    if not matches:
        return 0.0
    correct = 0
    n = 0
    for match in matches:
        hg = match.home_goals
        ag = match.away_goals
        if hg is None or ag is None:
            continue
        home_id = match.home_team_id
        away_id = match.away_team_id
        if home_id not in ratings or away_id not in ratings:
            continue
        lid = match.league_id or "UNKNOWN"
        ha = float(ha_by_league.get(lid, default_ha))
        probs = ensemble.elo.predict_prob(
            home_id, away_id,
            rating_a=ratings[home_id],
            rating_b=ratings[away_id],
            home_advantage=ha,
        )
        h, d, a = probs["home_win_prob"], probs["draw_prob"], probs["away_win_prob"]
        pred = "home" if h >= d and h >= a else ("away" if a >= d else "draw")
        actual = "home" if hg > ag else ("away" if hg < ag else "draw")
        if pred == actual:
            correct += 1
        n += 1
    return (correct / n) if n else 0.0

def train_poisson_model(db: Session, matches: list) -> dict:
    from services.ensemble_registry import get_ensemble
    ensemble = get_ensemble()
    from services.eval_metrics import decay_weight

    td = getattr(ensemble, "time_decay", {}) or {}
    decay_on = bool(td.get("enabled", True))
    half_life = float(td.get("half_life_days", 180) or 180)
    ref_date = matches[-1].match_date if matches else date.today()

    team_stats = {}
    league_matches = {}

    for match in matches:
        home_team = match.home_team_id
        away_team = match.away_team_id
        home_goals = match.home_goals or 0
        away_goals = match.away_goals or 0
        league_id = match.league_id
        w = decay_weight(
            match.match_date,
            ref_date=ref_date,
            half_life_days=half_life,
            enabled=decay_on,
        )

        if league_id not in league_matches:
            league_matches[league_id] = {"total_matches": 0.0, "total_goals": 0.0}
        league_matches[league_id]["total_matches"] += w
        league_matches[league_id]["total_goals"] += w * (home_goals + away_goals)

        for team_id, goals_scored, goals_conceded, is_home in [
            (home_team, home_goals, away_goals, True),
            (away_team, away_goals, home_goals, False),
        ]:
            if team_id not in team_stats:
                team_stats[team_id] = {
                    "home_matches": 0.0, "away_matches": 0.0,
                    "home_goals": 0.0, "away_goals": 0.0,
                    "home_conceded": 0.0, "away_conceded": 0.0,
                    "league": league_id,
                }
            if is_home:
                team_stats[team_id]["home_matches"] += w
                team_stats[team_id]["home_goals"] += w * goals_scored
                team_stats[team_id]["home_conceded"] += w * goals_conceded
            else:
                team_stats[team_id]["away_matches"] += w
                team_stats[team_id]["away_goals"] += w * goals_scored
                team_stats[team_id]["away_conceded"] += w * goals_conceded

    league_avg = {}
    for league_id, stats in league_matches.items():
        key = league_id or "UNKNOWN"
        league_avg[key] = stats["total_goals"] / stats["total_matches"] if stats["total_matches"] else 2.7

    new_team_params = {}
    for team_id, stats in team_stats.items():
        league_id = stats["league"]
        avg_goals = league_avg.get(league_id or "UNKNOWN", 2.7) or 2.7
        # 联赛场次全 0-0 时 avg_goals=0，避免后续除零
        if avg_goals <= 0:
            avg_goals = 2.7
        half_avg = avg_goals / 2
        home_attack = away_attack = home_defense = away_defense = 1.0
        if stats["home_matches"] > 0:
            home_attack = (stats["home_goals"] / stats["home_matches"]) / half_avg
            home_defense = (stats["home_conceded"] / stats["home_matches"]) / half_avg
        if stats["away_matches"] > 0:
            away_attack = (stats["away_goals"] / stats["away_matches"]) / half_avg
            away_defense = (stats["away_conceded"] / stats["away_matches"]) / half_avg
        attack = max(0.5, min(2.0, (home_attack + away_attack) / 2))
        defense = max(0.5, min(2.0, (home_defense + away_defense) / 2))
        new_team_params[team_id] = {
            "attack": round(attack, 2),
            "defense": round(defense, 2),
            "league": league_id,
        }

    ensemble.team_params = new_team_params
    ensemble.league_avg = league_avg
    return {
        "status": "success",
        "trained_teams": len(new_team_params),
        "leagues": len(league_avg),
        "league_avg": {str(k): round(v, 3) for k, v in league_avg.items()},
        "avg_attack": round(sum(p["attack"] for p in new_team_params.values()) / len(new_team_params), 2) if new_team_params else 0,
        "avg_defense": round(sum(p["defense"] for p in new_team_params.values()) / len(new_team_params), 2) if new_team_params else 0,
        "time_decay": {"enabled": decay_on, "half_life_days": half_life},
    }

def train_xg_model(db: Session, matches: list) -> dict:
    """从 match_player_stats 射门/射正估计球队 xG 攻防参数。"""
    from services.ensemble_registry import get_ensemble
    ensemble = get_ensemble()
    from models.xg_model import XGModel

    if not matches:
        return {"status": "success", "trained_teams": 0, "matches_with_stats": 0}

    match_by_id = {m.id: m for m in matches}
    match_ids = list(match_by_id.keys())

    # 分批查询，避免 IN 过长
    rows = []
    batch = 500
    for i in range(0, len(match_ids), batch):
        chunk = match_ids[i:i + batch]
        rows.extend(
            db.query(MatchPlayerStat)
            .filter(MatchPlayerStat.match_id.in_(chunk))
            .all()
        )

    per_match_team = {}
    for r in rows:
        m = match_by_id.get(r.match_id)
        if not m:
            continue
        tid = r.team_id
        if not tid:
            tid = m.home_team_id if r.is_home else m.away_team_id
        if not tid:
            continue
        key = (r.match_id, str(tid))
        bucket = per_match_team.setdefault(key, {
            "shots": 0, "sot": 0, "goals_stat": 0, "is_home": bool(r.is_home),
        })
        bucket["shots"] += int(r.shots or 0)
        bucket["sot"] += int(r.shots_on_target or 0)
        bucket["goals_stat"] += int(r.goals or 0)

    # P2：球员行缺失时用 match_team_stats 补球队射门
    try:
        from db.models import MatchTeamStat
        team_rows = []
        for i in range(0, len(match_ids), batch):
            chunk = match_ids[i:i + batch]
            team_rows.extend(
                db.query(MatchTeamStat)
                .filter(MatchTeamStat.match_id.in_(chunk))
                .all()
            )
        for r in team_rows:
            key = (r.match_id, str(r.team_id))
            if key in per_match_team:
                continue
            per_match_team[key] = {
                "shots": int(r.shots or 0),
                "sot": int(r.shots_on_target or 0),
                "goals_stat": 0,
                "is_home": bool(r.is_home),
            }
    except Exception as e:
        logger.debug("merge match_team_stats for xG skipped: %s", e)

    if not per_match_team:
        return {
            "status": "success",
            "trained_teams": 0,
            "matches_with_stats": 0,
            "message": "无 match_player_stats / match_team_stats，跳过 xG",
        }

    # 联赛转化率先验
    league_tot = {}
    for (mid, tid), s in per_match_team.items():
        m = match_by_id.get(mid)
        if not m:
            continue
        lid = m.league_id or "UNKNOWN"
        tot = league_tot.setdefault(lid, {"shots": 0, "sot": 0, "goals": 0, "matches": set()})
        tot["shots"] += s["shots"]
        tot["sot"] += s["sot"]
        if tid == m.home_team_id:
            tot["goals"] += int(m.home_goals or 0)
        elif tid == m.away_team_id:
            tot["goals"] += int(m.away_goals or 0)
        tot["matches"].add(mid)

    prior_shot = float(ensemble.xg.prior_xg_per_shot)
    prior_sot = float(ensemble.xg.prior_xg_per_sot)
    league_priors = {}
    for lid, tot in league_tot.items():
        n_m = len(tot["matches"]) or 1
        xps = (tot["goals"] / tot["shots"]) if tot["shots"] > 0 else prior_shot
        xpso = (tot["goals"] / tot["sot"]) if tot["sot"] > 0 else prior_sot
        # 夹紧到合理区间，避免极端脏数据
        xps = max(0.05, min(0.25, float(xps)))
        xpso = max(0.15, min(0.55, float(xpso)))
        xg_for_avg = max(0.6, min(2.5, (
            0.4 * (tot["shots"] / n_m) * xps + 0.6 * (tot["sot"] / n_m) * xpso
        )))
        prior = {
            "xg_per_shot": round(xps, 4),
            "xg_per_sot": round(xpso, 4),
            "xg_for_avg": round(xg_for_avg, 3),
            "shots_pg": round(tot["shots"] / n_m, 2),
            "sot_pg": round(tot["sot"] / n_m, 2),
            "matches": n_m,
        }
        league_priors[lid] = prior
        ensemble.xg.set_league_prior(lid, prior)

    # 球队逐场 xG for / against
    team_agg = {}
    matches_with_stats = set()
    for m in matches:
        home_s = per_match_team.get((m.id, str(m.home_team_id)))
        away_s = per_match_team.get((m.id, str(m.away_team_id)))
        if not home_s and not away_s:
            continue
        matches_with_stats.add(m.id)
        lid = m.league_id or "UNKNOWN"
        prior = league_priors.get(lid, {})
        xps = float(prior.get("xg_per_shot", prior_shot))
        xpso = float(prior.get("xg_per_sot", prior_sot))

        home_xg = XGModel.match_team_xg_from_shots(
            home_s["shots"], home_s["sot"], xps, xpso
        ) if home_s else None
        away_xg = XGModel.match_team_xg_from_shots(
            away_s["shots"], away_s["sot"], xps, xpso
        ) if away_s else None

        def _ensure(tid, league):
            return team_agg.setdefault(tid, {
                "xg_for": [], "xg_against": [],
                "shots": 0, "sot": 0, "matches": 0, "league": league,
            })

        if home_xg is not None:
            th = _ensure(str(m.home_team_id), lid)
            th["xg_for"].append(home_xg)
            th["shots"] += home_s["shots"]
            th["sot"] += home_s["sot"]
            th["matches"] += 1
            if away_xg is not None:
                th["xg_against"].append(away_xg)
        if away_xg is not None:
            ta = _ensure(str(m.away_team_id), lid)
            ta["xg_for"].append(away_xg)
            ta["shots"] += away_s["shots"]
            ta["sot"] += away_s["sot"]
            ta["matches"] += 1
            if home_xg is not None:
                ta["xg_against"].append(home_xg)

    trained = 0
    xg_params = {}
    for tid, agg in team_agg.items():
        n = int(agg["matches"] or 0)
        if n < 1:
            continue
        xg_for = sum(agg["xg_for"]) / len(agg["xg_for"]) if agg["xg_for"] else 1.35
        if agg["xg_against"]:
            xg_against = sum(agg["xg_against"]) / len(agg["xg_against"])
        else:
            lid = agg["league"]
            xg_against = float(league_priors.get(lid, {}).get("xg_for_avg", 1.35))
        params = {
            "xg_for": round(max(0.4, min(3.5, xg_for)), 3),
            "xg_against": round(max(0.4, min(3.5, xg_against)), 3),
            "shots_pg": round(agg["shots"] / n, 2),
            "sot_pg": round(agg["sot"] / n, 2),
            "matches": n,
            "xg_matches": n,
            "league": agg["league"],
        }
        ensemble.xg.set_team(tid, params)
        xg_params[tid] = params
        # 合并进 team_params，供持久化与预测
        base = dict(ensemble.team_params.get(tid) or {})
        base.update(params)
        if "attack" not in base:
            base["attack"] = 1.0
        if "defense" not in base:
            base["defense"] = 1.0
        ensemble.team_params[tid] = base
        trained += 1

    avg_for = (
        sum(p["xg_for"] for p in xg_params.values()) / len(xg_params)
        if xg_params else 0
    )
    return {
        "status": "success",
        "trained_teams": trained,
        "matches_with_stats": len(matches_with_stats),
        "leagues": len(league_priors),
        "league_priors": league_priors,
        "avg_xg_for": round(avg_for, 3),
    }

def persist_trained_params(db: Session, results: dict) -> dict:
    """将 ELO / 攻防 / xG / 联赛场均进球回写数据库，供预测与重启后使用。"""
    from services.ensemble_registry import get_ensemble
    ensemble = get_ensemble()
    from db.models import League

    elo_n = 0
    for team_id, rating in (ensemble.elo.ratings or {}).items():
        team = db.query(Team).filter(Team.id == team_id).first()
        if not team:
            continue
        team.elo_rating = int(round(float(rating)))
        elo_n += 1

    strength_n = 0
    xg_n = 0
    for team_id, params in (ensemble.team_params or {}).items():
        team = db.query(Team).filter(Team.id == team_id).first()
        if not team:
            continue
        if params.get("attack") is not None:
            team.attack_strength = float(params["attack"])
        if params.get("defense") is not None:
            team.defense_strength = float(params["defense"])
        strength_n += 1
        if params.get("xg_for") is not None:
            team.xg_for = float(params["xg_for"])
            xg_n += 1
        if params.get("xg_against") is not None:
            team.xg_against = float(params["xg_against"])

    league_n = 0
    for league_id, avg in (ensemble.league_avg or {}).items():
        if not league_id or league_id == "UNKNOWN":
            continue
        league = db.query(League).filter(League.id == str(league_id)).first()
        if not league:
            continue
        league.avg_goals = round(float(avg), 2)
        league_n += 1

    db.commit()
    return {
        "status": "success",
        "elo_updated": elo_n,
        "strength_updated": strength_n,
        "xg_updated": xg_n,
        "league_avg_updated": league_n,
    }

def train_ensemble_model(db: Session, matches: list) -> dict:
    """全局 + 分联赛网格搜索融合权重，并搜索泊松主场优势。"""
    from services.ensemble_registry import get_ensemble
    ensemble = get_ensemble()

    if len(matches) < 10:
        return {
            "status": "success",
            "message": "数据不足，使用默认权重",
            "weights": ensemble.weights,
            "league_weights": {},
            "by_league": {},
            "validation_accuracy": 0,
            "validation_matches": 0,
        }

    min_league = getattr(ensemble, "min_league_samples", 40) or 40
    soft_league = getattr(ensemble, "soft_league_samples", 20) or 20
    soft_league = max(1, min(int(soft_league), int(min_league)))
    weight_options = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
    poisson_ha_options = list(
        getattr(ensemble, "hyperparam_options", {}).get("poisson_home_advantage")
        or [1.05, 1.10, 1.15, 1.20, 1.25]
    )

    # 训练前快照：用于 EMA，降低小样本联赛权重抖动
    prev_global_w = dict(ensemble.weights or {})
    prev_league_w = {
        str(lid): dict(w)
        for lid, w in (getattr(ensemble, "league_weights", {}) or {}).items()
        if isinstance(w, dict)
    }

    # 按联赛分组（保持时间序）
    by_league = {}
    for m in matches:
        lid = m.league_id or "UNKNOWN"
        by_league.setdefault(lid, []).append(m)

    # —— 全局权重：各联赛验证尾部拼成混合验证集 ——
    global_val = []
    for lid, lm in by_league.items():
        global_val.extend(validation_slice(lm))
    if len(global_val) < 5:
        global_val = matches[-min(40, max(5, len(matches) // 5)):]
    if len(global_val) > 150:
        from services.real_team_crawler import get_priority_leagues
        priority_set = set(get_priority_leagues()) | {"WC"}
        preferred = [m for m in global_val if (m.league_id or "") in priority_set]
        others = [m for m in global_val if (m.league_id or "") not in priority_set]
        global_val = (preferred + others)[:150]

    ghp = ensemble.get_hyperparams_for_league(None)
    best_global_hp = dict(ghp)
    best_global_acc = -1.0
    best_global_w = dict(ensemble.weights)
    best_global_cache_n = 0
    best_global_cache = []
    best_global_metrics = {"n": 0, "accuracy": -1.0, "brier": 9e9}
    from services.eval_metrics import is_better, score_cache as eval_score_cache

    for p_ha in poisson_ha_options:
        trial_hp = {
            **ghp,
            "poisson_home_advantage": float(p_ha),
        }
        cache = precompute_components(global_val, ensemble, hyperparams=trial_hp)
        if len(cache) < 5:
            continue
        w, acc, metrics = grid_search_weights(cache, weight_options, ensemble=ensemble)
        if is_better(metrics, best_global_metrics, primary=(getattr(ensemble, "evaluation", {}) or {}).get("primary_metric", "brier")):
            best_global_metrics = metrics
            best_global_acc = acc
            best_global_w = w
            best_global_hp = trial_hp
            best_global_cache_n = len(cache)
            best_global_cache = cache

    # 全局权重 EMA（按总样本自适应 α）
    raw_global_w = dict(best_global_w)
    best_global_w, global_alpha = smooth_weights(ensemble, best_global_w, prev_global_w, sample_n=len(matches),
    )
    if best_global_cache and abs(global_alpha - 1.0) > 1e-6:
        best_global_metrics = eval_score_cache(best_global_cache, best_global_w)
        best_global_acc = float(best_global_metrics.get("accuracy") or 0)

    ensemble.set_weights(best_global_w)
    ensemble.set_global_hyperparams(best_global_hp)

    # —— 分联赛权重 + 泊松主场 ——
    league_weight_map = {}
    league_hp_map = dict(getattr(ensemble, "league_hyperparams", {}) or {})
    league_meta = {}
    for lid, lm in by_league.items():
        sample_n = len(lm)
        base_hp = ensemble.get_hyperparams_for_league(lid)
        soft_mode = soft_league <= sample_n < min_league
        min_val = 5 if soft_mode else 8
        if sample_n < soft_league:
            league_meta[lid] = {
                "train_matches": sample_n,
                "sample_n": sample_n,
                "validation_matches": 0,
                "validation_accuracy": None,
                "source": "global_fallback",
                "hyper_source": "global_fallback",
                "smooth_alpha": None,
                "blend_beta": None,
                "weights": {k: round(v, 4) for k, v in best_global_w.items()},
                "hyperparams": {
                    "elo_k": round(float(base_hp["elo_k"]), 2),
                    "elo_home_advantage": round(float(base_hp["elo_home_advantage"]), 2),
                    "poisson_home_advantage": round(float(best_global_hp["poisson_home_advantage"]), 4),
                },
            }
            league_hp_map[lid] = league_meta[lid]["hyperparams"]
            continue

        val_slice = validation_slice(lm)
        if len(val_slice) < min_val:
            league_meta[lid] = {
                "train_matches": sample_n,
                "sample_n": sample_n,
                "validation_matches": len(val_slice),
                "validation_accuracy": None,
                "source": "global_fallback",
                "hyper_source": "global_fallback",
                "smooth_alpha": None,
                "blend_beta": None,
                "weights": {k: round(v, 4) for k, v in best_global_w.items()},
                "hyperparams": {
                    "elo_k": round(float(base_hp["elo_k"]), 2),
                    "elo_home_advantage": round(float(base_hp["elo_home_advantage"]), 2),
                    "poisson_home_advantage": round(float(best_global_hp["poisson_home_advantage"]), 4),
                },
            }
            league_hp_map[lid] = league_meta[lid]["hyperparams"]
            continue

        best_w = best_global_w
        best_acc = -1.0
        best_metrics = {"n": 0, "accuracy": -1.0, "brier": 9e9}
        best_hp = {
            **base_hp,
            "poisson_home_advantage": best_global_hp["poisson_home_advantage"],
        }
        best_cache_n = 0
        best_cache = []
        global_cache = precompute_components(
            val_slice, ensemble, hyperparams=best_global_hp
        )
        global_metrics = eval_score_cache(global_cache, best_global_w) if global_cache else {"n": 0, "accuracy": 0.0, "brier": 1.0}
        global_on_league = float(global_metrics.get("accuracy") or 0)
        primary = (getattr(ensemble, "evaluation", {}) or {}).get("primary_metric", "brier")
        for p_ha in poisson_ha_options:
            trial_hp = {**base_hp, "poisson_home_advantage": float(p_ha)}
            cache = precompute_components(val_slice, ensemble, hyperparams=trial_hp)
            if len(cache) < min_val:
                continue
            w, acc, metrics = grid_search_weights(cache, weight_options, ensemble=ensemble)
            if is_better(metrics, best_metrics, primary=primary):
                best_metrics = metrics
                best_acc = acc
                best_w = w
                best_hp = trial_hp
                best_cache_n = len(cache)
                best_cache = cache

        if best_acc < 0:
            best_acc = global_on_league
            best_metrics = global_metrics
            best_w = best_global_w
            best_hp = {
                **base_hp,
                "poisson_home_advantage": best_global_hp["poisson_home_advantage"],
            }
            best_cache_n = len(global_cache)
            best_cache = global_cache

        # 与全局对比：主指标优先；Brier 越低越好
        league_worse_than_global = False
        if primary == "accuracy":
            league_worse_than_global = best_acc + 0.01 < global_on_league
        else:
            league_worse_than_global = float(best_metrics.get(primary) or 9) > float(global_metrics.get(primary) or 9) + 0.005

        if league_worse_than_global:
            chosen_w, acc, source = best_global_w, global_on_league, "global_better"
            chosen_metrics = global_metrics
            chosen_hp = {
                **base_hp,
                "poisson_home_advantage": best_global_hp["poisson_home_advantage"],
            }
            hyper_source = "global_better"
            score_cache = global_cache
            blend_beta = None
        else:
            chosen_w, acc, source = best_w, best_acc, "league"
            chosen_metrics = best_metrics
            chosen_hp = best_hp
            score_cache = best_cache if best_cache else global_cache
            hyper_source = (
                "league"
                if abs(float(chosen_hp["poisson_home_advantage"]) - float(best_global_hp["poisson_home_advantage"])) > 1e-6
                or abs(float(chosen_hp["elo_k"]) - float(best_global_hp["elo_k"])) > 1e-6
                or abs(float(chosen_hp["elo_home_advantage"]) - float(best_global_hp["elo_home_advantage"])) > 1e-6
                else "global_better"
            )
            blend_beta = None
            # 小样本：联赛网格结果向全局收缩，减轻过拟合
            if soft_mode and source == "league":
                blend_beta = soft_blend_beta(ensemble, sample_n)
                chosen_w = blend_weights(ensemble, chosen_w, best_global_w, blend_beta)
                source = "league_blended"
                if score_cache:
                    chosen_metrics = eval_score_cache(score_cache, chosen_w)
                    acc = float(chosen_metrics.get("accuracy") or 0)
                # 超参同步软混合（泊松主场）
                if hyper_source == "league":
                    g_ha = float(best_global_hp["poisson_home_advantage"])
                    l_ha = float(chosen_hp["poisson_home_advantage"])
                    chosen_hp = {
                        **chosen_hp,
                        "poisson_home_advantage": blend_beta * l_ha + (1.0 - blend_beta) * g_ha,
                    }
                    hyper_source = "league_blended"

        # 分联赛权重 EMA：无历史联赛权重时向旧全局靠拢
        prev_w = prev_league_w.get(str(lid)) or prev_global_w
        chosen_w, smooth_alpha = smooth_weights(ensemble, chosen_w, prev_w, sample_n=sample_n,
        )
        if score_cache and abs(smooth_alpha - 1.0) > 1e-6:
            chosen_metrics = eval_score_cache(score_cache, chosen_w)
            acc = float(chosen_metrics.get("accuracy") or 0)

        league_weight_map[lid] = chosen_w
        league_hp_map[lid] = {
            "elo_k": round(float(chosen_hp["elo_k"]), 2),
            "elo_home_advantage": round(float(chosen_hp["elo_home_advantage"]), 2),
            "poisson_home_advantage": round(float(chosen_hp["poisson_home_advantage"]), 4),
        }
        league_meta[lid] = {
            "train_matches": sample_n,
            "sample_n": sample_n,
            "validation_matches": best_cache_n or len(global_cache),
            "validation_accuracy": round(acc, 4),
            "validation_brier": round(float(chosen_metrics.get("brier") or 0), 4) if chosen_metrics else None,
            "validation_log_loss": round(float(chosen_metrics.get("log_loss") or 0), 4) if chosen_metrics else None,
            "validation_ece": round(float(chosen_metrics.get("ece") or 0), 4) if chosen_metrics else None,
            "source": source,
            "hyper_source": hyper_source,
            "smooth_alpha": round(float(smooth_alpha), 4),
            "blend_beta": round(float(blend_beta), 4) if blend_beta is not None else None,
            "weights": {k: round(v, 4) for k, v in chosen_w.items()},
            "hyperparams": league_hp_map[lid],
        }

    ensemble.set_league_weights(league_weight_map)
    ensemble.set_league_hyperparams(league_hp_map)

    total_correct = 0.0
    total_n = 0
    for lid, meta in league_meta.items():
        if meta.get("validation_accuracy") is not None and meta.get("validation_matches"):
            total_correct += meta["validation_accuracy"] * meta["validation_matches"]
            total_n += meta["validation_matches"]
    if total_n == 0:
        total_n = best_global_cache_n
        total_correct = best_global_acc * total_n
    overall_acc = (total_correct / total_n) if total_n else 0.0

    sm_cfg = getattr(ensemble, "weight_smoothing", {}) or {}
    payload = ensemble.export_weights_payload(league_meta)
    return {
        "status": "success",
        "weights": {k: round(v, 4) for k, v in ensemble.weights.items()},
        "weights_raw_global": {k: round(v, 4) for k, v in raw_global_w.items()},
        "smooth_alpha_global": round(float(global_alpha), 4),
        "hyperparams": {
            "elo_k": round(float(best_global_hp["elo_k"]), 2),
            "elo_home_advantage": round(float(best_global_hp["elo_home_advantage"]), 2),
            "poisson_home_advantage": round(float(best_global_hp["poisson_home_advantage"]), 4),
        },
        "league_weights": {
            lid: meta["weights"] for lid, meta in league_meta.items()
            if meta.get("source") in ("league", "global_better", "league_blended")
        },
        "by_league": league_meta,
        "weights_payload": payload,
        "validation_accuracy": round(overall_acc, 4),
        "validation_matches": total_n,
        "global_validation_accuracy": round(max(0.0, best_global_acc), 4),
        "global_validation_matches": best_global_cache_n,
        "evaluation": {
            "primary_metric": (getattr(ensemble, "evaluation", {}) or {}).get("primary_metric", "brier"),
            "walk_forward_folds": int((getattr(ensemble, "evaluation", {}) or {}).get("walk_forward_folds") or 3),
            "global_brier": round(float(best_global_metrics.get("brier") or 0), 4),
            "global_log_loss": round(float(best_global_metrics.get("log_loss") or 0), 4),
            "global_ece": round(float(best_global_metrics.get("ece") or 0), 4),
            "global_folds": int(best_global_metrics.get("folds") or 1),
        },
        "time_decay": dict(getattr(ensemble, "time_decay", {}) or {}),
        "max_monte_carlo_weight": float(getattr(ensemble, "max_monte_carlo_weight", 0.28) or 0.28),
        "leagues_optimized": sum(1 for m in league_meta.values() if m.get("source") == "league"),
        "leagues_blended": sum(1 for m in league_meta.values() if m.get("source") == "league_blended"),
        "leagues_fallback": sum(1 for m in league_meta.values() if m.get("source") == "global_fallback"),
        "leagues_hyper_optimized": sum(
            1 for m in league_meta.values() if m.get("hyper_source") == "league"
        ),
        "min_league_samples": min_league,
        "soft_league_samples": soft_league,
        "weight_smoothing": {
            "enabled": bool(sm_cfg.get("enabled", True)),
            "prior_strength": sm_cfg.get("prior_strength"),
            "min_alpha": sm_cfg.get("min_alpha"),
            "max_alpha": sm_cfg.get("max_alpha"),
            "global_alpha": round(float(global_alpha), 4),
        },
    }

