"""串关奖金计算（2串1~8串1）：各场胜平负概率 × SP 组合。

- 单注 2 元；串关命中概率 = 各场选项概率乘积，奖金 = 2 × 各场 SP 乘积
- 串关单注奖金上限 50 万元；每场仅取胜平负三选一
- SP 直接取各场单场 prize.spf.sp（与单场奖金分析口径一致）
- 全程只读，不写库；仅供分析参考，不构成投注建议
"""

from __future__ import annotations

from itertools import product
from typing import Any, Dict, List

from services.prize_calculator import DISCLAIMER, _f, _round2, _round4

PAYOUT_CAP_PARLAY = 500000
MAX_LEGS = 8
OPTION_LABELS = {"win": "主胜", "draw": "平", "lose": "客胜"}


def calculate_parlay(legs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """legs: [{match_id, match_name, probs{win,draw,lose}, spf{win,draw,lose}}]"""
    if len(legs) < 2:
        raise ValueError("串关至少需要 2 场赛事")
    if len(legs) > MAX_LEGS:
        raise ValueError(f"串关最多支持 {MAX_LEGS} 场赛事")

    resolved: List[Dict[str, Any]] = []
    for leg in legs:
        probs = leg.get("probs") or {}
        spf = {}
        for k in ("win", "draw", "lose"):
            v = _f((leg.get("spf") or {}).get(k))
            if v is None:
                raise ValueError(
                    f"赛事 {leg.get('match_name') or leg.get('match_id')} 缺少胜平负 SP，无法计算串关"
                )
            spf[k] = v
        resolved.append({
            "match_id": leg.get("match_id"),
            "match_name": leg.get("match_name"),
            "probs": {k: float(probs.get(k) or 0) for k in ("win", "draw", "lose")},
            "spf": spf,
        })

    combos = []
    for picks in product(("win", "draw", "lose"), repeat=len(resolved)):
        prob = 1.0
        payout = 2.0
        for leg, pick in zip(resolved, picks):
            prob *= leg["probs"][pick]
            payout *= leg["spf"][pick]
        payout = _round2(min(payout, PAYOUT_CAP_PARLAY))
        combos.append({
            "picks": [OPTION_LABELS[p] for p in picks],
            "prob": _round4(prob),
            "payout": payout,
            "ev": _round2(prob * payout - 2.0),
        })

    combos.sort(key=lambda c: c["prob"], reverse=True)
    expected_payout = _round2(sum(c["prob"] * c["payout"] for c in combos))
    return {
        "disclaimer": DISCLAIMER,
        "legs": len(resolved),
        "total_combos": len(combos),
        "total_prob": _round4(sum(c["prob"] for c in combos)),
        "expected_payout": expected_payout,
        "expected_ev": _round2(expected_payout - 2.0),
        "payout_cap": PAYOUT_CAP_PARLAY,
        "top_combos": combos[:10],
    }
