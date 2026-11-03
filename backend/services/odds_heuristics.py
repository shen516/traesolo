"""竞彩「看盘基础版」启发式对照层。

仅根据 SP / 让球盘口做规则提示，不参与融合训练，不替换主预测结论。
文案仅供竞技分析对照，不构成投注建议。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from services.odds_analysis import _f, _odds_fields, implied_probs_from_sp

DISCLAIMER = "看盘启发式仅供分析对照，不构成投注建议"
THRESHOLD = 1.9
# 一边倒：主/客胜 SP 比另一侧低到该倍数以下视为强弱悬殊
ONE_SIDED_RATIO = 0.55


def _parse_score(s: str) -> Tuple[int, int]:
    try:
        a, b = str(s).split("-", 1)
        return int(a), int(b)
    except Exception:
        return 0, 0


def _goals_band(total: int) -> str:
    if total <= 0:
        return "0"
    if total >= 7:
        return "7+"
    return str(total)


def _htft_from_score(score: str) -> List[str]:
    """由全场比分推半全场常见组合（文档基础版）。"""
    h, a = _parse_score(score)
    if h == a:
        # 如 1-1 → 胜平 / 平平 / 负平
        return ["胜平", "平平", "负平"]
    if h >= a + 2:
        # 2-0 及以上 → 胜胜 / 平胜
        return ["胜胜", "平胜"]
    if a >= h + 2:
        return ["负负", "平负"]
    if h > a:
        return ["胜胜", "平胜", "胜平"]
    return ["负负", "平负", "负平"]


def _nspf_heuristic(win: float, draw: float, lose: float) -> Dict[str, Any]:
    """胜平负看盘：≥1.9 偏平；一边倒跟低赔；强弱悬殊偏大分。"""
    rules: List[str] = []
    side_odds = min(win, lose)
    strong_vs_weak = (min(win, lose) / max(win, lose)) <= ONE_SIDED_RATIO

    if strong_vs_weak:
        lean = "home" if win < lose else "away"
        lean_label = "主胜" if lean == "home" else "客胜"
        scores = ["3-0", "3-1", "4-0", "4-1"] if lean == "home" else ["0-3", "1-3", "0-4", "1-4"]
        rules.append("强弱悬殊：舍弃低赔平分路径，以大分为主")
        main = scores[0]
        return {
            "lean": lean,
            "lean_label": lean_label,
            "rule": "strong_vs_weak",
            "scores": scores[:4],
            "main_score": main,
            "alt_scores": scores[1:4],
            "rules_hit": rules,
            "threshold": THRESHOLD,
        }

    if side_odds >= THRESHOLD:
        scores = ["0-0", "1-1", "2-2"]
        rules.append(f"胜/负 SP 均≥{THRESHOLD}：倾向平局，主推平分")
        return {
            "lean": "draw",
            "lean_label": "平局",
            "rule": "above_threshold_draw",
            "scores": scores,
            "main_score": "1-1",
            "alt_scores": ["0-0", "2-2"],
            "rules_hit": rules,
            "threshold": THRESHOLD,
        }

    # 一边倒：向低赔侧倾斜
    lean = "home" if win <= lose else "away"
    lean_label = "主胜" if lean == "home" else "客胜"
    scores = ["1-0", "2-1", "2-0"] if lean == "home" else ["0-1", "1-2", "0-2"]
    rules.append(f"低赔一侧倒（最低胜负 SP={side_odds:.2f}<{THRESHOLD}）：倾向{lean_label}")
    return {
        "lean": lean,
        "lean_label": lean_label,
        "rule": "one_sided",
        "scores": scores,
        "main_score": scores[0],
        "alt_scores": scores[1:],
        "rules_hit": rules,
        "threshold": THRESHOLD,
    }


def _spf_heuristic(
    handicap: Any,
    win: float,
    draw: float,
    lose: float,
) -> Dict[str, Any]:
    """让球胜平负：盘口正负解读；≥1.9 偏让平；特强看低赔。"""
    rules: List[str] = []
    hc = None
    try:
        if handicap is not None and handicap != "":
            hc = float(handicap)
    except (TypeError, ValueError):
        hc = None

    if hc is not None:
        if hc <= -1:
            rules.append("让球≤-1：主队通常有主场优势或实力占优")
        elif hc >= 1:
            rules.append("让球≥+1：主队相对偏弱")

    side_min = min(win, lose)
    if side_min >= THRESHOLD:
        rules.append(f"让球盘胜/负 SP≥{THRESHOLD}：倾向让平")
        return {
            "lean": "draw",
            "lean_label": "让平",
            "rule": "handicap_draw",
            "handicap": hc,
            "rules_hit": rules,
            "threshold": THRESHOLD,
        }

    lean = "home" if win <= lose else "away"
    lean_label = "让胜" if lean == "home" else "让负"
    rules.append(f"让球盘低赔<{THRESHOLD}：倾向{lean_label}（对照低赔侧）")
    return {
        "lean": lean,
        "lean_label": lean_label,
        "rule": "handicap_low_odds",
        "handicap": hc,
        "rules_hit": rules,
        "threshold": THRESHOLD,
    }


def _score_board_hint(nspf: Dict[str, Any], win: float, draw: float, lose: float) -> Dict[str, Any]:
    """比分看盘：一般取最低三档；强弱悬殊走大分。"""
    ranked = sorted(
        [("home", win, "主胜相关"), ("draw", draw, "平局相关"), ("away", lose, "客胜相关")],
        key=lambda x: x[1],
    )
    lowest_three = [
        {"side": s, "sp": round(sp, 3), "note": note} for s, sp, note in ranked[:3]
    ]
    return {
        "lowest_three_sp": lowest_three,
        "preferred_scores": nspf.get("scores") or [],
        "note": "一般关注最低三档赔率对应方向；强弱悬殊时改推大分",
    }


def analyze_odds_heuristics(src: Any) -> Optional[Dict[str, Any]]:
    """从赛事赔率字段生成看盘启发式对照结果。"""
    fields = _odds_fields(src)
    w = _f(fields["odds_nspf_win"])
    d = _f(fields["odds_nspf_draw"])
    l = _f(fields["odds_nspf_lose"])
    nspf_block = None
    if w is not None and d is not None and l is not None:
        nspf_block = _nspf_heuristic(w, d, l)

    sw, sd, sl = (
        _f(fields["odds_spf_win"]),
        _f(fields["odds_spf_draw"]),
        _f(fields["odds_spf_lose"]),
    )
    spf_block = None
    if sw is not None and sd is not None and sl is not None:
        spf_block = _spf_heuristic(fields.get("handicap"), sw, sd, sl)

    if not nspf_block and not spf_block:
        return None

    main_score = (nspf_block or {}).get("main_score")
    alt_scores = (nspf_block or {}).get("alt_scores") or []
    goals = None
    htft = None
    if main_score:
        gh, ga = _parse_score(main_score)
        goals = {
            "from_score": main_score,
            "total": gh + ga,
            "band": _goals_band(gh + ga),
            "note": "进球数按启发式主推比分合计",
        }
        htft = {
            "from_score": main_score,
            "combos": _htft_from_score(main_score),
            "note": "半全场由主推比分推导",
        }

    score_hint = None
    if nspf_block and w is not None and d is not None and l is not None:
        score_hint = _score_board_hint(nspf_block, w, d, l)

    return {
        "disclaimer": DISCLAIMER,
        "source": "lookbook_basic_v1",
        "nspf": nspf_block,
        "spf": spf_block,
        "score": score_hint,
        "main_score": main_score,
        "alt_scores": alt_scores,
        "total_goals": goals,
        "htft": htft,
        "has_nspf": implied_probs_from_sp(
            fields["odds_nspf_win"], fields["odds_nspf_draw"], fields["odds_nspf_lose"]
        )
        is not None,
    }
