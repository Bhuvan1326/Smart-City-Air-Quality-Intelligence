"""Twilio webhook signature validation (X-Twilio-Signature).

Implements Twilio's documented algorithm with the standard library so the
backend does not depend on the optional `twilio` SDK just to *receive*
callbacks:

    signature = base64( HMAC-SHA1( auth_token,
                url + concat(sorted(params): key + value) ) )

Design rules:
  * Fail closed: missing token, missing configured base URL, missing header or
    mismatch -> HTTP 403. There is no development bypass.
  * The URL that is signed is the externally visible URL we gave Twilio
    (TWILIO_STATUS_CALLBACK_URL + path), never request.url / forwarded
    headers, so a reverse proxy cannot change what is validated.
  * Nothing sensitive (token, params, signature) is logged.
"""

import base64
import hashlib
import hmac
from collections.abc import Mapping, Sequence
from uuid import UUID

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.logging import logger

IVR_PATH_TEMPLATE = "/api/v1/notifications/ivr/{alert_id}"


def ivr_callback_url(alert_id: UUID | str) -> str:
    """Externally visible IVR webhook URL for an alert. Single source of truth
    shared by the dispatcher (when placing the call) and the validator."""
    base = (settings.TWILIO_STATUS_CALLBACK_URL or "").rstrip("/")
    return f"{base}{IVR_PATH_TEMPLATE.format(alert_id=alert_id)}"


def compute_signature(
    auth_token: str,
    url: str,
    params: Mapping[str, str | Sequence[str]] | None = None,
) -> str:
    data = url
    for key in sorted(params or {}):
        value = (params or {})[key]
        values = [value] if isinstance(value, str) else sorted(value)
        for v in values:
            data += f"{key}{v}"
    digest = hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def is_valid_signature(
    auth_token: str,
    url: str,
    params: Mapping[str, str | Sequence[str]] | None,
    signature: str | None,
) -> bool:
    if not auth_token or not signature:
        return False
    expected = compute_signature(auth_token, url, params)
    return hmac.compare_digest(expected, signature)


def _forbidden(reason: str) -> HTTPException:
    logger.warning("twilio.ivr_signature_rejected", reason=reason)
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature"
    )


async def require_valid_twilio_signature(request: Request) -> None:
    """FastAPI dependency for the IVR webhook (GET or POST)."""
    token = settings.TWILIO_AUTH_TOKEN
    if not token:
        raise _forbidden("auth_token_not_configured")
    if not (settings.TWILIO_STATUS_CALLBACK_URL or "").strip():
        raise _forbidden("public_base_url_not_configured")
    signature = request.headers.get("x-twilio-signature")
    if not signature:
        raise _forbidden("missing_signature")

    url = ivr_callback_url(request.path_params["alert_id"])
    if request.url.query:
        url = f"{url}?{request.url.query}"

    params: dict[str, list[str]] = {}
    if request.method == "POST":
        form = await request.form()
        for key in form:
            params[key] = [str(v) for v in form.getlist(key)]

    if not is_valid_signature(token, url, params, signature):
        raise _forbidden("signature_mismatch")
