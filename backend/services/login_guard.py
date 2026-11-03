"""登录失败限流：优先 Redis，回退进程内存。"""

from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 15 * 60
MAX_FAILURES = 8
LOCK_SECONDS = 15 * 60
KEY_PREFIX = "traesolo:login_fail:"

_mem: dict[str, dict] = {}


def _client():
    try:
        from services.redis_client import get_redis_client
        return get_redis_client()
    except Exception:
        return None


def _norm(username: str) -> str:
    return (username or "").strip().lower() or "_"


def is_locked(username: str) -> Tuple[bool, int]:
    """返回 (是否锁定, 剩余秒数)。"""
    key = _norm(username)
    client = _client()
    if client is not None:
        try:
            ttl = client.ttl(f"{KEY_PREFIX}lock:{key}")
            if ttl and ttl > 0:
                return True, int(ttl)
            return False, 0
        except Exception as e:
            logger.debug("login lock redis check failed: %s", e)

    row = _mem.get(key) or {}
    until = float(row.get("locked_until") or 0)
    now = time.time()
    if until > now:
        return True, int(until - now)
    return False, 0


def record_failure(username: str) -> Tuple[int, bool]:
    """记录一次失败。返回 (当前窗口失败次数, 是否刚触发锁定)。"""
    key = _norm(username)
    client = _client()
    if client is not None:
        try:
            fail_key = f"{KEY_PREFIX}count:{key}"
            n = int(client.incr(fail_key))
            if n == 1:
                client.expire(fail_key, WINDOW_SECONDS)
            locked = False
            if n >= MAX_FAILURES:
                client.setex(f"{KEY_PREFIX}lock:{key}", LOCK_SECONDS, "1")
                client.delete(fail_key)
                locked = True
            return n, locked
        except Exception as e:
            logger.debug("login fail redis incr failed: %s", e)

    now = time.time()
    row = _mem.get(key) or {"fails": [], "locked_until": 0}
    fails = [t for t in row.get("fails", []) if now - t < WINDOW_SECONDS]
    fails.append(now)
    locked = False
    if len(fails) >= MAX_FAILURES:
        row["locked_until"] = now + LOCK_SECONDS
        fails = []
        locked = True
    row["fails"] = fails
    _mem[key] = row
    return len(fails), locked


def clear_failures(username: str) -> None:
    key = _norm(username)
    client = _client()
    if client is not None:
        try:
            client.delete(f"{KEY_PREFIX}count:{key}", f"{KEY_PREFIX}lock:{key}")
        except Exception as e:
            logger.debug("login fail redis clear failed: %s", e)
    _mem.pop(key, None)


def remaining_attempts(username: str) -> Optional[int]:
    key = _norm(username)
    client = _client()
    if client is not None:
        try:
            raw = client.get(f"{KEY_PREFIX}count:{key}")
            n = int(raw or 0)
            return max(0, MAX_FAILURES - n)
        except Exception:
            return None
    row = _mem.get(key) or {}
    now = time.time()
    fails = [t for t in row.get("fails", []) if now - t < WINDOW_SECONDS]
    return max(0, MAX_FAILURES - len(fails))
