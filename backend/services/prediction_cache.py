"""预测结果 Redis 缓存（match_id + model_version）。"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from services.redis_client import get_redis_client, load_redis_config

logger = logging.getLogger(__name__)

KEY_PREFIX = "traesolo:pred:"
_mem: Dict[str, str] = {}


def _cfg() -> dict:
    cfg = load_redis_config()
    pc = dict(cfg.get("prediction_cache") or {})
    enabled = pc.get("enabled", True)
    if os.environ.get("TRAESOLO_PREDICTION_CACHE_DISABLED", "").lower() in ("1", "true", "yes"):
        enabled = False
    ttl = int(pc.get("ttl_seconds") or 3600)
    return {"enabled": bool(enabled), "ttl_seconds": max(60, ttl)}


def _key(match_id: str, model_version: str) -> str:
    return f"{KEY_PREFIX}{match_id}:{model_version or 'unknown'}"


def get(match_id: str, model_version: str) -> Optional[dict]:
    cfg = _cfg()
    if not cfg["enabled"] or not match_id:
        return None
    k = _key(match_id, model_version)
    client = get_redis_client()
    if client is not None:
        try:
            raw = client.get(k)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning("prediction_cache get failed: %s", e)
    raw = _mem.get(k)
    if raw:
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None
    return None


def set(match_id: str, model_version: str, payload: dict, ttl: Optional[int] = None) -> None:
    cfg = _cfg()
    if not cfg["enabled"] or not match_id:
        return
    k = _key(match_id, model_version)
    raw = json.dumps(payload, ensure_ascii=False)
    ttl = int(ttl if ttl is not None else cfg["ttl_seconds"])
    client = get_redis_client()
    if client is not None:
        try:
            client.setex(k, ttl, raw)
            return
        except Exception as e:
            logger.warning("prediction_cache set failed: %s", e)
    _mem[k] = raw


def invalidate_match(match_id: str) -> int:
    """删除某场比赛全部版本缓存。"""
    if not match_id:
        return 0
    prefix = f"{KEY_PREFIX}{match_id}:"
    n = 0
    client = get_redis_client()
    if client is not None:
        try:
            for k in client.scan_iter(f"{prefix}*"):
                client.delete(k)
                n += 1
        except Exception as e:
            logger.warning("prediction_cache invalidate_match failed: %s", e)
    for k in list(_mem.keys()):
        if k.startswith(prefix):
            _mem.pop(k, None)
            n += 1
    return n


def invalidate_all() -> int:
    n = len(_mem)
    _mem.clear()
    client = get_redis_client()
    if client is not None:
        try:
            for k in client.scan_iter(f"{KEY_PREFIX}*"):
                client.delete(k)
                n += 1
        except Exception as e:
            logger.warning("prediction_cache invalidate_all failed: %s", e)
    return n


def status() -> dict:
    cfg = _cfg()
    return {
        "enabled": cfg["enabled"],
        "ttl_seconds": cfg["ttl_seconds"],
        "backend": "redis" if get_redis_client() else "memory",
        "memory_keys": len(_mem),
    }
