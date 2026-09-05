"""Industrial Pollution Intelligence endpoint.

For each active industrial-type emission source, compares the nearest
station's current AQI against its own 3-day historical baseline (same
rolling-window convention used elsewhere in this platform), cross-checked
with permit/violation history and ward attribution. See
app/services/industrial_pollution.py for the "never confirms a source"
discipline.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.models.analytics import PollutionAttribution
from app.models.emission_source import EmissionSource, EmissionSourceType
from app.repositories.aqi import AQIReadingRepository, MonitoringStationRepository
from app.schemas.base import APIResponse
from app.schemas.industrial_pollution import (
    IndustrialPollutionReportResponse,
    IndustrialZoneResponse,
)
from app.services.industrial_pollution import assess_industrial_zone
from app.utils.geo import haversine_km

router = APIRouter(prefix="/sources", tags=["Industrial Pollution Intelligence"])


@router.get(
    "/industrial-risk", response_model=APIResponse[IndustrialPollutionReportResponse]
)
async def get_industrial_pollution_risk(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[IndustrialPollutionReportResponse]:
    source_result = await session.execute(
        select(EmissionSource).where(
            EmissionSource.city == city,
            EmissionSource.source_type == EmissionSourceType.INDUSTRIAL,
            EmissionSource.is_active.is_(True),
            EmissionSource.is_deleted.is_(False),
        )
    )
    sources = list(source_result.scalars().all())

    if not sources:
        return APIResponse(
            data=IndustrialPollutionReportResponse(city=city, zones=[]),
            message="No active industrial emission sources on record for this city",
        )

    station_repo = MonitoringStationRepository(session)
    reading_repo = AQIReadingRepository(session)
    stations = await station_repo.get_active_by_city(city)

    three_hours_ago = datetime.now(timezone.utc) - timedelta(hours=3)

    zones: list[IndustrialZoneResponse] = []
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

        current_aqi = None
        pm25 = pm10 = no2 = None
        baseline_aqi = None
        if nearest_station is not None:
            reading = await reading_repo.get_latest_by_station(nearest_station.id)
            if reading is not None:
                current_aqi, pm25, pm10, no2 = (
                    reading.aqi,
                    reading.pm25,
                    reading.pm10,
                    reading.no2,
                )

            baseline_result = await session.execute(
                text(
                    """
                    SELECT AVG(aqi) AS avg_aqi FROM aqi_readings
                    WHERE station_id = :station_id
                      AND timestamp BETWEEN NOW() - INTERVAL '3 days' AND NOW() - INTERVAL '2 hours'
                      AND is_deleted = false AND quality_flag != 'invalid'
                    """
                ),
                {"station_id": nearest_station.id},
            )
            row = baseline_result.first()
            baseline_aqi = row.avg_aqi if row and row.avg_aqi is not None else None

        industrial_attribution_pct = None
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
                industrial_attribution_pct = attribution.industrial_pct

        permit_status_value = (
            source.permit_status.value
            if hasattr(source.permit_status, "value")
            else source.permit_status
        )

        assessment = assess_industrial_zone(
            source_name=source.name,
            ward_id=source.ward_id,
            permit_status=permit_status_value,
            violation_count=source.violation_count,
            current_aqi=current_aqi,
            pm25=pm25,
            pm10=pm10,
            no2=no2,
            historical_baseline_aqi=baseline_aqi,
            industrial_attribution_pct=industrial_attribution_pct,
            nearest_station_distance_km=(
                round(nearest_distance, 2) if nearest_distance is not None else None
            ),
        )

        zones.append(
            IndustrialZoneResponse(
                source_id=source.id,
                source_name=assessment.source_name,
                ward_id=assessment.ward_id,
                latitude=source.latitude,
                longitude=source.longitude,
                permit_status=assessment.permit_status,
                violation_count=assessment.violation_count,
                current_aqi=assessment.current_aqi,
                current_risk=assessment.current_risk.value,
                historical_baseline_aqi=(
                    round(assessment.historical_baseline_aqi, 1)
                    if assessment.historical_baseline_aqi
                    else None
                ),
                deviation_level=assessment.deviation_level.value,
                status=assessment.status,
                possible_contributing_source=assessment.possible_contributing_source,
                supporting_observations=assessment.supporting_observations,
            )
        )

    status_order = {"environmental_anomaly_detected": 0, "normal": 1}
    zones.sort(key=lambda z: status_order.get(z.status, 2))

    return APIResponse(data=IndustrialPollutionReportResponse(city=city, zones=zones))
