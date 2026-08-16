from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.models.monitoring import MonitoringStation, SensorHealthAssessment
from app.schemas.base import APIResponse
from app.schemas.sensor_health import (SensorHealthAssessmentResponse,
                                       StationHealthSummary)

router = APIRouter(prefix="/sensors", tags=["Predictive Sensor Maintenance"])


@router.get("/health", response_model=APIResponse[list[StationHealthSummary]])
async def list_station_health(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str | None = Query(None),
    priority: str | None = Query(
        None, description="Filter by routine|soon|urgent|critical"
    ),
) -> APIResponse[list[StationHealthSummary]]:
    """Latest predictive-maintenance assessment for every active station."""
    query = select(MonitoringStation).where(
        MonitoringStation.is_deleted == False,  # noqa: E712
        MonitoringStation.is_active == True,  # noqa: E712
    )
    if city:
        query = query.where(MonitoringStation.city == city)
    stations = (await session.execute(query)).scalars().all()

    summaries: list[StationHealthSummary] = []
    for station in stations:
        latest_result = await session.execute(
            select(SensorHealthAssessment)
            .where(SensorHealthAssessment.station_id == station.id)
            .order_by(desc(SensorHealthAssessment.assessed_at))
            .limit(1)
        )
        latest = latest_result.scalar_one_or_none()
        if priority and (not latest or latest.maintenance_priority != priority):
            continue
        summaries.append(
            StationHealthSummary(
                station_id=station.id,
                station_name=station.name,
                ward_id=station.ward_id,
                maintenance_score=station.maintenance_score,
                latest_assessment=(
                    SensorHealthAssessmentResponse.model_validate(latest)
                    if latest
                    else None
                ),
            )
        )

    summaries.sort(
        key=lambda s: (
            s.latest_assessment.maintenance_priority_score
            if s.latest_assessment
            else -1
        ),
        reverse=True,
    )
    return APIResponse(data=summaries)


@router.get(
    "/{station_id}/health/history",
    response_model=APIResponse[list[SensorHealthAssessmentResponse]],
)
async def station_health_history(
    station_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(30, ge=1, le=200),
) -> APIResponse[list[SensorHealthAssessmentResponse]]:
    """Historical assessments for one station, most recent first — powers a drift/RUL trend chart."""
    result = await session.execute(
        select(SensorHealthAssessment)
        .where(SensorHealthAssessment.station_id == station_id)
        .order_by(desc(SensorHealthAssessment.assessed_at))
        .limit(limit)
    )
    assessments = list(result.scalars().all())
    return APIResponse(
        data=[SensorHealthAssessmentResponse.model_validate(a) for a in assessments]
    )
