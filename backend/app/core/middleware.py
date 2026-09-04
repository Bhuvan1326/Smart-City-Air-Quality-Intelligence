"""
Middleware:
  - RateLimitMiddleware: per-IP sliding window via Redis
  - AuditLogMiddleware: logs all mutating API calls to audit_logs table
"""

from __future__ import annotations

import ipaddress
import time
from collections.abc import Callable
from typing import ClassVar

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

    SKIP_PATHS: ClassVar[set[str]] = {
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/metrics",
    }

    @staticmethod
    def _is_dev_local_ip(client_ip: str) -> bool:
        """True for loopback/private/link-local addresses.

        In the docker-compose dev setup, every request the frontend
        container makes to the backend container arrives from a single
        docker-bridge gateway IP (e.g. 172.18.0.1), so the sliding-window
        counter gets shared across *all* traffic from the dev machine and
        trips almost immediately. This is never true in production, where
        requests come from real client IPs (or a load balancer that sets
        a distinct forwarded IP per client), so restricting the exemption
        to private/loopback addresses AND non-production ENVIRONMENT
        keeps production rate limiting completely unaffected.
        """
        try:
            addr = ipaddress.ip_address(client_ip)
        except ValueError:
            return False
        return addr.is_private or addr.is_loopback or addr.is_link_local

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        if any(request.url.path.startswith(p) for p in self.SKIP_PATHS):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        # DEVELOPMENT ONLY: don't rate-limit local/Docker-internal traffic.
        # Production keeps full rate limiting regardless of IP.
        if not settings.is_production and self._is_dev_local_ip(client_ip):
            return await call_next(request)

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
        except Exception as e:  # noqa: BLE001 -- Redis unavailable, fail open
            # Redis unavailable — fail open (don't block requests)
            logger.warning("rate_limit.redis_unavailable", error=str(e))

        return await call_next(request)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    Writes audit log entries for all mutating requests (POST, PATCH, PUT, DELETE).
    Extracts user ID from JWT if present.
    """

    MUTATING_METHODS: ClassVar[set[str]] = {"POST", "PATCH", "PUT", "DELETE"}
    SKIP_PATHS: ClassVar[set[str]] = {
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/metrics",
    }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method not in self.MUTATING_METHODS:
            return await call_next(request)
        if any(request.url.path.startswith(p) for p in self.SKIP_PATHS):
            return await call_next(request)

        response = await call_next(request)

        # Write audit log asynchronously (don't block response).
        #
        # IMPORTANT: this must use the SAME engine/session factory as the
        # rest of the request — not a hardcoded module-level import of
        # app.core.database.AsyncSessionLocal. That engine is created
        # once at module-import time and bound to whichever event loop
        # is running then; reusing it from a different event loop later
        # (e.g. a different pytest-asyncio test function, each of which
        # gets its own event loop) causes asyncpg/SQLAlchemy errors like
        # "Future attached to a different loop" and, once the pool's
        # internal state is corrupted by that mismatch, cascading
        # MissingGreenlet errors on later requests. Tests override the
        # DB dependency via app.dependency_overrides[get_db] for
        # endpoint code, but middleware doesn't go through Depends() —
        # so it needs its own escape hatch: request.app.state.
        # async_session_factory, which app/tests/conftest.py's `client`
        # fixture sets to the exact same per-test engine/session factory
        # used for endpoint requests. Falls back to the real
        # AsyncSessionLocal outside of tests.
        session_factory = getattr(request.app.state, "async_session_factory", None)
        if session_factory is None:
            from app.core.database import AsyncSessionLocal

            session_factory = AsyncSessionLocal

        try:
            user_id = self._extract_user_id(request)
            resource_type = self._infer_resource(request.url.path)

            async with session_factory() as session:
                from sqlalchemy import text

                await session.execute(
                    text("""
                    INSERT INTO audit_logs
                        (id, user_id, action, resource_type, ip_address, user_agent, response_code, created_at, updated_at, is_deleted)
                    VALUES
                        (gen_random_uuid(), :user_id, :action, :resource_type, :ip, :ua, :code, NOW(), NOW(), false)
                """),
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
        except Exception as e:  # noqa: BLE001 -- audit write must not block request
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
        except Exception:  # noqa: BLE001 -- malformed/expired token, treat as anonymous
            return None

    def _infer_resource(self, path: str) -> str:
        parts = [p for p in path.split("/") if p and not p.startswith("api")]
        return parts[1] if len(parts) > 1 else parts[0] if parts else "unknown"
