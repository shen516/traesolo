"""共享 Redis 连接（Token / 验证码 / 预测缓存 / RQ 队列）。"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

_client = None
_config: Optional[Dict[str, Any]] = None


def load_redis_config() -> Dict[str, Any]:
    global _config
    if _config is not None:
        return _config
    cfg_path = Path(__file__).resolve().parent.parent / "config.yaml"
    data: Dict[str, Any] = {}
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        data = {}
    redis_cfg = dict(data.get("redis") or {})
    env_url = os.environ.get("REDIS_URL") or os.environ.get("TRAESOLO_REDIS_URL")
    if env_url:
        redis_cfg["url"] = env_url
        redis_cfg.setdefault("enabled", True)
    if os.environ.get("TRAESOLO_REDIS_DISABLED", "").lower() in ("1", "true", "yes"):
        redis_cfg["enabled"] = False
    _config = redis_cfg
    return redis_cfg


def get_redis_client():
    """返回 Redis 客户端；不可用时返回 None。"""
    global _client
    cfg = load_redis_config()
    if not cfg.get("enabled", False):
        return None
    if _client is not None:
        return _client
    url = cfg.get("url") or "redis://localhost:6379/0"
    try:
        import redis

        client = redis.from_url(url, decode_responses=True, socket_connect_timeout=0.5, socket_timeout=1.0)
        client.ping()
        _client = client
        logger.info("Redis client ready (%s)", url.split("@")[-1])
        return _client
    except Exception as e:
        logger.warning("Redis unavailable: %s", e)
        return None


def redis_status() -> Dict[str, Any]:
    client = get_redis_client()
    if client is None:
        return {"backend": "memory", "status": "degraded", "detail": "redis not connected"}
    try:
        client.ping()
        return {"backend": "redis", "status": "ok"}
    except Exception as e:
        return {"backend": "redis", "status": "error", "detail": str(e)}
