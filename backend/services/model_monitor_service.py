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
