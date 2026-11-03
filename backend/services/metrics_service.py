"""Prometheus 指标与 HTTP 请求统计。"""

from __future__ import annotations

import time
from typing import Callable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "traesolo_http_requests_total",
    "HTTP requests",
    ["method", "path", "status"],
)
HTTP_LATENCY = Histogram(
    "traesolo_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)
PREDICTIONS = Counter(
    "traesolo_predictions_total",
    "Predictions computed",
    ["source"],
)


def metrics_payload() -> bytes:
    return generate_latest()


def metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST


def record_request(method: str, path: str, status: int, elapsed: float) -> None:
    route = _normalize_path(path)
    HTTP_REQUESTS.labels(method=method, path=route, status=str(status)).inc()
    HTTP_LATENCY.labels(method=method, path=route).observe(elapsed)


def record_prediction(source: str = "api") -> None:
    PREDICTIONS.labels(source=source).inc()


def _normalize_path(path: str) -> str:
    if not path.startswith("/api/"):
        return path or "/"
    parts = path.strip("/").split("/")
    if len(parts) >= 4 and parts[2] == "matches" and parts[3].isdigit() is False and len(parts) > 3:
        # /api/v1/matches/{id}/...
        if len(parts) >= 4:
            parts[3] = ":id"
    elif len(parts) >= 4 and parts[2] in ("users", "teams", "players", "model"):
        if len(parts) >= 4 and parts[3] not in ("train", "status", "current", "upcoming", "finished"):
            parts[3] = ":id"
    return "/" + "/".join(parts[:6])


async def metrics_middleware(request, call_next: Callable):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    try:
        record_request(request.method, request.url.path, response.status_code, elapsed)
    except Exception:
        pass
    return response
