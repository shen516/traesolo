"""串关奖金计算（2串1~8串1）。

两类能力：

1. `calculate_parlay`：各场胜平负概率 × SP 组合的 3^n 全展开分析（保留，供批量模拟串关奖金分析）。
2. `calculate_parlay_picks`：**用户选定选项的单组串关落单**（全玩法，供 §12-7 串关落单）。

- 单注 2 元；串关命中概率 = 各选项概率乘积，奖金 = 2 × 各选项 SP 乘积
- 串关单注奖金上限 50 万元（PAYOUT_CAP_PARLAY）
- 全程只读，不写库；仅供分析参考，不构成投注建议
"""

from __future__ import annotations

from itertools import product
from typing import Any, Dict, List, Optional

from services.prize_calculator import DISCLAIMER, _f, _round2, _round4

PAYOUT_CAP_PARLAY = 500000
MAX_LEGS = 8
OPTION_LABELS = {"win": "主胜", "draw": "平", "lose": "客胜"}

# 全玩法选项：play_type → (前端键, 标签) 映射。
# 串关落单选项范围覆盖全部玩法（spf/nspf/bf/tg/hspf），每个 leg 携带
# play_type + option（玩法内选项，如 bf 的 "1:0"、tg 的 "2"、hspf 的 "win"）。
PLAY_TYPE_OPTIONS = {
    "spf": {"win": "主胜", "draw": "平", "lose": "客胜"},
    "nspf": {"win": "主胜", "draw": "平", "lose": "客胜"},
    "bf": {},
    "tg": {},
    "hspf": {"win": "主胜", "draw": "平", "lose": "客胜"},
}
# 允许的玩法集合（与 db.models.SimulationBet.play_type Enum 一致）
VALID_PLAY_TYPES = tuple(PLAY_TYPE_OPTIONS.keys())


def _leg_label(play_type: str, option: str, match_name: Optional[str] = None) -> str:
    """拼人类可读选项标签（含玩法前缀，便于串关单展示）。"""
    base = PLAY_TYPE_OPTIONS.get(play_type, {}).get(option, option)
    prefix = {
        "spf": "胜平负",
        "nspf": "让球",
        "bf": "比分",
        "tg": "总进球",
        "hspf": "半场胜平负",
    }.get(play_type, play_type)
    name = f"{match_name} " if match_name else ""
    return f"{name}{prefix}-{base}"


def calculate_parlay(legs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """legs: [{match_id, match_name, probs{win,draw,lose}, spf{win,draw,lose}}]

    仅胜平负三选一，3^n 全展开（保留，供批量模拟串关奖金分析）。
    """
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


def calculate_parlay_picks(
    picks: List[Dict[str, Any]],
    multiple: int = 1,
) -> Dict[str, Any]:
    """用户选定选项的单组串关落单（§12-7）。

    picks: [{match_id, match_name, play_type, option, sp, prob}]
        - play_type ∈ VALID_PLAY_TYPES（全玩法）
        - option：玩法内选项（spf/nspf/hspf 为 win/draw/lose；bf 为比分键如 "1:0"；tg 为进球数键如 "2"）
        - sp：该选项真实/模拟 SP；prob：该选项命中概率

    单注 2 元；奖金 = min(2 × ∏sp × multiple, PAYOUT_CAP_PARLAY)。
    命中概率 = ∏prob。仅计算该选定组合，不展开。
    """
    if len(picks) < 2:
        raise ValueError("串关至少需要 2 场赛事")
    if len(picks) > MAX_LEGS:
        raise ValueError(f"串关最多支持 {MAX_LEGS} 场赛事")
    if not isinstance(multiple, int) or multiple < 1:
        raise ValueError("串关倍数需为正整数")

    resolved = []
    for i, leg in enumerate(picks, start=1):
        play_type = leg.get("play_type")
        if play_type not in VALID_PLAY_TYPES:
            raise ValueError(f"第 {i} 项玩法 {play_type!r} 不支持串关")
        option = leg.get("option")
        if not option:
            raise ValueError(f"第 {i} 项缺少选项")
        sp = _f(leg.get("sp"))
        prob = _f(leg.get("prob"))
        if sp is None or sp <= 0:
            raise ValueError(f"第 {i} 项 SP 无效，无法计算串关")
        if sp < 1.01:
            raise ValueError(f"第 {i} 项 SP 不能小于 1.01")
        if prob is None:
            raise ValueError(f"第 {i} 项概率缺失，无法计算串关")
        resolved.append({
            "match_id": leg.get("match_id"),
            "match_name": leg.get("match_name"),
            "play_type": play_type,
            "option": str(option),
            "sp": sp,
            "prob": float(prob),
            "label": _leg_label(play_type, str(option), leg.get("match_name")),
        })

    prob = 1.0
    for leg in resolved:
        prob *= leg["prob"]
    payout = 2.0
    for leg in resolved:
        payout *= leg["sp"]
    payout = _round2(min(payout * multiple, PAYOUT_CAP_PARLAY))

    return {
        "disclaimer": DISCLAIMER,
        "legs": len(resolved),
        "picks": [
            {
                "match_id": leg["match_id"],
                "match_name": leg["match_name"],
                "play_type": leg["play_type"],
                "option": leg["option"],
                "label": leg["label"],
                "sp": _round2(leg["sp"]),
                "prob": _round4(leg["prob"]),
            }
            for leg in resolved
        ],
        "multiple": multiple,
        "prob": _round4(prob),
        "payout": payout,
        "ev": _round2(prob * payout - 2.0 * multiple),
        "payout_cap": PAYOUT_CAP_PARLAY,
    }
