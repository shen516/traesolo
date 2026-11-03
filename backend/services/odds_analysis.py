"""竞彩 SP → 隐含概率 / 抽水 / 与模型偏差（仅分析展示，非投注建议）。

公式：
  raw_i = 1 / SP_i
  overround = sum(raw) - 1
  implied_i = raw_i / sum(raw)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, time as dt_time
from typing import Any, Dict, List, Optional

OUTCOME_HOME = "H"
OUTCOME_DRAW = "D"
OUTCOME_AWAY = "A"

_OUTCOME_LABEL = {
    OUTCOME_HOME: "主胜",
    OUTCOME_DRAW: "平局",
    OUTCOME_AWAY: "客胜",
}


def _f(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        x = float(v)
        return x if x > 0 else None
    except (TypeError, ValueError):
        return None


def implied_probs_from_sp(
    win: Any,
    draw: Any,
    lose: Any,
) -> Optional[Dict[str, Any]]:
    """三路 SP → 归一化隐含概率与 overround。"""
    w, d, l = _f(win), _f(draw), _f(lose)
    if w is None or d is None or l is None:
        return None
    raw_w, raw_d, raw_l = 1.0 / w, 1.0 / d, 1.0 / l
    s = raw_w + raw_d + raw_l
    if s <= 0:
        return None
    home, draw_p, away = raw_w / s, raw_d / s, raw_l / s
    overround = s - 1.0
    tendency = OUTCOME_HOME
    if draw_p >= home and draw_p >= away:
        tendency = OUTCOME_DRAW
    elif away >= home and away >= draw_p:
        tendency = OUTCOME_AWAY
    return {
        "home": round(home, 4),
        "draw": round(draw_p, 4),
        "away": round(away, 4),
        "overround": round(overround, 4),
        "overround_pct": round(overround * 100, 2),
        "tendency": tendency,
        "tendency_label": _OUTCOME_LABEL[tendency],
        "sp": {"win": round(w, 3), "draw": round(d, 3), "lose": round(l, 3)},
    }


NSPF_NOT_ON_SALE_CODE = "nspf_not_on_sale"
NSPF_NOT_ON_SALE_MSG = (
    "胜平负未开售或缺少完整 SP（不影响模型预测计算）"
)


def has_nspf_odds(src: Any) -> bool:
    """是否具备完整胜平负（不让球）三路 SP。"""
    fields = _odds_fields(src)
    return (
        implied_probs_from_sp(
            fields["odds_nspf_win"],
            fields["odds_nspf_draw"],
            fields["odds_nspf_lose"],
        )
        is not None
    )


def require_nspf_odds_enabled() -> bool:
    """config.yaml → prediction.require_nspf_odds（默认 False：预测与开售无关）。"""
    try:
        from db.database import config as app_config
        pred = (app_config or {}).get("prediction") or {}
        if "require_nspf_odds" in pred:
            return bool(pred.get("require_nspf_odds"))
    except Exception:
        pass
    return False


class PredictionSkipped(Exception):
    """预测门禁跳过：不计算、不落库。"""

    def __init__(self, reason: str, code: str = NSPF_NOT_ON_SALE_CODE):
        self.reason = reason
        self.code = code
        super().__init__(reason)


def assert_nspf_on_sale(src: Any) -> None:
    """遗留门禁：仅当 require_nspf_odds=true 且无完整胜平负 SP 时抛出。预测默认不调用。"""
    if not require_nspf_odds_enabled():
        return
    if has_nspf_odds(src):
        return
    raise PredictionSkipped(NSPF_NOT_ON_SALE_MSG, NSPF_NOT_ON_SALE_CODE)


def _model_probs_from_prediction(prediction: Any) -> Optional[Dict[str, float]]:
    if not prediction:
        return None
    if isinstance(prediction, dict):
        h = prediction.get("home_win_prob", prediction.get("homeWinProb"))
        d = prediction.get("draw_prob", prediction.get("drawProb"))
        a = prediction.get("away_win_prob", prediction.get("awayWinProb"))
    else:
        h = getattr(prediction, "home_win_prob", None)
        d = getattr(prediction, "draw_prob", None)
        a = getattr(prediction, "away_win_prob", None)
    try:
        hf, df, af = float(h), float(d), float(a)
    except (TypeError, ValueError):
        return None
    if hf < 0 or df < 0 or af < 0:
        return None
    s = hf + df + af
    if s <= 0:
        return None
    return {"home": hf / s, "draw": df / s, "away": af / s}


def compare_to_model(
    implied: Dict[str, Any],
    model: Dict[str, float],
) -> Dict[str, Any]:
    """市场隐含 − 模型概率（百分点差）。"""
    keys = ("home", "draw", "away")
    deltas = {k: round(float(implied[k]) - float(model[k]), 4) for k in keys}
    abs_map = {k: abs(deltas[k]) for k in keys}
    max_key = max(keys, key=lambda k: abs_map[k])
    max_abs = abs_map[max_key]
    level = "low"
    if max_abs >= 0.12:
        level = "high"
    elif max_abs >= 0.06:
        level = "mid"
    return {
        "delta_home": deltas["home"],
        "delta_draw": deltas["draw"],
        "delta_away": deltas["away"],
        "max_abs_delta": round(max_abs, 4),
        "max_abs_delta_pct": round(max_abs * 100, 1),
        "max_side": max_key,
        "max_side_label": {"home": "主胜", "draw": "平局", "away": "客胜"}[max_key],
        "level": level,
        "agree_tendency": implied.get("tendency") == (
            OUTCOME_HOME if model["home"] >= model["draw"] and model["home"] >= model["away"]
            else (OUTCOME_DRAW if model["draw"] >= model["away"] else OUTCOME_AWAY)
        ),
    }


def _odds_fields(src: Any) -> Dict[str, Any]:
    if isinstance(src, dict):
        g = src.get
    else:
        g = lambda k, default=None: getattr(src, k, default)
    return {
        "handicap": g("handicap"),
        "odds_nspf_win": g("odds_nspf_win"),
        "odds_nspf_draw": g("odds_nspf_draw"),
        "odds_nspf_lose": g("odds_nspf_lose"),
        "odds_spf_win": g("odds_spf_win"),
        "odds_spf_draw": g("odds_spf_draw"),
        "odds_spf_lose": g("odds_spf_lose"),
    }


def analyze_odds(
    src: Any,
    prediction: Any = None,
    *,
    compact: bool = False,
) -> Optional[Dict[str, Any]]:
    """从赛事字段（及可选预测）构造 odds_analysis。"""
    fields = _odds_fields(src)
    nspf = implied_probs_from_sp(
        fields["odds_nspf_win"], fields["odds_nspf_draw"], fields["odds_nspf_lose"]
    )
    spf = implied_probs_from_sp(
        fields["odds_spf_win"], fields["odds_spf_draw"], fields["odds_spf_lose"]
    )
    if not nspf and not spf:
        return None

    primary = nspf or spf
    model = _model_probs_from_prediction(prediction)
    vs_model = compare_to_model(primary, model) if (primary and model) else None

    heuristics = None
    try:
        from services.odds_heuristics import analyze_odds_heuristics
        heuristics = analyze_odds_heuristics(fields if isinstance(src, dict) else src)
    except Exception:
        heuristics = None

    if compact:
        out: Dict[str, Any] = {
            "has_odds": True,
            "has_nspf": nspf is not None,
            "market_tendency": primary.get("tendency"),
            "market_tendency_label": primary.get("tendency_label"),
            "overround_pct": primary.get("overround_pct"),
            "implied_home": primary.get("home"),
            "implied_draw": primary.get("draw"),
            "implied_away": primary.get("away"),
        }
        if vs_model:
            out["delta_level"] = vs_model["level"]
            out["max_abs_delta_pct"] = vs_model["max_abs_delta_pct"]
            out["agree_tendency"] = vs_model["agree_tendency"]
        if heuristics and heuristics.get("nspf"):
            out["heuristic_lean"] = heuristics["nspf"].get("lean")
            out["heuristic_lean_label"] = heuristics["nspf"].get("lean_label")
        return out

    return {
        "disclaimer": "隐含概率由 SP 归一化得到，仅供竞技分析对照，不构成投注建议",
        "handicap": fields["handicap"],
        "nspf": nspf,
        "spf": spf,
        "primary": "nspf" if nspf else "spf",
        "has_nspf": nspf is not None,
        "market_tendency": primary.get("tendency"),
        "market_tendency_label": primary.get("tendency_label"),
        "overround_pct": primary.get("overround_pct"),
        "vs_model": vs_model,
        "model_probs": (
            {k: round(v, 4) for k, v in model.items()} if model else None
        ),
        "heuristics": heuristics,
    }


def attach_odds_analysis(
    item: dict,
    match: Any = None,
    prediction: Any = None,
    *,
    compact: bool = False,
) -> dict:
    """就地写入 item['odds_analysis']。"""
    src = match if match is not None else item
    pred = prediction if prediction is not None else item.get("prediction")
    analysis = analyze_odds(src, pred, compact=compact)
    if analysis:
        item["odds_analysis"] = analysis
    return item


def odds_deviation_report(
    db,
    *,
    days: int = 30,
    league_id: Optional[str] = None,
    limit_samples: int = 500,
) -> Dict[str, Any]:
    """完赛且同时有 SP + 预测的样本：平均抽水与 |市场−模型| 偏差汇总。"""
    from db.models import Match, MatchPrediction

    days = max(7, min(int(days or 30), 180))
    since = date.today() - timedelta(days=days)
    q = (
        db.query(Match)
        .filter(
            Match.status == "finished",
            Match.match_date >= since,
            Match.odds_nspf_win.isnot(None),
            Match.odds_nspf_draw.isnot(None),
            Match.odds_nspf_lose.isnot(None),
        )
        .order_by(Match.match_date.desc())
    )
    if league_id:
        q = q.filter(Match.league_id == league_id)
    matches = q.limit(max(50, min(limit_samples, 2000))).all()
    if not matches:
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "days": days,
            "league_id": league_id,
            "sample_size": 0,
            "with_prediction": 0,
            "avg_overround_pct": None,
            "avg_max_abs_delta_pct": None,
            "agree_rate": None,
            "by_level": {"low": 0, "mid": 0, "high": 0},
            "mean_delta": None,
            "disclaimer": "样本不足；需竞彩 SP 与赛前预测同时存在",
        }

    ids = [m.id for m in matches]
    preds = (
        db.query(MatchPrediction)
        .filter(MatchPrediction.match_id.in_(ids))
        .order_by(MatchPrediction.created_at.asc())
        .all()
    )
    # 开赛前最后一条；无时间则取最早
    by_match: Dict[str, list] = {}
    for p in preds:
        by_match.setdefault(p.match_id, []).append(p)

    overrounds: List[float] = []
    max_deltas: List[float] = []
    agrees = 0
    compared = 0
    by_level = {"low": 0, "mid": 0, "high": 0}
    sum_dh = sum_dd = sum_da = 0.0

    for m in matches:
        nspf = implied_probs_from_sp(m.odds_nspf_win, m.odds_nspf_draw, m.odds_nspf_lose)
        if not nspf:
            continue
        overrounds.append(float(nspf["overround_pct"]))
        plist = by_match.get(m.id) or []
        if not plist:
            continue
        kickoff = datetime.combine(
            m.match_date or date.today(),
            m.match_time if isinstance(m.match_time, dt_time) else dt_time.max,
        )
        before = [p for p in plist if p.created_at and p.created_at <= kickoff]
        chosen = before[-1] if before else plist[0]
        model = _model_probs_from_prediction(chosen)
        if not model:
            continue
        vs = compare_to_model(nspf, model)
        compared += 1
        max_deltas.append(float(vs["max_abs_delta_pct"]))
        by_level[vs["level"]] = by_level.get(vs["level"], 0) + 1
        if vs["agree_tendency"]:
            agrees += 1
        sum_dh += vs["delta_home"]
        sum_dd += vs["delta_draw"]
        sum_da += vs["delta_away"]

    def _avg(xs: List[float]) -> Optional[float]:
        return round(sum(xs) / len(xs), 2) if xs else None

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "days": days,
        "league_id": league_id,
        "sample_size": len(overrounds),
        "with_prediction": compared,
        "avg_overround_pct": _avg(overrounds),
        "avg_max_abs_delta_pct": _avg(max_deltas),
        "agree_rate": round(agrees / compared, 4) if compared else None,
        "by_level": by_level,
        "mean_delta": (
            {
                "home": round(sum_dh / compared, 4),
                "draw": round(sum_dd / compared, 4),
                "away": round(sum_da / compared, 4),
            }
            if compared
            else None
        ),
        "disclaimer": "市场−模型差为分析对照；正值表示市场隐含高于模型。不构成投注建议。",
    }
