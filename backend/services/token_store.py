"""Token 存储：优先 Redis（多实例共享 + TTL），不可用时回退内存。"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

DEFAULT_TTL = 24 * 3600
TOKEN_KEY_PREFIX = "traesolo:token:"


def _load_redis_config() -> dict:
    cfg_path = Path(__file__).resolve().parent.parent / "config.yaml"
    data = {}
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        data = {}
    redis_cfg = dict(data.get("redis") or {})
    # 环境变量覆盖（Docker Compose）
    env_url = os.environ.get("REDIS_URL") or os.environ.get("TRAESOLO_REDIS_URL")
    if env_url:
        redis_cfg["url"] = env_url
        redis_cfg.setdefault("enabled", True)
    if os.environ.get("TRAESOLO_REDIS_DISABLED", "").lower() in ("1", "true", "yes"):
        redis_cfg["enabled"] = False
    return redis_cfg


class TokenStore:
    def __init__(self):
        self._mem: Dict[str, dict] = {}
        self._redis = None
        self.backend = "memory"
        self.ttl_seconds = DEFAULT_TTL
        self._init_backend()

    def _init_backend(self):
        cfg = _load_redis_config()
        self.ttl_seconds = int(cfg.get("token_ttl_seconds") or DEFAULT_TTL)
        if not cfg.get("enabled", False):
            logger.info("Token store: memory (redis disabled in config)")
            return
        url = cfg.get("url") or "redis://localhost:6379/0"
        try:
            import redis

            client = redis.from_url(url, decode_responses=True, socket_connect_timeout=0.4, socket_timeout=0.8)
            client.ping()
            self._redis = client
            self.backend = "redis"
            logger.info("Token store: redis (%s)", url.split("@")[-1])
        except Exception as e:
            self._redis = None
            self.backend = "memory"
            logger.warning("Token store fallback to memory: %s", e)

    def _key(self, token: str) -> str:
        return f"{TOKEN_KEY_PREFIX}{token}"

    def store(
        self,
        token: str,
        user_id: int,
        username: str,
        roles: list,
        permissions: list,
        ttl: Optional[int] = None,
    ):
        ttl = int(ttl if ttl is not None else self.ttl_seconds)
        payload = {
            "user_id": int(user_id),
            "username": username,
            "expires": time.time() + ttl,
            "roles": roles or [],
            "permissions": permissions or [],
        }
        if self._redis is not None:
            try:
                self._redis.setex(self._key(token), ttl, json.dumps(payload, ensure_ascii=False))
                return
            except Exception as e:
                logger.warning("Redis store_token failed, use memory: %s", e)
        self._mem[token] = payload

    def get(self, token: str) -> Optional[dict]:
        if self._redis is not None:
            try:
                raw = self._redis.get(self._key(token))
                if raw:
                    data = json.loads(raw)
                    if time.time() > float(data.get("expires") or 0):
                        self.revoke(token)
                        return None
                    return data
                # Redis 未命中时不要误读过期内存残留
            except Exception as e:
                logger.warning("Redis get_token failed, try memory: %s", e)
        data = self._mem.get(token)
        if not data:
            return None
        if time.time() > float(data.get("expires") or 0):
            self._mem.pop(token, None)
            return None
        return data

    def revoke(self, token: str):
        if self._redis is not None:
            try:
                self._redis.delete(self._key(token))
            except Exception as e:
                logger.warning("Redis revoke_token failed: %s", e)
        self._mem.pop(token, None)

    def revoke_by_user(self, user_id: int) -> int:
        """吊销指定用户的全部 token。

        用于账号被禁用/删除时：否则禁用用户手里未过期的 token（默认 24h TTL）
        仍能访问所有受保护接口。返回本次处理到的 token 数量；Redis 不可用时
        只能覆盖本进程内存里的 token。
        """
        uid = int(user_id)
        revoked = 0

        if self._redis is not None:
            try:
                for key in list(self._redis.scan_iter(f"{TOKEN_KEY_PREFIX}*", count=500)):
                    raw = self._redis.get(key)
                    if not raw:
                        continue
                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue
                    if int(data.get("user_id") or 0) != uid:
                        continue
                    self._redis.delete(key)
                    revoked += 1
            except Exception as e:
                logger.warning("Redis revoke_by_user(%s) failed: %s", uid, e)

        # 内存是兜底存储（Redis 不可用或写失败时），需一并清理
        for token, data in list(self._mem.items()):
            if int((data or {}).get("user_id") or 0) != uid:
                continue
            self._mem.pop(token, None)
            revoked += 1

        if revoked:
            logger.info("Revoked %d token(s) for user %s", revoked, uid)
        return revoked


    def status(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "ttl_seconds": self.ttl_seconds,
            "memory_tokens": len(self._mem),
        }


token_store = TokenStore()
