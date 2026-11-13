"""奖金计算模式：模型概率 × 竞彩 SP → 理论奖金 / EV / 价值标记。

SP 来源按玩法独立判定（快照 → matches.odds_* → 合成兜底 → 手动覆盖）。
仅供分析参考，不构成投注建议；全程只读，不写库。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from services.odds_analysis import implied_probs_from_sp

DISCLAIMER = "仅供分析参考，不构成投注建议"

# 单关单注奖金上限（元）；串关上限留待批量模拟扩展
PAYOUT_CAP_SINGLE = 100000
PAYOUT_MIN = 2.0
VALUE_EDGE_THRESHOLD = 0.02

# 竞彩比分 31 选项
BF_HOME_KEYS = ("1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2", "5:0", "5:1", "5:2")
BF_DRAW_KEYS = ("0:0", "1:1", "2:2", "3:3")
BF_AWAY_KEYS = ("0:1", "0:2", "1:2", "0:3", "1:3", "2:3", "0:4", "1:4", "2:4", "0:5", "1:5", "2:5")
BF_ALL_KEYS = BF_HOME_KEYS + ("胜其它",) + BF_DRAW_KEYS + ("平其它",) + BF_AWAY_KEYS + ("负其它",)

TG_KEYS = ("0", "1", "2", "3", "4", "5", "6", "7+")


def _f(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        x = float(v)
        return x if x > 0 else None
    except (TypeError, ValueError):
        return None


def _round2(x) -> float:
    return round(float(x), 2)


def _round4(x) -> float:
    return round(float(x), 4)


def _payout(sp: float) -> float:
    """单注奖金 = 2 × SP；上限截断，不足 2 元补足。"""
    payout = 2.0 * float(sp)
    payout = min(payout, PAYOUT_CAP_SINGLE)
    if payout < PAYOUT_MIN:
        payout = PAYOUT_MIN
    return _round2(payout)


def _ev(prob: float, sp: float) -> float:
    """每 2 元投注的期望净收益。"""
    return _round2(float(prob) * float(sp) * 2.0 - 2.0)


def _synthetic_sp(probs: Dict[str, float], overround: float) -> Dict[str, float]:
    """合成兜底：SP_i = 1 / (P_i × (1 + overround))。"""
    factor = 1.0 + float(overround)
    out = {}
    for key, p in probs.items():
        p = max(float(p), 1e-6)
        out[key] = _round2(1.0 / (p * factor))
    return out


def _implied_from_sp(sp: Dict[str, float]) -> Dict[str, float]:
    """多选项 SP → 归一化隐含概率。"""
    raw = {k: 1.0 / float(v) for k, v in sp.items() if _f(v)}
    s = sum(raw.values())
    if s <= 0:
        return {k: 0.0 for k in sp}
    return {k: _round4(v / s) for k, v in raw.items()}


def _latest_snapshot(db, match_id: str):
    from db.models import OddsSnapshot
    return (
        db.query(OddsSnapshot)
        .filter(OddsSnapshot.match_id == str(match_id))
        .order_by(OddsSnapshot.captured_at.desc())
        .first()
    )


def _parse_bf_json(raw) -> Optional[Dict[str, float]]:
    if not raw:
        return None
    data = raw if isinstance(raw, dict) else None
    if data is None:
        try:
            data = json.loads(raw)
        except Exception:
            return None
    if not isinstance(data, dict):
        return None
    out = {}
    for key in BF_ALL_KEYS:
        v = _f(data.get(key))
        if v is not None:
            out[key] = v
    return out or None


def _three_way_probs(mc: Dict[str, Any]) -> Dict[str, float]:
    return {
        "win": _round4(mc.get("home_win_prob") or 0),
        "draw": _round4(mc.get("draw_prob") or 0),
        "lose": _round4(mc.get("away_win_prob") or 0),
    }


def _nspf_probs(score_matrix: List[List[float]], handicap: int) -> Dict[str, float]:
    """让球胜平负：基于比分矩阵偏移聚合。主让为负。"""
    h = int(handicap or 0)
    win = draw = lose = 0.0
    for hg, row in enumerate(score_matrix or []):
        for ag, p in enumerate(row):
            diff = hg - ag + h
            if diff > 0:
                win += p
            elif diff == 0:
                draw += p
            else:
                lose += p
    total = win + draw + lose
    if total <= 0:
        return {"win": 1 / 3, "draw": 1 / 3, "lose": 1 / 3}
    return {"win": _round4(win / total), "draw": _round4(draw / total), "lose": _round4(lose / total)}


def _bf_probs(mc: Dict[str, Any]) -> Dict[str, float]:
    """比分 31 选项概率：矩阵单元格 + 胜/平/负其它兜底。"""
    matrix = mc.get("score_matrix") or []
    probs: Dict[str, float] = {}

    def cell(key: str) -> float:
        h, a = key.split(":")
        hi, ai = int(h), int(a)
        if hi < len(matrix) and ai < len(matrix[hi]):
            return float(matrix[hi][ai])
        return 0.0

    home_known = sum(cell(k) for k in BF_HOME_KEYS)
    draw_known = sum(cell(k) for k in BF_DRAW_KEYS)
    away_known = sum(cell(k) for k in BF_AWAY_KEYS)

    for k in BF_HOME_KEYS + BF_DRAW_KEYS + BF_AWAY_KEYS:
        probs[k] = _round4(cell(k))
    probs["胜其它"] = _round4(max(0.0, float(mc.get("home_win_prob") or 0) - home_known))
    probs["平其它"] = _round4(max(0.0, float(mc.get("draw_prob") or 0) - draw_known))
    probs["负其它"] = _round4(max(0.0, float(mc.get("away_win_prob") or 0) - away_known))
    return probs


def _tg_probs(mc: Dict[str, Any]) -> Dict[str, float]:
    """总进球 0~7+：直接映射 goal_distribution。"""
    dist = {int(g["goals"]): float(g["prob"]) for g in (mc.get("goal_distribution") or [])}
    probs = {}
    for g in range(7):
        probs[str(g)] = _round4(dist.get(g, 0.0))
    rest = 1.0 - sum(dist.get(g, 0.0) for g in range(7))
    probs["7+"] = _round4(max(0.0, rest))
    return probs


def _hspf_probs(mc: Dict[str, Any]) -> Dict[str, float]:
    """半场胜平负三选一概率：直接读 mc.hspf_probs（由半场泊松 λ≈0.45λ 模拟聚合）。"""
    hspf = mc.get("hspf_probs") or {}
    win = _f(hspf.get("win"))
    draw = _f(hspf.get("draw"))
    lose = _f(hspf.get("lose"))
    if win is None or draw is None or lose is None:
        # 兜底：半场平局概率显著高于全场，近似 1/3 均分
        return {"win": _round4(1 / 3), "draw": _round4(1 / 3), "lose": _round4(1 / 3)}
    total = win + draw + lose
    if total <= 0:
        return {"win": _round4(1 / 3), "draw": _round4(1 / 3), "lose": _round4(1 / 3)}
    return {"win": _round4(win / total), "draw": _round4(draw / total), "lose": _round4(lose / total)}


def _option_block(probs: Dict[str, float], sp: Dict[str, float]) -> Dict[str, Any]:
    """通用：全量模型概率 + 可用选项的 SP / 隐含概率 / EV / 价值标记 / 单注奖金。"""
    implied = _implied_from_sp(sp)
    return {
        "probs": {k: _round4(v) for k, v in probs.items()},
        "sp": {k: _round2(sp[k]) for k in sp},
        "implied": {k: _round4(implied[k]) for k in implied},
        "ev": {k: _ev(probs.get(k, 0), sp[k]) for k in sp},
        "value_flags": {
            k: bool(probs.get(k, 0) - implied.get(k, 0) > VALUE_EDGE_THRESHOLD) for k in sp
        },
        "payout": {k: _payout(sp[k]) for k in sp},
    }


def _resolve_sp(
    *,
    probs: Dict[str, float],
    real_sp: Optional[Dict[str, float]],
    manual_sp: Optional[Dict[str, float]],
    sp_mode: str,
    overround: float,
    real_source: str,
) -> tuple:
    """返回 (sp, overall_source, option_sources)。

    选项级解析：手动覆盖的选项用手动值；未被手动覆盖/真实缺失的选项用合成兜底。
    overall_source（玩法级粗粒度，兼容既有语义）：
        有手动覆盖→'manual'；否则有真实→real_source；否则→'synthetic'。
    option_sources（选项级精确）：{option: 'manual'|'synthetic'|real_source}，供前端行内提示。
    """
    synth = _synthetic_sp(probs, overround)

    def _overall(has_manual: bool, has_real: bool) -> str:
        if has_manual:
            return "manual"
        if has_real:
            return real_source
        return "synthetic"

    if manual_sp:
        cleaned = {k: v for k, v in manual_sp.items() if _f(v) is not None}
        if cleaned:
            sp, src = {}, {}
            has_manual = has_real = False
            for k in probs:
                if k in cleaned:
                    sp[k] = _round2(_f(cleaned[k]))
                    src[k] = "manual"
                    has_manual = True
                elif sp_mode == "synthetic" or not real_sp or k not in real_sp or _f(real_sp[k]) is None:
                    sp[k] = synth[k]
                    src[k] = "synthetic"
                else:
                    sp[k] = _round2(_f(real_sp[k]))
                    src[k] = real_source
                    has_real = True
            return sp, _overall(has_manual, has_real), src

    if sp_mode == "synthetic":
        src = {k: "synthetic" for k in synth}
        return synth, "synthetic", src
    if real_sp:
        sp, src = {}, {}
        has_real = False
        for k in probs:
            if k in real_sp and _f(real_sp[k]) is not None:
                sp[k] = _round2(_f(real_sp[k]))
                src[k] = real_source
                has_real = True
            else:
                sp[k] = synth[k]
                src[k] = "synthetic"
        return sp, _overall(False, has_real), src
    src = {k: "synthetic" for k in synth}
    return synth, "synthetic", src


def calculate_prize(
    db,
    match,
    mc_detailed: Dict[str, Any],
    *,
    sp_mode: str = "auto",
    overround: float = 0.13,
    handicap: Optional[int] = None,
    manual_sp: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, Any]:
    """组装 prize 字段。mc_detailed 来自 simulate_detailed 输出。"""
    manual_sp = manual_sp or {}
    overround = max(0.05, min(0.30, float(overround or 0.13)))

    snapshot = _latest_snapshot(db, match.id)
    snapshot_at = None
    if snapshot and snapshot.captured_at:
        snapshot_at = snapshot.captured_at.strftime("%Y-%m-%d %H:%M")

    # --- 真实 SP 提取（快照优先，回退 matches.odds_*） ---
    def _spf(row) -> Optional[Dict[str, float]]:
        if row is None:
            return None
        w, d, l = _f(row.odds_spf_win), _f(row.odds_spf_draw), _f(row.odds_spf_lose)
        if w and d and l:
            return {"win": w, "draw": d, "lose": l}
        return None

    def _nspf(row) -> Optional[Dict[str, float]]:
        if row is None:
            return None
        w, d, l = _f(row.odds_nspf_win), _f(row.odds_nspf_draw), _f(row.odds_nspf_lose)
        if w and d and l:
            return {"win": w, "draw": d, "lose": l}
        return None

    def _bf(row) -> Optional[Dict[str, float]]:
        if row is None:
            return None
        return _parse_bf_json(getattr(row, "odds_bf_json", None))

    def _hspf(row) -> Optional[Dict[str, float]]:
        if row is None:
            return None
        w = _f(getattr(row, "odds_hspf_win", None))
        d = _f(getattr(row, "odds_hspf_draw", None))
        l = _f(getattr(row, "odds_hspf_lose", None))
        if w and d and l:
            return {"win": w, "draw": d, "lose": l}
        return None

    spf_real, spf_source_real = _spf(snapshot), "snapshot"
    if spf_real is None:
        spf_real, spf_source_real = _spf(match), "real"
    nspf_real, nspf_source_real = _nspf(snapshot), "snapshot"
    if nspf_real is None:
        nspf_real, nspf_source_real = _nspf(match), "real"
    bf_real, bf_source_real = _bf(snapshot), "snapshot"
    if bf_real is None:
        bf_real, bf_source_real = _bf(match), "real"
    hspf_real, hspf_source_real = _hspf(snapshot), "snapshot"
    if hspf_real is None:
        hspf_real, hspf_source_real = _hspf(match), "real"

    # --- 各玩法概率 ---
    spf_probs = _three_way_probs(mc_detailed)
    hc = handicap if handicap is not None else getattr(match, "handicap", None)
    hc_source = "manual" if handicap is not None else ("match" if hc is not None else "default")
    hc = int(hc) if hc is not None else 0
    nspf_probs = _nspf_probs(mc_detailed.get("score_matrix") or [], hc)
    bf_probs = _bf_probs(mc_detailed)
    tg_probs = _tg_probs(mc_detailed)
    hspf_probs = _hspf_probs(mc_detailed)

    # --- SP 解析 ---
    spf_sp, spf_src, spf_optsrc = _resolve_sp(
        probs=spf_probs, real_sp=spf_real, manual_sp=manual_sp.get("spf"),
        sp_mode=sp_mode, overround=overround, real_source=spf_source_real,
    )
    nspf_sp, nspf_src, nspf_optsrc = _resolve_sp(
        probs=nspf_probs, real_sp=nspf_real, manual_sp=manual_sp.get("nspf"),
        sp_mode=sp_mode, overround=overround, real_source=nspf_source_real,
    )
    bf_sp, bf_src, bf_optsrc = _resolve_sp(
        probs=bf_probs, real_sp=bf_real, manual_sp=manual_sp.get("bf"),
        sp_mode=sp_mode, overround=overround, real_source=bf_source_real,
    )
    tg_sp, tg_src, tg_optsrc = _resolve_sp(
        probs=tg_probs, real_sp=None, manual_sp=manual_sp.get("tg"),
        sp_mode=sp_mode, overround=overround, real_source="real",
    )
    hspf_sp, hspf_src, hspf_optsrc = _resolve_sp(
        probs=hspf_probs, real_sp=hspf_real, manual_sp=manual_sp.get("hspf"),
        sp_mode=sp_mode, overround=overround, real_source=hspf_source_real,
    )

    spf_block = _option_block(spf_probs, spf_sp)
    nspf_block = _option_block(nspf_probs, nspf_sp)
    nspf_block["handicap"] = hc
    nspf_block["handicap_source"] = hc_source
    tg_block = _option_block(tg_probs, tg_sp)
    hspf_block = _option_block(hspf_probs, hspf_sp)

    # 比分：全量 31 项 + Top5 价值
    bf_block = _option_block(bf_probs, bf_sp)
    implied_bf = bf_block["implied"]
    top_value = sorted(
        (
            {
                "score": k,
                "sp": bf_sp[k],
                "prob": bf_probs.get(k, 0),
                "ev": _ev(bf_probs.get(k, 0), bf_sp[k]),
                "edge": _round4(bf_probs.get(k, 0) - implied_bf.get(k, 0)),
            }
            for k in bf_sp
            if bf_optsrc.get(k) != "synthetic"  # 仅真实 SP 选项参与价值推荐，合成值不作为依据
        ),
        key=lambda x: x["ev"],
        reverse=True,
    )[:5]
    bf_block["top_value"] = top_value

    return {
        "sp_source": {"spf": spf_src, "nspf": nspf_src, "bf": bf_src, "tg": tg_src, "hspf": hspf_src},
        "sp_source_detail": {
            "spf": spf_optsrc, "nspf": nspf_optsrc, "bf": bf_optsrc, "tg": tg_optsrc, "hspf": hspf_optsrc,
        },
        "snapshot_at": snapshot_at,
        "overround": _round2(overround),
        "spf": spf_block,
        "nspf": nspf_block,
        "bf": bf_block,
        "tg": tg_block,
        "hspf": hspf_block,
        "parlay": {
            "enabled": False,
            "note": "串关需多场赛事，当前为单场模拟，串关功能在批量模拟中支持",
        },
        "disclaimer": DISCLAIMER,
    }
