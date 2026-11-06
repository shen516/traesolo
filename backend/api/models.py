"""模型管理API"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import User
from services import ModelService
from services.training_service import training_service
from api.deps import get_current_user
from pydantic import BaseModel
from datetime import date
from typing import Optional
from api.authz import RequireModelRead, RequireModelManage

logger = logging.getLogger(__name__)

router = APIRouter()


class ModelCreate(BaseModel):
    version: str
    description: Optional[str] = None
    accuracy: Optional[float] = None
    training_data_start: Optional[date] = None
    training_data_end: Optional[date] = None
    weights_json: Optional[str] = None


@router.get("/", dependencies=[RequireModelRead])
async def get_models(db: Session = Depends(get_db)):
    return {"models": ModelService.get_all(db)}


@router.get("/status", dependencies=[RequireModelRead])
async def get_model_status(db: Session = Depends(get_db)):
    from services.ensemble_registry import get_ensemble
    ensemble = get_ensemble()
    from db.models import TrainingRecord
    import json

    current = ModelService.get_current(db)
    latest_train = (
        db.query(TrainingRecord)
        .filter(TrainingRecord.status == "success")
        .order_by(TrainingRecord.started_at.desc())
        .first()
    )

    accuracy = None
    version = "未训练"
    last_train = None
    if current:
        version = current.version
        if current.accuracy is not None:
            accuracy = float(current.accuracy) / 100 if float(current.accuracy) > 1 else float(current.accuracy)
    elif latest_train and latest_train.accuracy is not None:
        accuracy = float(latest_train.accuracy)
        version = latest_train.model_version or version
    if latest_train and latest_train.finished_at:
        last_train = latest_train.finished_at.date().isoformat()

    training_sample = None
    if latest_train:
        training_sample = latest_train.total_matches

    by_league = {}
    if current and current.weights_json:
        try:
            payload = json.loads(current.weights_json)
            if isinstance(payload, dict):
                by_league = payload.get("by_league") or {}
        except (TypeError, ValueError, json.JSONDecodeError):
            by_league = {}

    return {
        "version": version,
        "accuracy": accuracy,
        "last_train": last_train,
        "training_sample": training_sample,
        "status": "running",
        "models": ["poisson", "elo", "xg", "monte_carlo"],
        "weights": ensemble.weights,
        "league_weights": getattr(ensemble, "league_weights", {}),
        "hyperparams": getattr(ensemble, "global_hyperparams", {}),
        "league_hyperparams": getattr(ensemble, "league_hyperparams", {}),
        "by_league": by_league,
        "evaluation": getattr(ensemble, "evaluation", {}),
        "time_decay": getattr(ensemble, "time_decay", {}),
        "max_monte_carlo_weight": getattr(ensemble, "max_monte_carlo_weight", None),
        "models_detail": [
            {
                "name": "泊松模型",
                "key": "poisson",
                "status": "running",
                "key_params": {
                    "max_goals": ensemble.poisson.max_goals,
                    "home_advantage": float(
                        (getattr(ensemble, "global_hyperparams", {}) or {}).get(
                            "poisson_home_advantage", ensemble.home_advantage
                        )
                    ),
                },
                "loaded_data": {
                    "leagues_count": len(ensemble.league_avg),
                    "teams_count": len(ensemble.team_params),
                },
                "description": "基于泊松分布对进球数进行建模，通过两队攻防强度计算期望进球数",
            },
            {
                "name": "ELO评级",
                "key": "elo",
                "status": "running",
                "key_params": {
                    "k_factor": float(
                        (getattr(ensemble, "global_hyperparams", {}) or {}).get(
                            "elo_k", ensemble.elo.k
                        )
                    ),
                    "home_advantage": float(
                        (getattr(ensemble, "global_hyperparams", {}) or {}).get(
                            "elo_home_advantage", ensemble.elo.home_advantage
                        )
                    ),
                    "initial_rating": ensemble.elo.initial_rating,
                },
                "loaded_data": {
                    "teams_count": len(ensemble.elo.ratings),
                },
                "description": "通过双方ELO评级差计算胜率期望，反映球队长期实力对比",
            },
            {
                "name": "期望进球 xG",
                "key": "xg",
                "status": "running",
                "key_params": {
                    "prior_xg_per_shot": ensemble.xg.prior_xg_per_shot,
                    "prior_xg_per_sot": ensemble.xg.prior_xg_per_sot,
                    "shrink_k": ensemble.xg.shrink_k,
                    "min_matches": ensemble.xg.min_matches,
                },
                "loaded_data": {
                    "teams_count": len(ensemble.xg.team_xg),
                    "leagues_count": len(ensemble.xg.league_priors),
                },
                "description": "基于射门/射正历史估计进攻与防守 xG，合成单场 λ 后经泊松得胜平负",
            },
            {
                "name": "蒙特卡洛模拟",
                "key": "monte_carlo",
                "status": "running",
                "key_params": {
                    "simulations": ensemble.monte_carlo.simulations,
                },
                "loaded_data": {},
                "description": "通过大量随机模拟提升预测精度，统计各比分概率分布",
            },
        ],
    }


@router.get("/current", dependencies=[RequireModelRead])
async def get_current_model(db: Session = Depends(get_db)):
    model = ModelService.get_current(db)
    if not model:
        raise HTTPException(status_code=404, detail="No current model found")
    return model


@router.get("/train/insights/latest", dependencies=[RequireModelManage])
async def get_latest_training_insights():
    """获取最新训练快照与完善建议（每次训练后更新）。"""
    try:
        return training_service.get_latest_insights()
    except Exception:
        logger.exception("加载训练洞察失败")
        raise HTTPException(status_code=500, detail="加载训练洞察失败")


@router.get("/train/insights", dependencies=[RequireModelManage])
async def get_training_insights_alias():
    """与 /train/insights/latest 相同，兼容旧客户端。"""
    return training_service.get_latest_insights()


@router.get("/train/records", dependencies=[RequireModelManage])
async def list_training_records(
    page: int = 1,
    page_size: int = 20,
):
    return training_service.list_records(page=page, page_size=page_size)


@router.get("/train/records/{record_id}", dependencies=[RequireModelManage])
async def get_training_record(record_id: int):
    rec = training_service.get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="训练记录不存在")
    return rec


@router.post("/train", dependencies=[RequireModelManage])
async def train_models(
    start_date: date = None,
    end_date: date = None,
    use_queue: bool = True,
    current: User = Depends(get_current_user),
):
    """启动全量训练（优先 RQ 队列，否则守护线程）。"""
    from services import job_queue

    if use_queue and job_queue.status().get("enabled"):
        queued = job_queue.enqueue_training(start_date, end_date, user_id=current.id)
        if queued.get("code") == "TRAIN_BUSY" or queued.get("status") == "error":
            raise HTTPException(status_code=409, detail=queued.get("message") or "训练正在进行中")
        return {
            "message": "训练任务已加入队列",
            **queued,
        }

    started = training_service.start_train_async(
        start_date=start_date, end_date=end_date, user_id=current.id,
    )
    if started.get("status") == "error":
        raise HTTPException(status_code=409, detail=started.get("message") or "无法启动训练")

    return {"message": "训练已在后台线程启动，请稍后查看训练状态", "async": True, "mode": "thread"}


@router.get("/jobs/{job_id}", dependencies=[RequireModelManage])
async def get_async_job(job_id: str):
    from services import job_queue
    return job_queue.get_job_status(job_id)


@router.get("/monitor/calibration", dependencies=[RequireModelManage])
async def get_calibration_monitor(
    days: int = Query(90, ge=7, le=365),
    league_id: str = Query(None),
    db: Session = Depends(get_db),
):
    from services.model_monitor_service import calibration_report
    return calibration_report(db, days=days, league_id=league_id)


@router.get("/monitor/drift", dependencies=[RequireModelManage])
async def get_drift_monitor(days: int = Query(30, ge=7, le=180), db: Session = Depends(get_db)):
    from services.model_monitor_service import drift_report
    return drift_report(db, recent_days=days)


@router.get("/monitor/odds-deviation", dependencies=[RequireModelManage])
async def get_odds_deviation_monitor(
    days: int = Query(30, ge=7, le=180),
    league_id: str = Query(None),
    db: Session = Depends(get_db),
):
    """竞彩隐含概率 vs 模型偏差汇总（分析对照，非投注建议）。"""
    from services.odds_analysis import odds_deviation_report
    return odds_deviation_report(db, days=days, league_id=league_id)


@router.get("/monitor/breakdown", dependencies=[RequireModelManage])
async def get_accuracy_breakdown(
    days: int = Query(60, ge=7, le=365),
    db: Session = Depends(get_db),
):
    """分联赛 / 分玩法准确率（胜平负 · 比分 · 总进球），即时聚合。"""
    from services.model_monitor_service import breakdown_report
    return breakdown_report(db, days=days)


@router.get("/train/status", dependencies=[RequireModelManage])
async def get_training_status():
    status = training_service.get_training_status()
    try:
        from services.token_store import token_store
        status["token_store"] = token_store.status()
    except Exception:
        pass
    try:
        from services.ensemble_registry import get_ensemble
        ensemble = get_ensemble()
        status["evaluation"] = getattr(ensemble, "evaluation", {})
        status["time_decay"] = getattr(ensemble, "time_decay", {})
        status["max_monte_carlo_weight"] = getattr(ensemble, "max_monte_carlo_weight", None)
    except Exception:
        pass
    return status


@router.post("/", dependencies=[RequireModelManage])
async def create_model(data: ModelCreate, db: Session = Depends(get_db)):
    existing = ModelService.get_by_version(db, data.version)
    if existing:
        raise HTTPException(status_code=400, detail="Version already exists")
    return ModelService.create(db, data.model_dump())


@router.put("/{model_id}/current", dependencies=[RequireModelManage])
async def set_current_model(model_id: int, db: Session = Depends(get_db)):
    model = ModelService.set_current(db, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if model.weights_json:
        try:
            import json
            from services.ensemble_registry import get_ensemble, publish_weights_version
            from services import prediction_cache
            ensemble = get_ensemble()
            weights = json.loads(model.weights_json)
            ensemble.apply_weights_payload(weights)
            publish_weights_version(model.version)
            prediction_cache.invalidate_all()
        except Exception:
            pass
    return {"message": "Model set as current", "model": model}


@router.delete("/{model_id}", dependencies=[RequireModelManage])
async def delete_model(model_id: int, db: Session = Depends(get_db)):
    model = ModelService.delete(db, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return {"message": "Model deleted"}


@router.get("/{version}", dependencies=[RequireModelRead])
async def get_model_by_version(version: str, db: Session = Depends(get_db)):
    model = ModelService.get_by_version(db, version)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model
