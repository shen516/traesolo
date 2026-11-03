"""训练评测指标：Brier / 对数损失 / 校准 / walk-forward 切分。"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Iterable, List, Optional, Sequence, Tuple


OUTCOMES = ("home", "draw", "away")


def decay_weight(
    match_date,
    *,
    ref_date=None,
    half_life_days: float = 180.0,
    enabled: bool = True,
) -> float:
    """指数时间衰减：w = 0.5 ** (age / half_life)。"""
    if not enabled or half_life_days is None or float(half_life_days) <= 0:
        return 1.0
    ref = ref_date or date.today()
    if isinstance(ref, datetime):
        ref = ref.date()
    md = match_date
    if isinstance(md, datetime):
        md = md.date()
    if md is None:
        return 1.0
    age = max(0, (ref - md).days)
    return float(0.5 ** (age / float(half_life_days)))


def _probs_tuple(pred: dict) -> Tuple[float, float, float]:
    h = max(0.0, float(pred.get("home") or 0))
    d = max(0.0, float(pred.get("draw") or 0))
    a = max(0.0, float(pred.get("away") or 0))
    s = h + d + a
    if s <= 0:
        return (1 / 3, 1 / 3, 1 / 3)
    return (h / s, d / s, a / s)


def _one_hot(actual: str) -> Tuple[float, float, float]:
    return (
        1.0 if actual == "home" else 0.0,
        1.0 if actual == "draw" else 0.0,
        1.0 if actual == "away" else 0.0,
    )


def blend_probs(components: dict, weights: dict) -> Tuple[float, float, float]:
    """按融合权重合成胜平负概率（与 _score_weights 逻辑一致）。"""
    elo_w = float(weights.get("elo", 0))
    poisson_w = float(weights.get("poisson", 0))
    xg_w = float(weights.get("xg", 0))
    mc_w = float(weights.get("monte_carlo", 0))
    if float(components.get("xg_coverage") or 0) <= 0 and xg_w > 0:
        poisson_w += xg_w
        xg_w = 0.0
    total = elo_w + poisson_w + xg_w + mc_w
    if total <= 0:
        return (1 / 3, 1 / 3, 1 / 3)
    elo_w /= total
    poisson_w /= total
    xg_w /= total
    mc_w /= total
    xg_c = components.get("xg") or {"home": 0, "draw": 0, "away": 0}
    h = (
        elo_w * components["elo"]["home"]
        + poisson_w * components["poisson"]["home"]
        + xg_w * xg_c["home"]
        + mc_w * components["monte_carlo"]["home"]
    )
    d = (
        elo_w * components["elo"]["draw"]
        + poisson_w * components["poisson"]["draw"]
        + xg_w * xg_c.get("draw", 0)
        + mc_w * components["monte_carlo"]["draw"]
    )
    a = (
        elo_w * components["elo"]["away"]
        + poisson_w * components["poisson"]["away"]
        + xg_w * xg_c["away"]
        + mc_w * components["monte_carlo"]["away"]
    )
    if d <= 0:
        d = max(0.01, 1.0 - h - a)
    return _probs_tuple({"home": h, "draw": d, "away": a})


def predict_label(probs: Tuple[float, float, float]) -> str:
    h, d, a = probs
    if h >= d and h >= a:
        return "home"
    if a >= d:
        return "away"
    return "draw"


def score_cache(
    cache: Sequence[dict],
    weights: dict,
    *,
    use_sample_weights: bool = True,
    calibration_bins: int = 5,
) -> dict:
    """对预计算组件缓存评测：准确率 / Brier / log-loss / ECE。"""
    if not cache:
        return {
            "n": 0,
            "accuracy": 0.0,
            "brier": 1.0,
            "log_loss": 2.0,
            "ece": 1.0,
            "weighted_n": 0.0,
        }

    w_sum = 0.0
    correct_w = 0.0
    brier_w = 0.0
    ll_w = 0.0
    # 校准：按预测最大类概率分箱
    bins = max(2, int(calibration_bins or 5))
    bin_conf = [0.0] * bins
    bin_acc = [0.0] * bins
    bin_w = [0.0] * bins

    for c in cache:
        sw = float(c.get("sample_weight") or 1.0) if use_sample_weights else 1.0
        if sw <= 0:
            continue
        probs = blend_probs(c, weights)
        actual = c.get("actual")
        y = _one_hot(actual)
        brier = sum((probs[i] - y[i]) ** 2 for i in range(3)) / 3.0
        # clip for log-loss
        eps = 1e-12
        p_true = probs[0] if actual == "home" else (probs[1] if actual == "draw" else probs[2])
        p_true = min(1.0 - eps, max(eps, p_true))
        ll = -math.log(p_true)
        pred = predict_label(probs)
        hit = 1.0 if pred == actual else 0.0

        w_sum += sw
        correct_w += sw * hit
        brier_w += sw * brier
        ll_w += sw * ll

        conf = max(probs)
        bi = min(bins - 1, int(conf * bins))
        bin_w[bi] += sw
        bin_conf[bi] += sw * conf
        bin_acc[bi] += sw * hit

    if w_sum <= 0:
        return {
            "n": 0,
            "accuracy": 0.0,
            "brier": 1.0,
            "log_loss": 2.0,
            "ece": 1.0,
            "weighted_n": 0.0,
        }

    ece = 0.0
    for i in range(bins):
        if bin_w[i] <= 0:
            continue
        avg_conf = bin_conf[i] / bin_w[i]
        avg_acc = bin_acc[i] / bin_w[i]
        ece += (bin_w[i] / w_sum) * abs(avg_acc - avg_conf)

    return {
        "n": len(cache),
        "accuracy": correct_w / w_sum,
        "brier": brier_w / w_sum,
        "log_loss": ll_w / w_sum,
        "ece": ece,
        "weighted_n": round(w_sum, 2),
    }


def walk_forward_slices(cache: Sequence[dict], folds: int = 3) -> List[List[dict]]:
    """按时间序将验证缓存切成 folds 段（walk-forward 评测用）。"""
    folds = max(1, int(folds or 1))
    if not cache or folds <= 1 or len(cache) < folds * 4:
        return [list(cache)] if cache else []

    ordered = sorted(
        cache,
        key=lambda c: c.get("match_date") or date.min,
    )
    n = len(ordered)
    size = n // folds
    slices = []
    for i in range(folds):
        start = i * size
        end = n if i == folds - 1 else (i + 1) * size
        part = ordered[start:end]
        if part:
            slices.append(part)
    return slices or [list(ordered)]


def average_metrics(metric_list: Iterable[dict]) -> dict:
    rows = [m for m in metric_list if m and int(m.get("n") or 0) > 0]
    if not rows:
        return {
            "n": 0,
            "accuracy": 0.0,
            "brier": 1.0,
            "log_loss": 2.0,
            "ece": 1.0,
            "weighted_n": 0.0,
            "folds": 0,
        }
    total_n = sum(int(m["n"]) for m in rows)
    # 按场次加权平均
    def _avg(key):
        return sum(float(m[key]) * int(m["n"]) for m in rows) / total_n

    return {
        "n": total_n,
        "accuracy": _avg("accuracy"),
        "brier": _avg("brier"),
        "log_loss": _avg("log_loss"),
        "ece": _avg("ece"),
        "weighted_n": sum(float(m.get("weighted_n") or 0) for m in rows),
        "folds": len(rows),
    }


def is_better(candidate: dict, best: dict, primary: str = "brier") -> bool:
    """primary=brier/log_loss/ece → 越小越好；accuracy → 越大越好。"""
    metric = (primary or "brier").lower()
    if not best or int(best.get("n") or 0) <= 0:
        return True
    if metric == "accuracy":
        return float(candidate.get("accuracy") or 0) > float(best.get("accuracy") or -1)
    # 越小越好；同等时准确率更高者优先
    c_v = float(candidate.get(metric) or 9e9)
    b_v = float(best.get(metric) or 9e9)
    if abs(c_v - b_v) < 1e-9:
        return float(candidate.get("accuracy") or 0) > float(best.get("accuracy") or 0)
    return c_v < b_v
