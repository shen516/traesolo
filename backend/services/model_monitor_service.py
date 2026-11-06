"""模型校准与漂移监控。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from db.models import AccuracyTrend, Match
from services import PredictionService
from services.eval_metrics import predict_label, _one_hot


def _actual_outcome(match: Match) -> Optional[str]:
    r = (match.result or "").upper()
    if r == "H":
        return "home"
    if r == "A":
        return "away"
    if r == "D":
        return "draw"
    if match.home_goals is not None and match.away_goals is not None:
        if match.home_goals > match.away_goals:
            return "home"
        if match.home_goals < match.away_goals:
            return "away"
        return "draw"
    return None


def calibration_report(
    db: Session,
    *,
    days: int = 90,
    league_id: Optional[str] = None,
    bins: int = 5,
) -> dict:
    """已完赛场次：预测最大概率分箱 vs 实际命中率（ECE）。"""
    since = date.today() - timedelta(days=max(7, int(days)))
    q = db.query(Match).filter(
        Match.status == "finished",
        Match.match_date >= since,
    )
    if league_id:
        q = q.filter(Match.league_id == league_id)
    matches = q.order_by(Match.match_date.desc()).limit(3000).all()

    n_bins = max(2, int(bins))
    bin_conf = [0.0] * n_bins
    bin_acc = [0.0] * n_bins
    bin_w = [0.0] * n_bins
    total = 0
    correct = 0
    brier_sum = 0.0

    for match in matches:
        pred = PredictionService.get_by_match(db, match.id)
        if not pred:
            continue
        actual = _actual_outcome(match)
        if not actual:
            continue
        h = float(pred.home_win_prob or 0)
        d = float(pred.draw_prob or 0)
        a = float(pred.away_win_prob or 0)
        s = h + d + a
        if s <= 0:
            continue
        probs = (h / s, d / s, a / s)
        y = _one_hot(actual)
        brier_sum += sum((probs[i] - y[i]) ** 2 for i in range(3)) / 3.0
        pred_label = predict_label(probs)
        hit = 1.0 if pred_label == actual else 0.0
        total += 1
        correct += int(hit)
        conf = max(probs)
        bi = min(n_bins - 1, int(conf * n_bins))
        bin_w[bi] += 1
        bin_conf[bi] += conf
        bin_acc[bi] += hit

    ece = 0.0
    calibration_bins: List[dict] = []
    for i in range(n_bins):
        if bin_w[i] <= 0:
            calibration_bins.append({
                "bin": i,
                "count": 0,
                "avg_confidence": None,
                "avg_accuracy": None,
            })
            continue
        avg_c = bin_conf[i] / bin_w[i]
        avg_a = bin_acc[i] / bin_w[i]
        ece += (bin_w[i] / max(total, 1)) * abs(avg_a - avg_c)
        calibration_bins.append({
            "bin": i,
            "count": int(bin_w[i]),
            "avg_confidence": round(avg_c, 4),
            "avg_accuracy": round(avg_a, 4),
        })

    return {
        "period_days": int(days),
        "league_id": league_id,
        "sample_size": total,
        "accuracy": round(correct / total, 4) if total else None,
        "brier": round(brier_sum / total, 4) if total else None,
        "ece": round(ece, 4) if total else None,
        "calibration_bins": calibration_bins,
    }


def breakdown_report(
    db: Session,
    *,
    days: int = 60,
    limit: int = 2000,
) -> dict:
    """分联赛 / 分玩法（胜平负 · 主线比分 · 总进球高低）准确率。

    不改 accuracy_trend 表结构：从完赛 + 已落库预测即时聚合。
    """
    since = date.today() - timedelta(days=max(7, int(days)))
    matches = (
        db.query(Match)
        .filter(
            Match.status == "finished",
            Match.match_date >= since,
            Match.home_goals.isnot(None),
            Match.away_goals.isnot(None),
        )
        .order_by(Match.match_date.desc())
        .limit(max(100, min(int(limit), 5000)))
        .all()
    )

    by_league: Dict[str, Dict[str, Any]] = {}
    play = {
        "1x2": {"correct": 0, "total": 0, "brier_sum": 0.0},
        "score": {"correct": 0, "total": 0},
        "totals": {"correct": 0, "total": 0},
    }

    for match in matches:
        pred = PredictionService.get_by_match(db, match.id)
        if not pred:
            continue
        actual = _actual_outcome(match)
        if not actual:
            continue
        h = float(pred.home_win_prob or 0)
        d = float(pred.draw_prob or 0)
        a = float(pred.away_win_prob or 0)
        s = h + d + a
        if s <= 0:
            continue
        probs = (h / s, d / s, a / s)
        y = _one_hot(actual)
        brier = sum((probs[i] - y[i]) ** 2 for i in range(3)) / 3.0
        pred_label = predict_label(probs)
        hit_1x2 = pred_label == actual

        lid = str(match.league_id or "UNKNOWN")
        bucket = by_league.setdefault(
            lid, {"league_id": lid, "correct": 0, "total": 0, "brier_sum": 0.0}
        )
        bucket["total"] += 1
        bucket["correct"] += int(hit_1x2)
        bucket["brier_sum"] += brier

        play["1x2"]["total"] += 1
        play["1x2"]["correct"] += int(hit_1x2)
        play["1x2"]["brier_sum"] += brier

        main = str(getattr(pred, "main_score", None) or "").strip()
        if main and ":" in main:
            try:
                ph, pa = main.replace("-", ":").split(":")[:2]
                ph_i, pa_i = int(ph), int(pa)
                play["score"]["total"] += 1
                if ph_i == int(match.home_goals) and pa_i == int(match.away_goals):
                    play["score"]["correct"] += 1
            except (TypeError, ValueError):
                pass

        # 总进球：预测字段可能是 "2.5+" / "over" / 数字；尽量解析
        tg_hit = _totals_hit(pred, int(match.home_goals) + int(match.away_goals))
        if tg_hit is not None:
            play["totals"]["total"] += 1
            play["totals"]["correct"] += int(tg_hit)

    league_rows = []
    for lid, b in by_league.items():
        n = b["total"]
        if n <= 0:
            continue
        league_rows.append({
            "league_id": lid,
            "sample_size": n,
            "accuracy": round(b["correct"] / n, 4),
            "brier": round(b["brier_sum"] / n, 4),
        })
    league_rows.sort(key=lambda r: (-r["sample_size"], r["league_id"]))

    play_rows = {}
    for key, b in play.items():
        n = b["total"]
        play_rows[key] = {
            "sample_size": n,
            "accuracy": round(b["correct"] / n, 4) if n else None,
            "brier": round(b["brier_sum"] / n, 4) if n and "brier_sum" in b else None,
        }

    return {
        "period_days": int(days),
        "sample_size": play["1x2"]["total"],
        "by_league": league_rows[:30],
        "by_play": play_rows,
        "disclaimer": "基于已落库预测与完赛比分即时聚合；仅供学习研究。",
    }


def _totals_hit(pred, actual_goals: int) -> Optional[bool]:
    """解析 total_goals 预测是否命中大小球（以 2.5 为默认线）。"""
    raw = getattr(pred, "total_goals", None)
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text or text in ("-", "none", "null"):
        return None
    line = 2.5
    over = None
    if "大" in text or "over" in text or text.endswith("+"):
        over = True
    elif "小" in text or "under" in text or text.endswith("-"):
        over = False
    import re
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if m:
        try:
            line = float(m.group(1))
        except ValueError:
            pass
    if over is None:
        # 仅数字：按预测期望进球 vs 实际粗判（±0.5）
        try:
            expected = float(text.replace("+", "").replace("-", ""))
            return abs(expected - actual_goals) <= 0.5
        except ValueError:
            return None
    if over:
        return actual_goals > line
    return actual_goals < line


def drift_report(db: Session, *, recent_days: int = 30) -> dict:
    """近期完赛预测准确率 vs AccuracyTrend 基线。"""
    recent = calibration_report(db, days=recent_days)
    current = (
        db.query(AccuracyTrend)
        .order_by(AccuracyTrend.date.desc())
        .limit(30)
        .all()
    )
    baseline_acc = None
    if current:
        vals = [float(r.accuracy) for r in current if r.accuracy is not None]
        if vals:
            # DB 可能存 0-100 或 0-1
            baseline_acc = sum(v / 100 if v > 1 else v for v in vals) / len(vals)

    recent_acc = recent.get("accuracy")
    drift = None
    status = "unknown"
    if recent_acc is not None and baseline_acc is not None:
        drift = round(recent_acc - baseline_acc, 4)
        if drift < -0.05:
            status = "degraded"
        elif drift > 0.05:
            status = "improved"
        else:
            status = "stable"

    return {
        "recent_days": recent_days,
        "recent_accuracy": recent_acc,
        "recent_sample": recent.get("sample_size"),
        "recent_brier": recent.get("brier"),
        "recent_ece": recent.get("ece"),
        "baseline_accuracy": round(baseline_acc, 4) if baseline_acc is not None else None,
        "baseline_points": len(current),
        "drift": drift,
        "status": status,
    }
