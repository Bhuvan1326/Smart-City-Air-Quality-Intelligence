"""Construction & Dust Intelligence endpoint.

Combines the existing (previously unexposed) emission_sources table with
current AQI/PM10 readings and pollution attribution to flag "possible
contributing condition" for construction/dust-type sites — never a
confirmed-source claim. See app/services/construction_dust.py.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from app.api.deps import CurrentUser, get_db
from app.models.analytics import PollutionAttribution
from app.models.emission_source import EmissionSource, EmissionSourceType
from app.repositories.aqi import AQIReadingRepository, MonitoringStationRepository
from app.schemas.base import APIResponse
from app.schemas.construction_dust import (
    ConstructionDustReportResponse,
    ConstructionDustSiteResponse,
)
from app.services.construction_dust import assess_construction_dust_risk
from app.utils.geo import haversine_km
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/sources", tags=["Construction & Dust Intelligence"])


@router.get(
    "/construction-dust-risk",
    response_model=APIResponse[ConstructionDustReportResponse],
)
async def get_construction_dust_risk(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[ConstructionDustReportResponse]:
    source_result = await session.execute(
        select(EmissionSource).where(
            EmissionSource.city == city,
            EmissionSource.source_type.in_(
                [EmissionSourceType.CONSTRUCTION, EmissionSourceType.DUST]
            ),
            EmissionSource.is_active.is_(True),
            EmissionSource.is_deleted.is_(False),
        )
    )
    sources = list(source_result.scalars().all())

    if not sources:
        return APIResponse(
            data=ConstructionDustReportResponse(city=city, sites=[]),
            message="No active construction or dust-type emission sources on record for this city",
        )

    station_repo = MonitoringStationRepository(session)
    reading_repo = AQIReadingRepository(session)
    stations = await station_repo.get_active_by_city(city)

    three_hours_ago = datetime.now(timezone.utc) - timedelta(hours=3)

    sites: list[ConstructionDustSiteResponse] = []
    for source in sources:
        nearest_station = None
        nearest_distance = None
        for station in stations:
            d = haversine_km(
                source.latitude, source.longitude, station.latitude, station.longitude
            )
            if nearest_distance is None or d < nearest_distance:
                nearest_distance = d
                nearest_station = station

        pm10 = None
        if nearest_station is not None:
            reading = await reading_repo.get_latest_by_station(nearest_station.id)
            if reading is not None:
                pm10 = reading.pm10

        attribution_pct_construction = None
        attribution_pct_dust = None
        if source.ward_id:
            attr_result = await session.execute(
                select(PollutionAttribution)
                .where(
                    PollutionAttribution.city == city,
                    PollutionAttribution.ward_id == source.ward_id,
                    PollutionAttribution.timestamp >= three_hours_ago,
                    PollutionAttribution.is_deleted.is_(False),
                )
                .order_by(desc(PollutionAttribution.timestamp))
                .limit(1)
            )
            attribution = attr_result.scalar_one_or_none()
            if attribution:
                attribution_pct_construction = attribution.construction_pct
                attribution_pct_dust = attribution.dust_pct

        source_type_value = (
            source.source_type.value
            if hasattr(source.source_type, "value")
            else source.source_type
        )
        permit_status_value = (
            source.permit_status.value
            if hasattr(source.permit_status, "value")
            else source.permit_status
        )

        assessment = assess_construction_dust_risk(
            source_name=source.name,
            source_type=source_type_value,
            ward_id=source.ward_id,
            permit_status=permit_status_value,
            violation_count=source.violation_count,
            nearest_station_name=nearest_station.name if nearest_station else None,
            nearest_station_distance_km=(
                round(nearest_distance, 2) if nearest_distance is not None else None
            ),
            pm10=pm10,
            construction_attribution_pct=attribution_pct_construction,
            dust_attribution_pct=attribution_pct_dust,
        )

        sites.append(
            ConstructionDustSiteResponse(
                source_id=source.id,
                source_name=assessment.source_name,
                source_type=assessment.source_type,
                ward_id=assessment.ward_id,
                latitude=source.latitude,
                longitude=source.longitude,
                permit_status=assessment.permit_status,
                violation_count=assessment.violation_count,
                last_inspected_at=source.last_inspected_at,
                nearest_station_name=assessment.nearest_station_name,
                nearest_station_distance_km=assessment.nearest_station_distance_km,
                pm10=assessment.pm10,
                risk_level=assessment.risk_level.value,
                supporting_observations=assessment.supporting_observations,
                requires_verification=assessment.requires_verification,
            )
        )

    risk_order = {"high": 0, "moderate": 1, "low": 2}
    sites.sort(key=lambda s: risk_order.get(s.risk_level, 3))

    return APIResponse(data=ConstructionDustReportResponse(city=city, sites=sites))
