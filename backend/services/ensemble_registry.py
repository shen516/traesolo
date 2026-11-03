"""EnsembleModel 进程内单例 — 避免 api/services 循环 import main。

训练写入 current 版本后通过 Redis 广播 version，其它进程在预测前按需 reload。
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from models.ensemble import EnsembleModel

logger = logging.getLogger(__name__)

WEIGHTS_VERSION_KEY = "traesolo:ensemble:weights_version"

_ensemble: Optional[EnsembleModel] = None
_local_weights_version: Optional[str] = None


def get_ensemble(*, sync_weights: bool = False) -> EnsembleModel:
    """返回全局融合模型实例（懒加载）。

    sync_weights=True 时若 Redis 中版本与本地不一致则从 DB 重载。
    """
    global _ensemble
    if _ensemble is None:
        _ensemble = EnsembleModel()
    if sync_weights:
        ensure_weights_current()
    return _ensemble


def set_ensemble(model: EnsembleModel) -> None:
    """测试或启动时注入实例。"""
    global _ensemble
    _ensemble = model


def get_local_weights_version() -> Optional[str]:
    return _local_weights_version


def publish_weights_version(version: Optional[str]) -> None:
    """训练/切版本后广播，供其它进程 reload。"""
    global _local_weights_version
    if not version:
        return
    _local_weights_version = str(version)
    try:
        from services.redis_client import get_redis_client
        client = get_redis_client()
        if client is not None:
            client.set(WEIGHTS_VERSION_KEY, str(version))
    except Exception as e:
        logger.debug("publish weights version failed: %s", e)


def ensure_weights_current() -> bool:
    """若远程版本新于本地则 load_weights_from_db。返回是否发生重载。"""
    global _local_weights_version
    remote = None
    try:
        from services.redis_client import get_redis_client
        client = get_redis_client()
        if client is not None:
            remote = client.get(WEIGHTS_VERSION_KEY)
    except Exception as e:
        logger.debug("read weights version failed: %s", e)

    if remote and remote != _local_weights_version:
        load_weights_from_db()
        _local_weights_version = remote
        return True
    return False


def load_weights_from_db(db=None) -> None:
    """从当前 model_versions 记录加载融合权重。"""
    global _local_weights_version
    own = db is None
    if own:
        from db.database import SessionLocal
        db = SessionLocal()
    try:
        from services import ModelService

        current = ModelService.get_current(db)
        if current and current.weights_json:
            get_ensemble().apply_weights_payload(json.loads(current.weights_json))
            n_league = len(getattr(get_ensemble(), "league_weights", {}) or {})
            _local_weights_version = current.version
            publish_weights_version(current.version)
            logger.info(
                "Loaded model %s weights (league profiles: %s)",
                current.version,
                n_league,
            )
    except Exception as e:
        logger.warning("Failed to load current model weights: %s", e)
    finally:
        if own:
            db.close()
