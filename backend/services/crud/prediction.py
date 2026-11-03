from services.crud._common import *

class PredictionService:
    @staticmethod
    def _loads_json_field(raw, default=None):
        """解析 TEXT JSON；不写回 ORM，避免污染 Session 导致 flush 失败。"""
        if raw is None or raw == "":
            return default
        if not isinstance(raw, str):
            return raw
        import json
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def meta_dict(prediction) -> dict:
        """安全读取 meta_json（字符串或已是 dict），不修改 ORM。"""
        if not prediction:
            return {}
        meta = PredictionService._loads_json_field(getattr(prediction, "meta_json", None), {})
        return meta if isinstance(meta, dict) else {}

    @staticmethod
    def to_api_dict(prediction) -> dict:
        """ORM → API 字典，并把 meta_json 展开到顶层便于前端展示。"""
        if not prediction:
            return {}
        meta = PredictionService.meta_dict(prediction)
        alt_scores = PredictionService._loads_json_field(prediction.alt_scores, []) or []
        key_variables = PredictionService._loads_json_field(prediction.key_variables, []) or []
        score_matrix = PredictionService._loads_json_field(prediction.score_matrix, []) or []
        data = {
            "id": prediction.id,
            "match_id": prediction.match_id,
            "model_version": prediction.model_version,
            "lambda_home": float(prediction.lambda_home) if prediction.lambda_home is not None else None,
            "lambda_away": float(prediction.lambda_away) if prediction.lambda_away is not None else None,
            "home_win_prob": float(prediction.home_win_prob) if prediction.home_win_prob is not None else None,
            "draw_prob": float(prediction.draw_prob) if prediction.draw_prob is not None else None,
            "away_win_prob": float(prediction.away_win_prob) if prediction.away_win_prob is not None else None,
            "main_score": prediction.main_score,
            "alt_scores": alt_scores if isinstance(alt_scores, list) else [],
            "total_goals": prediction.total_goals,
            "tendency": prediction.tendency,
            "confidence": prediction.confidence,
            "risk_level": prediction.risk_level,
            "key_variables": key_variables if isinstance(key_variables, list) else [],
            "analysis": prediction.analysis,
            "score_matrix": score_matrix if isinstance(score_matrix, list) else [],
            "created_at": prediction.created_at.isoformat() if prediction.created_at else None,
            "updated_at": prediction.updated_at.isoformat() if prediction.updated_at else None,
        }
        for key in (
            "xg_home", "xg_away", "xg_coverage", "weights_used",
            "weight_source", "league_id", "elo_home", "elo_away",
            "hyperparams_used", "env_adjust", "soft_priors",
            "primary_scenario", "scenario_reason", "espn_pipeline",
            "scenarios", "scenario_order", "ensemble_probs", "scenario_locked",
        ):
            if key in meta and meta[key] is not None:
                data[key] = meta[key]
        return data

    @staticmethod
    def get_by_match(db: Session, match_id: str):
        return db.query(MatchPrediction).filter(MatchPrediction.match_id == match_id).order_by(desc(MatchPrediction.created_at)).first()

    @staticmethod
    def get_by_id(db: Session, prediction_id: int):
        return db.query(MatchPrediction).filter(MatchPrediction.id == prediction_id).first()

    @staticmethod
    def get_history_by_match(db: Session, match_id: str, limit: int = 10):
        rows = db.query(MatchPrediction).filter(MatchPrediction.match_id == match_id).order_by(desc(MatchPrediction.created_at)).limit(limit).all()
        return [PredictionService.to_api_dict(p) for p in rows]

    @staticmethod
    def get_all(db: Session):
        return db.query(MatchPrediction).order_by(desc(MatchPrediction.created_at)).all()

    @staticmethod
    def create(db: Session, data: dict):
        import json
        payload = dict(data)
        for field in ("alt_scores", "key_variables", "score_matrix", "meta_json"):
            if field in payload and not isinstance(payload[field], str):
                payload[field] = json.dumps(payload[field], ensure_ascii=False)
        prediction = MatchPrediction(**payload)
        db.add(prediction)
        db.commit()
        db.refresh(prediction)
        return prediction

    @staticmethod
    def create_or_update(db: Session, match_id: str, data: dict, *, append_history: bool = True):
        """保存预测。

        append_history=True（默认）：始终新增一条记录，保留旧预测作为历史。
        append_history=False：原地更新该场最新一条（无则新建），供手动 PUT 覆盖。
        """
        import json
        payload = dict(data)
        for field in ("alt_scores", "key_variables", "score_matrix", "meta_json"):
            if field in payload and not isinstance(payload[field], str):
                payload[field] = json.dumps(payload[field], ensure_ascii=False)
        payload.pop("match_id", None)

        if append_history:
            payload["match_id"] = match_id
            return PredictionService.create(db, payload)

        existing = (
            db.query(MatchPrediction)
            .filter(MatchPrediction.match_id == match_id)
            .order_by(desc(MatchPrediction.created_at))
            .first()
        )
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            db.commit()
            db.refresh(existing)
            return existing
        payload["match_id"] = match_id
        return PredictionService.create(db, payload)
