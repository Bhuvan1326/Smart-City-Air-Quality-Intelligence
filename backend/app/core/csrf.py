"""
CSRF protection — double-submit cookie pattern.

This API is primarily consumed with Bearer tokens (Authorization header),
which are *not* ambient credentials, so classic CSRF (a third-party site
tricking a browser into firing an authenticated request) does not apply to
those calls — the attacker's page cannot read or attach the header.

CSRF protection is still needed for the small number of flows that *do* rely
on browser-managed credentials — e.g. a future cookie-based web session, or
any endpoint a `<form>` could submit to. `CSRFMiddleware` enforces the
double-submit pattern for exactly those requests: if a request carries the
session cookie, it must also carry a matching `X-CSRF-Token` header, whose
value was previously handed out via `/api/v1/auth/csrf-token` and stored in
a separate readable cookie. Bearer-authenticated requests are left untouched.
"""

from __future__ import annotations

import hmac
import secrets
from typing import Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
SESSION_COOKIE_NAME = "session"  # only relevant if/when cookie-based auth is enabled

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Bearer-token requests aren't ambient credentials — no CSRF exposure.
        if request.headers.get("authorization", "").startswith("Bearer "):
            return await call_next(request)

        # No session cookie on the request → nothing ambient to forge either.
        if SESSION_COOKIE_NAME not in request.cookies:
            return await call_next(request)

        if request.method not in _SAFE_METHODS:
            cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
            header_token = request.headers.get(CSRF_HEADER_NAME)
            if (
                not cookie_token
                or not header_token
                or not hmac.compare_digest(cookie_token, header_token)
            ):
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "success": False,
                        "error": "CSRF token missing or invalid",
                        "code": "CSRF_FAILURE",
                    },
                )

        return await call_next(request)
