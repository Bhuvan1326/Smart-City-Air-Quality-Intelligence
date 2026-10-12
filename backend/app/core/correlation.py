from __future__ import annotations

import re
import uuid
from collections.abc import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_ID_HEADER = "x-request-id"

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _safe_request_id(incoming: str | None) -> str:
    if incoming is not None and _ID_RE.fullmatch(incoming):
        return incoming
    return uuid.uuid4().hex


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = _safe_request_id(request.headers.get(REQUEST_ID_HEADER))
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
