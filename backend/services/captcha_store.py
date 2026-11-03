"""验证码存储：优先 Redis（多 worker 共享 + TTL），不可用时回退内存。"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from services.token_store import _load_redis_config

logger = logging.getLogger(__name__)

CAPTCHA_KEY_PREFIX = "traesolo:captcha:"
DEFAULT_TTL = 300


class CaptchaStore:
    def __init__(self):
        self._mem: dict[str, dict] = {}
        self._redis = None
        self.backend = "memory"
        self.ttl_seconds = DEFAULT_TTL
        self._init_backend()

    def _init_backend(self):
        cfg = _load_redis_config()
        if not cfg.get("enabled", False):
            logger.info("Captcha store: memory (redis disabled in config)")
            return
        url = cfg.get("url") or "redis://localhost:6379/0"
        try:
            import redis

            client = redis.from_url(url, decode_responses=True, socket_connect_timeout=0.4, socket_timeout=0.8)
            client.ping()
            self._redis = client
            self.backend = "redis"
            logger.info("Captcha store: redis (%s)", url.split("@")[-1])
        except Exception as e:
            self._redis = None
            self.backend = "memory"
            logger.warning("Captcha store fallback to memory: %s", e)

    def _key(self, captcha_id: str) -> str:
        return f"{CAPTCHA_KEY_PREFIX}{captcha_id}"

    def store(self, captcha_id: str, code: str, ttl: Optional[int] = None) -> None:
        ttl = int(ttl if ttl is not None else self.ttl_seconds)
        payload = {"code": code.upper(), "expire": time.time() + ttl}
        if self._redis is not None:
            try:
                self._redis.setex(self._key(captcha_id), ttl, json.dumps(payload, ensure_ascii=False))
                return
            except Exception as e:
                logger.warning("Redis store_captcha failed, use memory: %s", e)
        self._mem[captcha_id] = payload

    def get(self, captcha_id: str) -> Optional[dict]:
        if self._redis is not None:
            try:
                raw = self._redis.get(self._key(captcha_id))
                if raw:
                    data = json.loads(raw)
                    if time.time() > float(data.get("expire") or 0):
                        self.revoke(captcha_id)
                        return None
                    return data
            except Exception as e:
                logger.warning("Redis get_captcha failed, try memory: %s", e)
        data = self._mem.get(captcha_id)
        if not data:
            return None
        if time.time() > float(data.get("expire") or 0):
            self._mem.pop(captcha_id, None)
            return None
        return data

    def revoke(self, captcha_id: str) -> None:
        if self._redis is not None:
            try:
                self._redis.delete(self._key(captcha_id))
            except Exception as e:
                logger.warning("Redis revoke_captcha failed: %s", e)
        self._mem.pop(captcha_id, None)


captcha_store = CaptchaStore()
