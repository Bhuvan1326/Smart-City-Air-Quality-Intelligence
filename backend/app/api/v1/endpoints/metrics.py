"""Prometheus metrics collection for the platform."""

import hmac

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import PlainTextResponse

from app.core.config import settings

router = APIRouter(tags=["Observability"])


@router.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
async def prometheus_metrics(request: Request) -> PlainTextResponse:
    """Expose Prometheus-compatible metrics.

    Access: if METRICS_TOKEN is set, a matching `Authorization: Bearer`
    header is required. If unset, open in development, 404 in production.
    """
    token = settings.METRICS_TOKEN
    if token:
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied, f"Bearer {token}"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid metrics token",
                headers={"WWW-Authenticate": "Bearer"},
            )
    elif settings.is_production:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        return PlainTextResponse(
            generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )
    except ImportError:
        return PlainTextResponse(
            "# prometheus_client not installed\n",
            media_type="text/plain",
        )
