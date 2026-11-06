"""Walk-forward 切片与评估辅助（薄封装，供训练门面复用）。"""

from __future__ import annotations

from typing import Any, Dict, List

from services.train.hyperparam import validation_slice


def walk_forward_slices(cache: list, folds: int = 3) -> List[list]:
    from services.eval_metrics import walk_forward_slices as _slices
    return _slices(cache, folds=folds)


def score_cache(cache: list, weights: dict, calibration_bins: int = 5) -> Dict[str, Any]:
    from services.eval_metrics import score_cache as _score
    return _score(cache, weights, calibration_bins=calibration_bins)


__all__ = ["validation_slice", "walk_forward_slices", "score_cache"]
