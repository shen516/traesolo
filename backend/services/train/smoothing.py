"""权重 EMA 平滑与小样本向全局收缩。

底层仍走 ensemble 实例方法，本模块仅统一调用点，便于门面/执行层解耦。
"""
from __future__ import annotations

from typing import Any, Dict, Tuple


def smooth_weights(
    ensemble,
    new_weights: Dict[str, float],
    prev_weights: Dict[str, float] | None,
    sample_n: int,
) -> Tuple[Dict[str, float], float]:
    return ensemble.smooth_weights(new_weights, prev_weights, sample_n=sample_n)


def blend_weights(
    ensemble,
    league_weights: Dict[str, float],
    global_weights: Dict[str, float],
    beta: float,
) -> Dict[str, float]:
    return ensemble.blend_weights(league_weights, global_weights, beta)


def soft_blend_beta(ensemble, sample_n: int) -> float:
    return float(ensemble.soft_blend_beta(sample_n))
