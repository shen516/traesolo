"""P0 流水线状态跨进程共享（Redis）；无 Redis 时仅进程内有效。"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from services.redis_client import get_redis_client

logger = logging.getLogger(__name__)

P0_REDIS_KEY = "traesolo:p0:status"
P0_TTL_SECONDS = 7 * 24 * 3600


def load_shared_p0_status() -> Optional[Dict[str, Any]]:
    client = get_redis_client()
    if client is None:
        return None
    try:
        raw = client.get(P0_REDIS_KEY)
        if not raw:
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.debug("load shared p0 status failed: %s", e)
        return None


def save_shared_p0_status(status: Dict[str, Any]) -> bool:
    client = get_redis_client()
    if client is None:
        return False
    try:
        payload = json.dumps(status, ensure_ascii=False, default=str)
        client.set(P0_REDIS_KEY, payload, ex=P0_TTL_SECONDS)
        return True
    except Exception as e:
        logger.debug("save shared p0 status failed: %s", e)
        return False
