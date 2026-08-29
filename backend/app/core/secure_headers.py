"""
SecurityHeadersMiddleware — attaches standard hardening headers to every response.

Covers: clickjacking (X-Frame-Options), MIME sniffing (X-Content-Type-Options),
transport security (HSTS, production only), referrer leakage (Referrer-Policy),
browser feature access (Permissions-Policy), and a Content-Security-Policy
scoped to the API surface (JSON responses + the interactive OpenAPI docs).
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.config import settings
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# The API mostly serves JSON, but /docs and /redoc render a Swagger/ReDoc UI
# that needs to load its own inline scripts/styles from a CDN, so the CSP is
# relaxed only for those paths.
_DOCS_PATHS = ("/docs", "/redoc")

_BASE_CSP = (
    "default-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'self'"
)

_DOCS_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        is_docs = (
            any(request.url.path.startswith(p) for p in _DOCS_PATHS)
            or request.url.path == "/openapi.json"
        )

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(self), camera=(), microphone=(), payment=()"
        )
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        response.headers["Content-Security-Policy"] = (
            _DOCS_CSP if is_docs else _BASE_CSP
        )

        if settings.is_production:
            # Only advertise HSTS over an actual TLS deployment (production).
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        return response
