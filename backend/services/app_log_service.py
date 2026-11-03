"""系统运行日志 — 控制台 + backend/logs/runtime/ 按日文件。

环境变量：
- TRAESOLO_JSON_LOGS=1  输出单行 JSON（便于 Loki / ELK 采集）
- TRAESOLO_LOG_LEVEL=INFO|DEBUG|WARNING  根日志级别
"""
from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

LOG_DIR = Path(__file__).resolve().parent.parent / "logs" / "runtime"
TEXT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_CONFIGURED = False

_EXTRA_FIELDS = (
    "event",
    "service",
    "request_id",
    "path",
    "method",
    "status_code",
    "duration_ms",
    "job_id",
    "user",
    "match_id",
    "model_version",
)


def json_logs_enabled() -> bool:
    return os.environ.get("TRAESOLO_JSON_LOGS", "").lower() in ("1", "true", "yes")


def resolve_log_level() -> int:
    raw = (os.environ.get("TRAESOLO_LOG_LEVEL") or "INFO").upper()
    return getattr(logging, raw, logging.INFO)


class JsonLogFormatter(logging.Formatter):
    """单行 JSON 日志，保留 extra 结构化字段。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in _EXTRA_FIELDS:
            if hasattr(record, key):
                val = getattr(record, key)
                if val is not None:
                    payload[key] = val
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            payload["exception"] = record.exc_text
        return json.dumps(payload, ensure_ascii=False)


def setup_app_logging(level: Optional[int] = None) -> Path:
    """配置根 logger：同时输出到控制台与按日滚动的运行日志文件。"""
    global _CONFIGURED
    if _CONFIGURED:
        return get_current_log_path()

    level = level if level is not None else resolve_log_level()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = get_current_log_path()
    formatter: logging.Formatter
    if json_logs_enabled():
        formatter = JsonLogFormatter()
    else:
        formatter = logging.Formatter(TEXT_LOG_FORMAT)

    root = logging.getLogger()
    root.setLevel(level)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    has_console = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in root.handlers
    )
    if not has_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    _CONFIGURED = True
    boot = logging.getLogger(__name__)
    boot.info(
        "logging ready",
        extra={
            "event": "logging_ready",
            "path": str(log_path),
            "json": json_logs_enabled(),
            "level": logging.getLevelName(level),
        },
    )
    return log_path


def log_event(level: int, message: str, **fields: Any) -> None:
    """写入结构化业务事件（JSON 模式下字段会进入日志行）。"""
    logging.getLogger("traesolo").log(level, message, extra=fields)


def log_http_access(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    **extra: Any,
) -> None:
    """API 访问日志（仅 JSON 模式或显式 TRAESOLO_ACCESS_LOG=1 时写入）。"""
    if not json_logs_enabled() and os.environ.get("TRAESOLO_ACCESS_LOG", "").lower() not in (
        "1",
        "true",
        "yes",
    ):
        return
    logging.getLogger("traesolo.access").info(
        f"{method} {path} {status_code}",
        extra={
            "event": "http_access",
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            **extra,
        },
    )


def get_current_log_path() -> Path:
    return LOG_DIR / f"app_{datetime.now():%Y%m%d}.log"


def list_runtime_logs() -> List[dict]:
    if not LOG_DIR.is_dir():
        return []
    files = sorted(LOG_DIR.glob("app_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for path in files:
        stat = path.stat()
        result.append({
            "name": path.name,
            "size": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "is_current": path.name == get_current_log_path().name,
        })
    return result


def resolve_log_path(name: Optional[str] = None) -> Path:
    """解析日志文件路径，默认返回当日运行日志。"""
    if not name:
        return get_current_log_path()
    safe_name = Path(name).name
    if not safe_name.startswith("app_") or not safe_name.endswith(".log"):
        raise ValueError("无效的日志文件名")
    path = LOG_DIR / safe_name
    if not path.is_file():
        raise FileNotFoundError(f"日志文件不存在: {safe_name}")
    return path


def read_log_tail(path: Path, lines: int = 300, max_bytes: int = 512_000) -> str:
    lines = max(1, min(lines, 2000))
    if not path.is_file():
        return ""
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        read_size = min(size, max_bytes)
        f.seek(max(0, size - read_size))
        chunk = f.read(read_size)
    text = chunk.decode("utf-8", errors="replace")
    rows = text.splitlines()
    if len(rows) > lines:
        rows = rows[-lines:]
    return "\n".join(rows)
