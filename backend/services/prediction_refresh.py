"""训练后 / 模型切换后：按当前模型批量刷新未赛预测 meta。"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _prediction_is_stale(prediction, current_version: str) -> bool:
    from services import PredictionService

    if not prediction:
        return True
    version = getattr(prediction, "model_version", None) or ""
    if current_version and version != current_version:
        return True
    meta = PredictionService.meta_dict(prediction)
    if not meta:
        return True
    if meta.get("weights_used") is None and meta.get("weight_source") is None:
        return True
    return False


def refresh_stale_upcoming(
    db: Session = None,
    *,
    limit: int = 150,
    only_stale: bool = True,
    include_unpredicted: bool = True,
    league_id: Optional[str] = None,
) -> dict:
    """按当前模型重算未赛预测，补齐 meta_json / 版本滞后。

    供 train_all、priority_train、API 共用；单次默认最多 150 场。
    """
    from services import MatchService, ModelService, PredictionService

    own_session = db is None
    if own_session:
        from db.database import SessionLocal
        db = SessionLocal()

    try:
        from services.ensemble_registry import get_ensemble
        ensemble = get_ensemble()

        current = ModelService.get_current(db)
        current_version = current.version if current else ""

        def _payload_from_result(result: dict) -> dict:
            meta = {
                "xg_home": result.get("xg_home"),
                "xg_away": result.get("xg_away"),
                "xg_coverage": result.get("xg_coverage"),
                "weights_used": result.get("weights_used"),
                "weight_source": result.get("weight_source"),
                "league_id": result.get("league_id"),
                "elo_home": result.get("elo_home"),
                "elo_away": result.get("elo_away"),
                "hyperparams_used": result.get("hyperparams_used"),
                "env_adjust": result.get("env_adjust"),
                "soft_priors": result.get("soft_priors"),
            }
            return {
                "model_version": current_version or "v5.0.3",
                "lambda_home": result["lambda_home"],
                "lambda_away": result["lambda_away"],
                "home_win_prob": result["home_win_prob"],
                "draw_prob": result["draw_prob"],
                "away_win_prob": result["away_win_prob"],
                "main_score": result["main_score"],
                "alt_scores": result["alt_scores"],
                "total_goals": result["total_goals"],
                "tendency": result["tendency"],
                "confidence": result["confidence"],
                "risk_level": result["risk_level"],
                "key_variables": result["key_variables"],
                "analysis": result["analysis"],
                "score_matrix": result["score_matrix"],
                "meta_json": meta,
            }

        fetch_n = min(max(int(limit) * 3, int(limit)), 500)
        page_size = min(100, fetch_n)
        collected = []
        page = 1
        while len(collected) < fetch_n:
            chunk = MatchService.get_paginated_upcoming(
                db, page=page, page_size=page_size, league_id=league_id, keyword=None
            )
            if not chunk:
                break
            collected.extend(chunk)
            if len(chunk) < page_size:
                break
            page += 1

        calculated = 0
        skipped = 0
        failed = []
        for match in collected:
            if calculated >= int(limit):
                break
            existing = PredictionService.get_by_match(db, match.id)
            if existing is None:
                if not include_unpredicted:
                    skipped += 1
                    continue
            elif only_stale and not _prediction_is_stale(existing, current_version):
                skipped += 1
                continue
            try:
                result = ensemble.predict_from_db(
                    db, match.home_team_id, match.away_team_id, match_id=match.id
                )
                PredictionService.create_or_update(db, match.id, _payload_from_result(result))
                calculated += 1
            except Exception as e:
                logger.warning("refresh prediction failed for %s: %s", match.id, e)
                failed.append({"match_id": match.id, "error": str(e)})

        return {
            "calculated": calculated,
            "skipped": skipped,
            "gated": 0,
            "failed": failed,
            "failed_count": len(failed),
            "total_candidates": len(collected),
            "model_version": current_version,
            "limit": int(limit),
            "only_stale": only_stale,
        }
    finally:
        if own_session:
            db.close()
