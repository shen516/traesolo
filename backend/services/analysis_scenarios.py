"""预测分析场景：单模型 / 整合版定义与自动选择。

主结论按数据完备度自动选场景；详情页可切换浏览各场景胜平负。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# 场景 ID（稳定契约，前后端共用）
SCENARIO_ENSEMBLE = "ensemble"
SCENARIO_ELO = "elo"
SCENARIO_POISSON = "poisson"
SCENARIO_XG = "xg"
SCENARIO_MONTE_CARLO = "monte_carlo"

SCENARIO_ORDER = (
    SCENARIO_ENSEMBLE,
    SCENARIO_ELO,
    SCENARIO_POISSON,
    SCENARIO_XG,
    SCENARIO_MONTE_CARLO,
)

SCENARIO_META = {
    SCENARIO_ENSEMBLE: {
        "label": "整合版",
        "short": "融合",
        "desc": "ELO + 泊松 + xG + 蒙特卡洛加权，数据较全时的旗舰结论",
    },
    SCENARIO_ELO: {
        "label": "实力对比（ELO）",
        "short": "ELO",
        "desc": "仅用相对实力差；适合缺射门统计、只需强弱倾向的联赛",
    },
    SCENARIO_POISSON: {
        "label": "进球分布（泊松）",
        "short": "泊松",
        "desc": "攻防强度与联赛场均 → λ 与比分矩阵；缺 xG 时的主路径",
    },
    SCENARIO_XG: {
        "label": "过程质量（xG）",
        "short": "xG",
        "desc": "射门/射正估计期望进球；需 ESPN 等逐场统计覆盖",
    },
    SCENARIO_MONTE_CARLO: {
        "label": "波动模拟（蒙特卡洛）",
        "short": "MC",
        "desc": "对 λ 做随机模拟；依赖泊松/xG 的期望进球，非独立数据源",
    },
}

# 单场景权重（归一化前）；整合版权重由 ensemble 运行时权重填入
SCENARIO_WEIGHTS = {
    SCENARIO_ELO: {"elo": 1.0, "poisson": 0.0, "xg": 0.0, "monte_carlo": 0.0},
    SCENARIO_POISSON: {"elo": 0.0, "poisson": 1.0, "xg": 0.0, "monte_carlo": 0.0},
    SCENARIO_XG: {"elo": 0.0, "poisson": 0.0, "xg": 1.0, "monte_carlo": 0.0},
    SCENARIO_MONTE_CARLO: {"elo": 0.0, "poisson": 0.0, "xg": 0.0, "monte_carlo": 1.0},
}

# xG 覆盖达到此值才把整合版 / xG 场景视为「可用主结论」
XG_COVERAGE_FULL = 0.5
XG_COVERAGE_PARTIAL = 0.01


def scenario_label(scenario_id: str) -> str:
    return (SCENARIO_META.get(scenario_id) or {}).get("label") or scenario_id


def has_espn_pipeline(league_id: Optional[str]) -> bool:
    if not league_id:
        return False
    try:
        from services.real_team_crawler import ESPN_LEAGUE_MAP
        return str(league_id).upper() in ESPN_LEAGUE_MAP
    except Exception:
        return False


def is_priority_league(league_id: Optional[str]) -> bool:
    if not league_id:
        return False
    try:
        from services.real_team_crawler import get_priority_leagues
        return str(league_id).upper() in get_priority_leagues()
    except Exception:
        return False


def league_data_policy(league_id: Optional[str]) -> Dict[str, Any]:
    """联赛数据策略标记（P3：纯 500 → poisson-only 产品形态）。"""
    lid = str(league_id or "").upper()
    tier = "unknown"
    try:
        from services.real_team_crawler import league_pipeline_tier
        tier = league_pipeline_tier(lid) if lid else "unknown"
    except Exception:
        pass
    five00_only = tier == "five00_only" or (lid.startswith("LS") and tier != "dual_mapped")
    return {
        "pipeline_tier": tier,
        "five00_only": five00_only,
        "poisson_primary_policy": five00_only or tier == "espn_only",
        "xg_priority": tier in ("core", "extended", "dual_mapped"),
    }


def select_primary_scenario(
    league_id: Optional[str],
    xg_coverage: float,
    *,
    espn_pipeline: Optional[bool] = None,
) -> Tuple[str, str]:
    """按数据完备度选本场主结论场景。

    返回 (scenario_id, reason_zh)。
    """
    cov = float(xg_coverage or 0)
    espn = has_espn_pipeline(league_id) if espn_pipeline is None else bool(espn_pipeline)
    lid = (league_id or "").upper() or "未知联赛"
    policy = league_data_policy(league_id)

    if policy.get("five00_only"):
        return (
            SCENARIO_POISSON,
            f"{lid} 为纯 500 联赛（无 ESPN 射门管线），主结论固定泊松；可对照 ELO，勿作 xG 重点",
        )

    if espn and cov >= XG_COVERAGE_FULL:
        return (
            SCENARIO_ENSEMBLE,
            f"{lid} 有 ESPN 统计管线且 xG 覆盖充足（{cov:.0%}），采用整合版",
        )
    if espn and cov >= XG_COVERAGE_PARTIAL:
        return (
            SCENARIO_ENSEMBLE,
            f"{lid} 有 ESPN 管线但 xG 覆盖有限（{cov:.0%}），仍用整合版（缺侧已降权）",
        )
    if espn and cov < XG_COVERAGE_PARTIAL:
        return (
            SCENARIO_POISSON,
            f"{lid} 有 ESPN 映射但本场/双方暂无有效 xG，主结论改用泊松进球分布",
        )
    # 未映射 / espn_only 等：无球员级射门 → 不用整合版与 xG
    return (
        SCENARIO_POISSON,
        f"{lid} 无 ESPN 深度统计管线，主结论用泊松；可对照 ELO 实力场景",
    )


def scenario_availability(xg_coverage: float, espn_pipeline: bool) -> Dict[str, bool]:
    """各场景是否建议作为有效分析（仍可计算数值供对照）。"""
    cov = float(xg_coverage or 0)
    xg_ok = espn_pipeline and cov >= XG_COVERAGE_PARTIAL
    return {
        SCENARIO_ENSEMBLE: espn_pipeline,  # 无 ESPN 时整合版意义弱（与泊松高度同质）
        SCENARIO_ELO: True,
        SCENARIO_POISSON: True,
        SCENARIO_XG: xg_ok,
        SCENARIO_MONTE_CARLO: True,  # 始终可基于 λ 模拟
    }


def blend_outcome(
    weights: Dict[str, float],
    poisson: Dict[str, Any],
    elo: Dict[str, Any],
    xg: Dict[str, Any],
    mc: Dict[str, Any],
) -> Dict[str, float]:
    """按权重混合胜平负并归一。"""
    w = weights or {}
    we = float(w.get("elo", 0) or 0)
    wp = float(w.get("poisson", 0) or 0)
    wx = float(w.get("xg", 0) or 0)
    wm = float(w.get("monte_carlo", 0) or 0)
    total_w = we + wp + wx + wm
    if total_w <= 0:
        we, wp, wx, wm, total_w = 0.0, 1.0, 0.0, 0.0, 1.0
    we, wp, wx, wm = we / total_w, wp / total_w, wx / total_w, wm / total_w

    h = (
        wp * float(poisson.get("home_win_prob") or 0)
        + we * float(elo.get("home_win_prob") or 0)
        + wx * float(xg.get("home_win_prob") or 0)
        + wm * float(mc.get("home_win_prob") or 0)
    )
    a = (
        wp * float(poisson.get("away_win_prob") or 0)
        + we * float(elo.get("away_win_prob") or 0)
        + wx * float(xg.get("away_win_prob") or 0)
        + wm * float(mc.get("away_win_prob") or 0)
    )
    d = (
        wp * float(poisson.get("draw_prob") or 0)
        + we * float(elo.get("draw_prob") or 0)
        + wx * float(xg.get("draw_prob") or 0)
        + wm * float(mc.get("draw_prob") or 0)
    )
    if d <= 0:
        d = max(0.01, 1.0 - h - a)
    s = h + a + d
    if s <= 0:
        return {"home_win_prob": 1 / 3, "draw_prob": 1 / 3, "away_win_prob": 1 / 3}
    return {
        "home_win_prob": h / s,
        "draw_prob": d / s,
        "away_win_prob": a / s,
    }


def build_scenarios_payload(
    *,
    league_id: Optional[str],
    xg_coverage: float,
    ensemble_weights: Dict[str, float],
    poisson: Dict[str, Any],
    elo: Dict[str, Any],
    xg: Dict[str, Any],
    mc: Dict[str, Any],
    poisson_main_score: Optional[str] = None,
    poisson_alt_scores: Optional[List] = None,
    xg_main_score: Optional[str] = None,
    mc_top_scores: Optional[List] = None,
    espn_pipeline: Optional[bool] = None,
) -> Dict[str, Any]:
    """构造写入 meta_json 的 scenarios 块。"""
    espn = has_espn_pipeline(league_id) if espn_pipeline is None else bool(espn_pipeline)
    policy = league_data_policy(league_id)
    avail = scenario_availability(xg_coverage, espn)
    if policy.get("five00_only"):
        # 纯 500：整合版/xG 仅作弱对照，不可作主结论
        avail = {**avail, SCENARIO_ENSEMBLE: False, SCENARIO_XG: False}
    primary, reason = select_primary_scenario(
        league_id, xg_coverage, espn_pipeline=espn
    )

    mc_main = None
    if mc_top_scores:
        first = mc_top_scores[0]
        if isinstance(first, (list, tuple)) and first:
            mc_main = str(first[0])
        elif isinstance(first, dict) and first.get("score"):
            mc_main = str(first["score"])

    def pack(sid: str, weights: Dict[str, float], outcome: Dict[str, float], **extra) -> dict:
        meta = SCENARIO_META.get(sid) or {}
        return {
            "id": sid,
            "label": meta.get("label") or sid,
            "short": meta.get("short") or sid,
            "desc": meta.get("desc") or "",
            "available": bool(avail.get(sid, True)),
            "is_primary": sid == primary,
            "weights": {k: round(float(v), 4) for k, v in (weights or {}).items()},
            "home_win_prob": round(float(outcome["home_win_prob"]), 4),
            "draw_prob": round(float(outcome["draw_prob"]), 4),
            "away_win_prob": round(float(outcome["away_win_prob"]), 4),
            **extra,
        }

    scenarios = {
        SCENARIO_ENSEMBLE: pack(
            SCENARIO_ENSEMBLE,
            ensemble_weights,
            blend_outcome(ensemble_weights, poisson, elo, xg, mc),
            main_score=poisson_main_score,
            score_source="poisson",
        ),
        SCENARIO_ELO: pack(
            SCENARIO_ELO,
            SCENARIO_WEIGHTS[SCENARIO_ELO],
            blend_outcome(SCENARIO_WEIGHTS[SCENARIO_ELO], poisson, elo, xg, mc),
            main_score=None,
            score_source="none",
            note="ELO 不产出比分矩阵，比分请看泊松/整合版",
        ),
        SCENARIO_POISSON: pack(
            SCENARIO_POISSON,
            SCENARIO_WEIGHTS[SCENARIO_POISSON],
            blend_outcome(SCENARIO_WEIGHTS[SCENARIO_POISSON], poisson, elo, xg, mc),
            main_score=poisson_main_score,
            alt_scores=list(poisson_alt_scores or [])[:5],
            score_source="poisson",
        ),
        SCENARIO_XG: pack(
            SCENARIO_XG,
            SCENARIO_WEIGHTS[SCENARIO_XG],
            blend_outcome(SCENARIO_WEIGHTS[SCENARIO_XG], poisson, elo, xg, mc),
            main_score=xg_main_score or poisson_main_score,
            score_source="xg" if xg_main_score else "poisson_ref",
        ),
        SCENARIO_MONTE_CARLO: pack(
            SCENARIO_MONTE_CARLO,
            SCENARIO_WEIGHTS[SCENARIO_MONTE_CARLO],
            blend_outcome(SCENARIO_WEIGHTS[SCENARIO_MONTE_CARLO], poisson, elo, xg, mc),
            main_score=mc_main,
            score_source="monte_carlo",
        ),
    }

    return {
        "primary_scenario": primary,
        "scenario_reason": reason,
        "espn_pipeline": espn,
        "pipeline_tier": policy.get("pipeline_tier"),
        "five00_only": bool(policy.get("five00_only")),
        "data_policy": policy,
        "scenarios": scenarios,
        "scenario_order": list(SCENARIO_ORDER),
    }


def apply_scenario_override(
    result: Dict[str, Any],
    scenario_id: str,
    *,
    locked: bool = False,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """把某场景胜平负写回顶栏结论；可选标记用户锁定。"""
    if not result or not scenario_id:
        return result
    scenarios = result.get("scenarios") or {}
    pack = scenarios.get(scenario_id)
    if not isinstance(pack, dict):
        return result

    for sid, s in scenarios.items():
        if isinstance(s, dict):
            s["is_primary"] = sid == scenario_id

    h = float(pack.get("home_win_prob") or 0)
    d = float(pack.get("draw_prob") or 0)
    a = float(pack.get("away_win_prob") or 0)
    total = h + d + a
    if total > 0:
        h, d, a = h / total, d / total, a / total

    result["primary_scenario"] = scenario_id
    result["scenario_locked"] = bool(locked)
    result["scenarios"] = scenarios
    if locked:
        result["scenario_reason"] = reason or f"用户锁定场景：{pack.get('label') or scenario_id}"
    elif reason:
        result["scenario_reason"] = reason

    result["home_win_prob"] = round(h, 4)
    result["draw_prob"] = round(d, 4)
    result["away_win_prob"] = round(a, 4)
    result["weights_used"] = pack.get("weights") or result.get("weights_used")
    result["weight_source"] = f"scenario:{scenario_id}"

    if pack.get("main_score") is not None:
        result["main_score"] = pack.get("main_score")
    elif scenario_id == SCENARIO_ELO:
        result["main_score"] = None
    if pack.get("alt_scores") is not None:
        result["alt_scores"] = pack.get("alt_scores")

    ranked = sorted(
        [("home", h), ("draw", d), ("away", a)],
        key=lambda x: x[1],
        reverse=True,
    )
    top, second = ranked[0], ranked[1]
    margin = top[1] - second[1]
    if top[0] == "home":
        tendency = "主队占优，主场加持明显" if margin > 0.12 else "主队微优，需防平局"
    elif top[0] == "away":
        tendency = "客队占优，客场实力较强" if margin > 0.12 else "客队微优，主队有主场抵抗"
    else:
        tendency = "势均力敌，平局概率较高"
    max_prob = max(h, d, a)
    confidence = "high" if max_prob > 0.50 else ("mid" if max_prob > 0.38 else "low")
    result["tendency"] = tendency
    result["confidence"] = confidence

    label = pack.get("label") or scenario_label(scenario_id)
    prefix = f"【主结论·{label}】"
    note = result.get("scenario_reason") or ""
    result["analysis"] = f"{prefix}{tendency}。" + (f"（{note}）" if note else "")
    return result
