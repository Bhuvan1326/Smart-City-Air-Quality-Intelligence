"""Prometheus metrics collection for the platform."""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["Observability"])


@router.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
async def prometheus_metrics() -> PlainTextResponse:
    """Expose Prometheus-compatible metrics."""
    try:
        from prometheus_client import (CONTENT_TYPE_LATEST, Counter, Gauge,
                                       generate_latest)

        return PlainTextResponse(
            generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )
    except ImportError:
        return PlainTextResponse(
            "# prometheus_client not installed\n",
            media_type="text/plain",
        )
