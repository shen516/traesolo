"""模拟预测内存 TTL 缓存。

- 键：match_id + simulations + seed + overrides 规范化 JSON
- 仅进程内、短 TTL（默认 300s），不写库、不写 Redis，符合方案"不污染正式预测缓存"约束
- 命中直接返回深拷贝，避免调用方修改污染缓存
"""

from __future__ import annotations

import copy
import json
import threading
import time
from typing import Any, Dict, Optional, Tuple

DEFAULT_TTL_SECONDS = 300
_MAX_ENTRIES = 128

_LOCK = threading.Lock()
_STORE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def _normalize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _normalize(obj[k]) for k in sorted(obj)}
    if isinstance(obj, (list, tuple)):
        return [_normalize(x) for x in obj]
    if isinstance(obj, float) and obj.is_integer():
        return int(obj)
    return obj


def make_key(match_id: str, simulations: int, seed: Optional[int], overrides: Optional[dict]) -> str:
    payload = {
        "match_id": str(match_id),
        "simulations": int(simulations),
        "seed": seed,
        "overrides": _normalize(overrides or {}),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def get(key: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        item = _STORE.get(key)
        if item is None:
            return None
        expires_at, value = item
        if time.monotonic() >= expires_at:
            _STORE.pop(key, None)
            return None
        return copy.deepcopy(value)


def set(key: str, value: Dict[str, Any], ttl: int = DEFAULT_TTL_SECONDS) -> None:
    with _LOCK:
        if len(_STORE) >= _MAX_ENTRIES:
            oldest = min(_STORE.items(), key=lambda kv: kv[1][0])[0]
            _STORE.pop(oldest, None)
        _STORE[key] = (time.monotonic() + ttl, copy.deepcopy(value))


def clear() -> None:
    with _LOCK:
        _STORE.clear()
