"""赛事分析报告导出（TXT/Excel）。仅学习研究用途，不构成投注建议。"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from services import MatchService, PredictionService, TeamService


def build_report_payload(db: Session, match_id: str) -> Dict[str, Any]:
    match = MatchService.get_by_id(db, match_id)
    if not match:
        raise ValueError("赛事不存在")
    home = TeamService.get_by_id(db, match.home_team_id)
    away = TeamService.get_by_id(db, match.away_team_id)
    pred = PredictionService.get_by_match(db, match_id)
    home_name = home.name if home else match.home_team_id
    away_name = away.name if away else match.away_team_id

    def _f(v):
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return {
        "match_id": match.id,
        "league_id": match.league_id,
        "match_date": str(match.match_date) if match.match_date else "",
        "match_time": str(match.match_time) if match.match_time else "",
        "status": match.status,
        "home_team": home_name,
        "away_team": away_name,
        "score": (
            f"{match.home_goals}:{match.away_goals}"
            if match.home_goals is not None and match.away_goals is not None
            else ""
        ),
        "home_win_prob": _f(getattr(pred, "home_win_prob", None)) if pred else None,
        "draw_prob": _f(getattr(pred, "draw_prob", None)) if pred else None,
        "away_win_prob": _f(getattr(pred, "away_win_prob", None)) if pred else None,
        "lambda_home": _f(getattr(pred, "lambda_home", None)) if pred else None,
        "lambda_away": _f(getattr(pred, "lambda_away", None)) if pred else None,
        "main_score": getattr(pred, "main_score", None) if pred else None,
        "total_goals": getattr(pred, "total_goals", None) if pred else None,
        "model_version": getattr(pred, "model_version", None) if pred else None,
        "tendency": getattr(pred, "tendency", None) if pred else None,
        "analysis": getattr(pred, "analysis", None) if pred else None,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "disclaimer": "仅供学习、研究与数据分析，不构成投注建议。",
    }


def render_txt(payload: Dict[str, Any]) -> bytes:
    lines = [
        "========================================",
        "足球赛事量化分析报告",
        "========================================",
        "",
        f"赛事: {payload['home_team']} vs {payload['away_team']}",
        f"联赛: {payload.get('league_id') or '-'}",
        f"时间: {payload.get('match_date')} {payload.get('match_time')}",
        f"状态: {payload.get('status')}",
        f"比分: {payload.get('score') or '-'}",
        "",
        "【胜平负概率】",
        f"  主胜: {_pct(payload.get('home_win_prob'))}",
        f"  平局: {_pct(payload.get('draw_prob'))}",
        f"  客胜: {_pct(payload.get('away_win_prob'))}",
        "",
        "【λ / 结论】",
        f"  λ 主/客: {payload.get('lambda_home')} / {payload.get('lambda_away')}",
        f"  主线比分: {payload.get('main_score') or '-'}",
        f"  总进球: {payload.get('total_goals') or '-'}",
        f"  倾向: {payload.get('tendency') or '-'}",
        f"  模型版本: {payload.get('model_version') or '-'}",
        "",
        "【简要分析】",
        str(payload.get("analysis") or "（无）"),
        "",
        f"生成时间: {payload.get('generated_at')}",
        payload.get("disclaimer") or "",
        "========================================",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def render_xlsx(payload: Dict[str, Any]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "分析报告"
    rows = [
        ("赛事ID", payload.get("match_id")),
        ("主队", payload.get("home_team")),
        ("客队", payload.get("away_team")),
        ("联赛", payload.get("league_id")),
        ("日期", payload.get("match_date")),
        ("时间", payload.get("match_time")),
        ("状态", payload.get("status")),
        ("比分", payload.get("score")),
        ("主胜概率", payload.get("home_win_prob")),
        ("平局概率", payload.get("draw_prob")),
        ("客胜概率", payload.get("away_win_prob")),
        ("λ主", payload.get("lambda_home")),
        ("λ客", payload.get("lambda_away")),
        ("主线比分", payload.get("main_score")),
        ("总进球", payload.get("total_goals")),
        ("倾向", payload.get("tendency")),
        ("模型版本", payload.get("model_version")),
        ("分析", payload.get("analysis")),
        ("生成时间", payload.get("generated_at")),
        ("声明", payload.get("disclaimer")),
    ]
    ws.append(["字段", "值"])
    for k, v in rows:
        ws.append([k, v if v is not None else ""])
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 56
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _pct(v: Optional[float]) -> str:
    if v is None:
        return "-"
    x = float(v)
    if x <= 1:
        x *= 100
    return f"{x:.1f}%"
