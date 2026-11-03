"""定时任务执行锁：同一 task_id 同时只跑一份。

Redis 可用时 API、调度进程和 RQ worker 共用。连不上时回退进程内锁。
锁 TTL 较短，由心跳续期；进程退出后约一个 TTL 自动释放。
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from typing import Any, Dict, Iterable, Optional, Set

from services.redis_client import get_redis_client, load_redis_config

logger = logging.getLogger(__name__)

LOCK_PREFIX = "traesolo:task:lock:"
STATUS_PREFIX = "traesolo:task:status:"

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
    cfg = load_redis_config()
    block = dict(cfg.get("task_run_lock") or {})
    ttl = max(30, int(block.get("ttl_seconds") or 120))
    return {
        "ttl_seconds": ttl,
        "heartbeat_seconds": max(5, ttl // 3),
    }


class TaskRunLock:
    def __init__(self):
        self._mem_guard = threading.Lock()
        self._mem: Dict[str, Dict[str, Any]] = {}
        self._status: Dict[str, Dict[str, Any]] = {}
        self._hb_guard = threading.Lock()
        self._heartbeats: Dict[str, threading.Event] = {}

    def _lock_key(self, task_id: str) -> str:
        return f"{LOCK_PREFIX}{task_id}"

    def _status_key(self, task_id: str) -> str:
        return f"{STATUS_PREFIX}{task_id}"

    def acquire(self, task_id: str) -> Optional[str]:
        token = uuid.uuid4().hex
        ttl = lock_settings()["ttl_seconds"]
        client = get_redis_client()
        if client is not None:
            try:
                ok = client.set(self._lock_key(task_id), token, nx=True, ex=ttl)
                if ok:
                    return token
                return None
            except Exception as e:
                logger.warning("任务锁 Redis 获取失败，回退进程内锁: %s", e)
        now = time.time()
        with self._mem_guard:
            row = self._mem.get(task_id)
            if row and float(row.get("expires") or 0) > now:
                return None
            self._mem[task_id] = {"token": token, "expires": now + ttl}
            return token

    def refresh(self, task_id: str, token: str) -> bool:
        if not task_id or not token:
            return False
        ttl = lock_settings()["ttl_seconds"]
        client = get_redis_client()
        if client is not None:
            try:
                return bool(client.eval(_REFRESH_LUA, 1, self._lock_key(task_id), token, str(ttl)))
            except Exception as e:
                logger.warning("任务锁续期失败 %s: %s", task_id, e)
                return False
        with self._mem_guard:
            row = self._mem.get(task_id) or {}
            if row.get("token") != token:
                return False
            row["expires"] = time.time() + ttl
            self._mem[task_id] = row
            return True

    def release(self, task_id: str, token: str) -> bool:
        if not task_id or not token:
            return False
        self.stop_heartbeat(task_id)
        client = get_redis_client()
        if client is not None:
            try:
                removed = bool(client.eval(_RELEASE_LUA, 1, self._lock_key(task_id), token))
            except Exception as e:
                logger.warning("任务锁释放失败 %s: %s", task_id, e)
                removed = False
            if removed:
                try:
                    client.delete(self._status_key(task_id))
                except Exception:
                    pass
            return removed
        with self._mem_guard:
            row = self._mem.get(task_id) or {}
            if row.get("token") != token:
                return False
            self._mem.pop(task_id, None)
            self._status.pop(task_id, None)
            return True

    def current_token(self, task_id: str) -> Optional[str]:
        client = get_redis_client()
        if client is not None:
            try:
                return client.get(self._lock_key(task_id))
            except Exception:
                return None
        with self._mem_guard:
            row = self._mem.get(task_id) or {}
            if row and float(row.get("expires") or 0) > time.time():
                return row.get("token")
            return None

    def is_locked(self, task_id: str) -> bool:
        return bool(self.current_token(task_id))

    def locked_ids(self, task_ids: Iterable[str]) -> Set[str]:
        ids = list(task_ids)
        if not ids:
            return set()
        client = get_redis_client()
        if client is not None:
            try:
                values = client.mget([self._lock_key(task_id) for task_id in ids])
                return {task_id for task_id, value in zip(ids, values) if value}
            except Exception as e:
                logger.debug("批量读取任务锁失败: %s", e)
                return set()
        now = time.time()
        held = set()
        with self._mem_guard:
            for task_id in ids:
                row = self._mem.get(task_id) or {}
                if row and float(row.get("expires") or 0) > now:
                    held.add(task_id)
        return held

    def write_status(self, task_id: str, payload: Dict[str, Any]) -> None:
        body = dict(payload or {})
        body["task_id"] = task_id
        body["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with self._mem_guard:
            self._status[task_id] = body
        client = get_redis_client()
        if client is None:
            return
        try:
            client.set(
                self._status_key(task_id),
                json.dumps(body, ensure_ascii=False, default=str),
                ex=lock_settings()["ttl_seconds"] * 4,
            )
        except Exception as e:
            logger.debug("写入任务状态失败 %s: %s", task_id, e)

    def read_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        client = get_redis_client()
        if client is not None:
            try:
                raw = client.get(self._status_key(task_id))
                if raw:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        return data
            except Exception as e:
                logger.debug("读取任务状态失败 %s: %s", task_id, e)
        with self._mem_guard:
            row = self._status.get(task_id)
            return dict(row) if row else None

    def start_heartbeat(
        self,
        task_id: str,
        token: str,
        *,
        stop_when_phase_not: Optional[str] = None,
        max_seconds: Optional[int] = None,
    ) -> None:
        if not task_id or not token:
            return
        status = self.read_status(task_id) or {}
        if stop_when_phase_not and status.get("phase") not in (None, stop_when_phase_not):
            return
        interval = lock_settings()["heartbeat_seconds"]
        deadline = time.time() + max_seconds if max_seconds else None
        stop = threading.Event()
        with self._hb_guard:
            previous = self._heartbeats.get(task_id)
            self._heartbeats[task_id] = stop
        if previous is not None:
            previous.set()

        def _beat():
            while not stop.wait(interval):
                phase = (self.read_status(task_id) or {}).get("phase")
                if stop_when_phase_not and phase not in (None, stop_when_phase_not):
                    return
                if deadline and time.time() >= deadline:
                    if (
                        stop_when_phase_not
                        and phase == stop_when_phase_not
                        and self.current_token(task_id) == token
                    ):
                        self.write_status(task_id, {
                            "phase": "failed",
                            "in_progress": False,
                            "message": "任务排队超时，锁已释放",
                        })
                        self.release(task_id, token)
                    return
                if not self.refresh(task_id, token):
                    logger.warning("任务锁心跳失败，停止续期: %s", task_id)
                    return

        threading.Thread(
            target=_beat,
            name=f"traesolo-task-lock-{task_id}",
            daemon=True,
        ).start()

    def stop_heartbeat(self, task_id: str) -> None:
        with self._hb_guard:
            stop = self._heartbeats.pop(task_id, None)
        if stop is not None:
            stop.set()


task_run_lock = TaskRunLock()
