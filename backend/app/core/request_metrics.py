from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

try:
    from prometheus_client import Counter, Histogram

    _REQUESTS = Counter(
        "http_requests_total",
        "HTTP requests handled",
        ["method", "status_class"],
    )
    _DURATION = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method"],
    )
except ImportError:  # pragma: no cover - prometheus_client is in manifests
    _REQUESTS = _DURATION = None


def _status_class(code: int) -> str:
    return f"{code // 100}xx"


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if _REQUESTS is None:
            return await call_next(request)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            _DURATION.labels(request.method).observe(time.perf_counter() - start)
        _REQUESTS.labels(request.method, _status_class(response.status_code)).inc()
        return response
