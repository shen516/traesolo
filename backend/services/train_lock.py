"""训练分布式锁与进度。

Redis 可用时，API、调度、P0 与 RQ worker 共用一把锁，避免同时写球队参数。
连不上 Redis 时回退到进程内锁（仅能挡住同一进程）。
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from typing import Any, Dict, Optional

from services.redis_client import get_redis_client, load_redis_config

logger = logging.getLogger(__name__)

LOCK_KEY = "traesolo:train:lock"
STATUS_KEY = "traesolo:train:status"

_RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
  return redis.call("del", KEYS[1])
end
return 0
"""

_REFRESH_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
  return redis.call("expire", KEYS[1], ARGV[2])
end
return 0
"""


def lock_settings() -> Dict[str, int]:
    """ttl：心跳续期窗口。stale：无心跳时判定训练记录僵死的秒数（默认 3 小时）。"""
    cfg = load_redis_config()
    block = dict(cfg.get("training_lock") or {})
    ttl = int(block.get("ttl_seconds") or 120)
    stale = int(block.get("stale_running_seconds") or 3 * 3600)
    ttl = max(30, ttl)
    # 至少覆盖队列超时，避免仍在排队的任务被 3 小时阈值提前判死之前锁先丢
    queue_timeout = int((cfg.get("job_queue") or {}).get("default_timeout") or 7200)
    stale = max(ttl * 2, queue_timeout, stale)
    return {
        "ttl_seconds": ttl,
        "stale_running_seconds": stale,
        "heartbeat_seconds": max(5, ttl // 3),
        "grace_seconds": ttl * 2,
    }


class TrainLock:
    def __init__(self):
        self._mem_guard = threading.Lock()
        self._mem_token: Optional[str] = None
        self._mem_expires = 0.0
        self._mem_status: Dict[str, Any] = {}
        self._heartbeats: Dict[str, threading.Event] = {}
        self._hb_guard = threading.Lock()

    @property
    def using_redis(self) -> bool:
        return get_redis_client() is not None

    def acquire(self) -> Optional[str]:
        """抢锁。成功返回 owner token，已被占用返回 None。"""
        token = uuid.uuid4().hex
        ttl = lock_settings()["ttl_seconds"]
        client = get_redis_client()
        if client is not None:
            try:
                ok = client.set(LOCK_KEY, token, nx=True, ex=ttl)
                if ok:
                    return token
                return None
            except Exception as e:
                logger.warning("训练锁 Redis 获取失败，回退进程内锁: %s", e)
        with self._mem_guard:
            now = time.time()
            if self._mem_token and self._mem_expires > now:
                return None
            self._mem_token = token
            self._mem_expires = now + ttl
            return token

    def refresh(self, token: str) -> bool:
        if not token:
            return False
        ttl = lock_settings()["ttl_seconds"]
        client = get_redis_client()
        if client is not None:
            try:
                renewed = client.eval(_REFRESH_LUA, 1, LOCK_KEY, token, str(ttl))
                return bool(renewed)
            except Exception as e:
                logger.warning("训练锁续期失败: %s", e)
                return False
        with self._mem_guard:
            if self._mem_token != token:
                return False
            self._mem_expires = time.time() + ttl
            return True

    def release(self, token: str) -> bool:
        if not token:
            return False
        self.stop_heartbeat(token)
        client = get_redis_client()
        if client is not None:
            try:
                removed = client.eval(_RELEASE_LUA, 1, LOCK_KEY, token)
                return bool(removed)
            except Exception as e:
                logger.warning("训练锁释放失败: %s", e)
                return False
        with self._mem_guard:
            if self._mem_token != token:
                return False
            self._mem_token = None
            self._mem_expires = 0.0
            return True

    def is_locked(self) -> bool:
        client = get_redis_client()
        if client is not None:
            try:
                return bool(client.get(LOCK_KEY))
            except Exception as e:
                logger.debug("读取训练锁失败: %s", e)
                return False
        with self._mem_guard:
            return bool(self._mem_token) and self._mem_expires > time.time()

    def current_token(self) -> Optional[str]:
        client = get_redis_client()
        if client is not None:
            try:
                return client.get(LOCK_KEY)
            except Exception:
                return None
        with self._mem_guard:
            if self._mem_token and self._mem_expires > time.time():
                return self._mem_token
            return None

    def write_status(self, payload: Dict[str, Any]) -> None:
        body = dict(payload or {})
        body["updated_at"] = body.get("updated_at") or time.strftime("%Y-%m-%dT%H:%M:%S")
        raw = json.dumps(body, ensure_ascii=False, default=str)
        ttl = lock_settings()["stale_running_seconds"]
        with self._mem_guard:
            self._mem_status = body
        client = get_redis_client()
        if client is None:
            return
        try:
            client.set(STATUS_KEY, raw, ex=ttl)
        except Exception as e:
            logger.debug("写入训练状态失败: %s", e)

    def set_queued_user(self, user_id: int, **extra: Any) -> None:
        """记录训练提交者，供训练循环里校验账号是否仍有效。

        必须写入共享状态：RQ 模式下 API 进程排队、worker 进程执行，
        只在本地内存记录的话 worker 读不到。
        """
        uid = int(user_id)
        self.write_status({"queued_user_id": uid, **extra})
        logger.info("Training queued for user %s", uid)

    def get_queued_user(self) -> Optional[int]:
        """读取训练提交者 user_id；无记录时返回 None。"""
        info = self.read_status() or {}
        uid = info.get("queued_user_id")
        if uid is None:
            return None
        try:
            return int(uid)
        except (TypeError, ValueError):
            return None

    def read_status(self) -> Optional[Dict[str, Any]]:
        client = get_redis_client()
        if client is not None:
            try:
                raw = client.get(STATUS_KEY)
                if raw:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        return data
            except Exception as e:
                logger.debug("读取训练状态失败: %s", e)
        with self._mem_guard:
            return dict(self._mem_status) if self._mem_status else None

    def start_heartbeat(
        self,
        token: str,
        *,
        stop_when_phase_not: Optional[str] = None,
        max_seconds: Optional[int] = None,
    ) -> None:
        """续期锁。

        stop_when_phase_not：状态 phase 离开该值后退出，不释放锁（交给真正的训练心跳）。
        max_seconds：仅在 phase 仍等于 stop_when_phase_not 时到期释放，避免 worker 未启动时永久占锁。
        """
        if not token:
            return
        status = self.read_status() or {}
        if stop_when_phase_not and status.get("phase") not in (None, stop_when_phase_not):
            return
        interval = lock_settings()["heartbeat_seconds"]
        deadline = time.time() + max_seconds if max_seconds else None
        stop = threading.Event()
        with self._hb_guard:
            previous = self._heartbeats.get(token)
            self._heartbeats[token] = stop
        if previous is not None:
            previous.set()

        def _beat():
            while not stop.wait(interval):
                phase = (self.read_status() or {}).get("phase")
                if stop_when_phase_not and phase not in (None, stop_when_phase_not):
                    return
                if deadline and time.time() >= deadline:
                    if (
                        stop_when_phase_not
                        and phase == stop_when_phase_not
                        and self.current_token() == token
                    ):
                        self.write_status({
                            "is_training": False,
                            "progress": 0,
                            "message": "训练排队超时，锁已释放",
                            "current_record_id": None,
                            "phase": "failed",
                        })
                        self.release(token)
                    return
                if not self.refresh(token):
                    logger.warning("训练锁心跳续期失败，停止心跳")
                    return

        threading.Thread(
            target=_beat,
            name="traesolo-train-lock-heartbeat",
            daemon=True,
        ).start()

    def stop_heartbeat(self, token: str) -> None:
        with self._hb_guard:
            stop = self._heartbeats.pop(token, None)
        if stop is not None:
            stop.set()


train_lock = TrainLock()
