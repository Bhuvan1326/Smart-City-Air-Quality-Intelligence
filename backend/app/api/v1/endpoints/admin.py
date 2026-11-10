"""Administrative monitoring endpoints: error tracking, user/system
statistics, dependency health and audit-run status. All RequireAdmin."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, RequireAdmin, get_db
from app.core.redis_client import get_redis
from app.models.analytics import AuditLog
from app.models.monitoring import AQIReading, MonitoringStation
from app.models.user import User
from app.schemas.base import APIResponse

router = APIRouter(prefix="/admin", tags=["Administration"])

_AUDIT_RESULTS_DIR = Path(__file__).resolve().parents[5] / "docs" / "audit_results"


def _severity_for(code: int | None) -> str:
    if code is None:
        return "medium"
    if code >= 500:
        return "critical"
    if code >= 400:
        return "medium"
    return "low"


@router.get("/errors", dependencies=[RequireAdmin])
async def list_errors(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    min_status: int = Query(400, ge=100, le=599),
    since_hours: int | None = Query(None, ge=1, le=720),
):
    stmt = select(AuditLog).where(AuditLog.response_code >= min_status)
    if since_hours:
        stmt = stmt.where(
            AuditLog.created_at >= func.now() - text(f"interval '{since_hours} hours'")
        )
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    result = await session.execute(
        stmt.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    items = [
        {
            "id": str(r.id),
            "timestamp": r.created_at,
            "severity": _severity_for(r.response_code),
            "component": r.resource_type or "api",
            "endpoint": f"{r.action}",
            "http_status": r.response_code,
            "resource_id": r.resource_id,
            "resolution_status": "unresolved",
        }
        for r in result.scalars().all()
    ]
    return APIResponse(
        data={"items": items, "total": total or 0, "page": page, "per_page": per_page}
    )


@router.get("/errors/summary", dependencies=[RequireAdmin])
async def error_summary(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    rows = (
        await session.execute(
            select(AuditLog.response_code, func.count())
            .where(AuditLog.response_code >= 400)
            .group_by(AuditLog.response_code)
        )
    ).all()
    by_code = {str(code): n for code, n in rows}
    crit = sum(n for code, n in rows if code and code >= 500)
    med = sum(n for code, n in rows if code and 400 <= code < 500)
    return APIResponse(
        data={
            "total": sum(by_code.values()),
            "critical": crit,
            "medium": med,
            "unresolved": sum(by_code.values()),
            "by_status": by_code,
            "generated_at": datetime.now(UTC),
        }
    )


@router.get("/users/statistics", dependencies=[RequireAdmin])
async def user_statistics(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    by_role = dict(
        (
            await session.execute(select(User.role, func.count()).group_by(User.role))
        ).all()
    )
    by_city = dict(
        (
            await session.execute(
                select(func.coalesce(User.city, "unknown"), func.count()).group_by(
                    User.city
                )
            )
        ).all()
    )
    total = sum(by_role.values())
    active_flag = await session.scalar(
        select(func.count()).select_from(User).where(User.is_active.is_(True))
    )
    with_last_login = await session.scalar(
        select(func.count()).select_from(User).where(User.last_login.isnot(None))
    )
    return APIResponse(
        data={
            "total_users": total,
            "active_users_flagged": active_flag or 0,
            "inactive_users_flagged": (total - (active_flag or 0)),
            "users_with_last_login": with_last_login or 0,
            "active_by_login_note": (
                "Login activity not tracked per-user; counts reflect is_active flag and "
                "last_login presence only."
            ),
            "by_role": {
                str(k.value if hasattr(k, "value") else k): v
                for k, v in by_role.items()
            },
            "by_city": by_city,
            "generated_at": datetime.now(UTC),
        }
    )


@router.get("/system/statistics", dependencies=[RequireAdmin])
async def system_statistics(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    st = await session.execute(
        select(
            func.count(),
            func.count().filter(MonitoringStation.openaq_location_id.isnot(None)),
            func.count().filter(MonitoringStation.is_active.is_(True)),
        ).select_from(MonitoringStation)
    )
    total_st, openaq_st, active_st = st.one()
    flags = dict(
        (
            await session.execute(
                select(AQIReading.quality_flag, func.count()).group_by(
                    AQIReading.quality_flag
                )
            )
        ).all()
    )
    cities = await session.scalar(
        select(func.count(func.distinct(MonitoringStation.city))).select_from(
            MonitoringStation
        )
    )
    states = await session.scalar(
        select(func.count(func.distinct(MonitoringStation.state)))
        .select_from(MonitoringStation)
        .where(MonitoringStation.state.isnot(None))
    )
    with_readings = await session.scalar(
        select(func.count(func.distinct(AQIReading.station_id))).select_from(AQIReading)
    )
    return APIResponse(
        data={
            "stations": {
                "total": total_st,
                "openaq_mapped": openaq_st,
                "active": active_st,
                "with_any_readings": with_readings or 0,
            },
            "readings_by_flag": flags,
            "coverage": {"cities": cities or 0, "states": states or 0},
            "generated_at": datetime.now(UTC),
        }
    )


@router.get("/system/health", dependencies=[RequireAdmin])
async def system_health(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    checks: dict[str, str] = {}
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception:
        checks["database"] = "unavailable"
    try:
        r = await get_redis()
        checks["redis"] = "healthy" if await r.ping() else "degraded"
    except Exception:
        checks["redis"] = "unavailable"
    try:
        from app.ml.inference import get_model_registry

        checks["xgboost"] = (
            "healthy" if get_model_registry()._active_model else "not_loaded"
        )
    except Exception:
        checks["xgboost"] = "unavailable"
    from app.core.config import settings

    checks["openaq"] = "configured" if settings.OPENAQ_API_KEY else "not_configured"
    checks["nugen"] = (
        "configured" if getattr(settings, "NUGEN_API_KEY", None) else "not_configured"
    )
    checks["mapbox"] = (
        "configured"
        if getattr(settings, "NEXT_PUBLIC_MAPBOX_TOKEN", None)
        else "not_configured"
    )
    overall = (
        "degraded"
        if any(v in ("unavailable", "not_loaded") for v in checks.values())
        else "healthy"
    )
    return APIResponse(
        data={"overall": overall, "checks": checks, "checked_at": datetime.now(UTC)}
    )


@router.get("/audits", dependencies=[RequireAdmin])
async def audit_status(current_user: CurrentUser):
    out: dict[str, dict] = {}
    for audit_type in ("security", "api_reliability"):
        path = _AUDIT_RESULTS_DIR / f"{audit_type}_audit.json"
        if path.exists():
            try:
                out[audit_type] = {
                    **json.loads(path.read_text()),
                    "status": "completed",
                }
            except Exception:
                out[audit_type] = {"status": "result_unreadable"}
        else:
            out[audit_type] = {"status": "pending"}
    return APIResponse(data={"audits": out, "checked_at": datetime.now(UTC)})
