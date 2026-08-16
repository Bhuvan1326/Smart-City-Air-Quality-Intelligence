"""
Middleware:
  - RateLimitMiddleware: per-IP sliding window via Redis
  - AuditLogMiddleware: logs all mutating API calls to audit_logs table
"""

from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import logger


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiter using Redis.
    60 requests/minute, 1000 requests/hour per IP.
    Skips /health and /docs endpoints.
    """

    SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/metrics"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        if any(request.url.path.startswith(p) for p in self.SKIP_PATHS):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        try:
            from app.core.redis_client import get_redis

            redis = await get_redis()
            now = int(time.time())
            minute_key = f"rl:min:{client_ip}:{now // 60}"
            hour_key = f"rl:hr:{client_ip}:{now // 3600}"

            pipe = redis.pipeline()
            pipe.incr(minute_key)
            pipe.expire(minute_key, 70)
            pipe.incr(hour_key)
            pipe.expire(hour_key, 3700)
            results = await pipe.execute()
            minute_count = results[0]
            hour_count = results[2]

            if minute_count > settings.RATE_LIMIT_PER_MINUTE:
                logger.warning("rate_limit.minute", ip=client_ip, count=minute_count)
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "success": False,
                        "error": "Rate limit exceeded (60/min)",
                        "code": "RATE_LIMIT_MINUTE",
                    },
                    headers={"Retry-After": "60"},
                )
            if hour_count > settings.RATE_LIMIT_PER_HOUR:
                logger.warning("rate_limit.hour", ip=client_ip, count=hour_count)
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "success": False,
                        "error": "Rate limit exceeded (1000/hr)",
                        "code": "RATE_LIMIT_HOUR",
                    },
                    headers={"Retry-After": "3600"},
                )
        except Exception as e:
            # Redis unavailable — fail open (don't block requests)
            logger.warning("rate_limit.redis_unavailable", error=str(e))

        return await call_next(request)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    Writes audit log entries for all mutating requests (POST, PATCH, PUT, DELETE).
    Extracts user ID from JWT if present.
    """

    MUTATING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}
    SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/metrics"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method not in self.MUTATING_METHODS:
            return await call_next(request)
        if any(request.url.path.startswith(p) for p in self.SKIP_PATHS):
            return await call_next(request)

        response = await call_next(request)

        # Write audit log asynchronously (don't block response)
        try:
            user_id = self._extract_user_id(request)
            resource_type = self._infer_resource(request.url.path)
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                from sqlalchemy import text

                await session.execute(
                    text(
                        """
                    INSERT INTO audit_logs
                        (id, user_id, action, resource_type, ip_address, user_agent, response_code, created_at, updated_at, is_deleted)
                    VALUES
                        (gen_random_uuid(), :user_id, :action, :resource_type, :ip, :ua, :code, NOW(), NOW(), false)
                """
                    ),
                    {
                        "user_id": user_id,
                        "action": request.method.lower(),
                        "resource_type": resource_type,
                        "ip": request.client.host if request.client else None,
                        "ua": request.headers.get("user-agent", "")[:255],
                        "code": response.status_code,
                    },
                )
                await session.commit()
        except Exception as e:
            logger.warning("audit_log.write_failed", error=str(e))

        return response

    def _extract_user_id(self, request: Request) -> str | None:
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return None
        try:
            from app.core.security import decode_token

            payload = decode_token(auth[7:])
            return payload.get("sub")
        except Exception:
            return None

    def _infer_resource(self, path: str) -> str:
        parts = [p for p in path.split("/") if p and not p.startswith("api")]
        return parts[1] if len(parts) > 1 else parts[0] if parts else "unknown"
