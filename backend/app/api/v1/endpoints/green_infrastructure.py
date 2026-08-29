"""Green Infrastructure Optimization endpoint.

Ranks wards for tree-planting / green-corridor investment by combining
current pollution, population exposure (reusing the exposure-scoring
service), traffic level (reusing the traffic provider), and admin-entered
green-cover data. See app/services/green_infrastructure.py for the scoring
methodology and its explicit no-fabricated-impact guarantee.
"""

from datetime import datetime, timezone
from typing import Annotated

from app.api.deps import CurrentUser, get_db
from app.models.demographics import WardDemographics
from app.repositories.aqi import AQIReadingRepository, MonitoringStationRepository
from app.schemas.base import APIResponse
from app.schemas.green_infrastructure import (
    GreenInfrastructureReportResponse,
    GreenInfrastructureScoreResponse,
)
from app.services.green_infrastructure import (
    IMPACT_DISCLAIMER,
    METHODOLOGY,
    score_green_infrastructure,
)
from app.services.population_exposure import score_exposure
from app.services.traffic_provider import get_traffic_reading
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/green-infrastructure", tags=["Green Infrastructure"])


@router.get("/priority", response_model=APIResponse[GreenInfrastructureReportResponse])
async def get_green_infrastructure_priority(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[GreenInfrastructureReportResponse]:
    station_repo = MonitoringStationRepository(session)
    reading_repo = AQIReadingRepository(session)

    demo_result = await session.execute(
        select(WardDemographics).where(
            WardDemographics.city == city, WardDemographics.is_deleted.is_(False)
        )
    )
    demographics_by_ward = {d.ward_id: d for d in demo_result.scalars().all()}
    all_populations = [
        d.population for d in demographics_by_ward.values() if d.population is not None
    ]

    stations = await station_repo.get_active_by_city(city)
    wards_seen: dict[str, object] = {}
    for station in stations:
        if not station.ward_id or station.ward_id in wards_seen:
            continue
        reading = await reading_repo.get_latest_by_station(station.id)
        if reading is not None:
            wards_seen[station.ward_id] = reading

    now = datetime.now(timezone.utc)
    scores: list[GreenInfrastructureScoreResponse] = []
    missing_green_cover: list[str] = []

    for ward_id, reading in wards_seen.items():
        demo = demographics_by_ward.get(ward_id)

        exposure = score_exposure(
            ward_id=ward_id,
            aqi=reading.aqi,
            pm25=reading.pm25,
            pm10=reading.pm10,
            no2=reading.no2,
            co=reading.co,
            population=demo.population if demo else None,
            sensitive_sites_count=demo.sensitive_sites_count if demo else None,
            all_city_populations=all_populations,
        )
        traffic = get_traffic_reading(now, ward_id=ward_id)

        green_cover_pct = demo.green_cover_pct if demo else None
        if green_cover_pct is None:
            missing_green_cover.append(ward_id)

        result = score_green_infrastructure(
            ward_id=ward_id,
            aqi=reading.aqi,
            pm25=reading.pm25,
            pm10=reading.pm10,
            no2=reading.no2,
            co=reading.co,
            exposure_level=exposure.exposure_level,
            traffic_level=traffic.level,
            green_cover_pct=green_cover_pct,
        )

        scores.append(
            GreenInfrastructureScoreResponse(
                ward_id=result.ward_id,
                aqi=result.aqi,
                pollution_risk=result.pollution_risk.value,
                exposure_level=result.exposure_level.value,
                traffic_level=result.traffic_level.value,
                green_cover_pct=result.green_cover_pct,
                is_green_cover_configured=result.is_green_cover_configured,
                priority=result.priority.value,
                priority_score=result.priority_score,
                recommended_intervention=result.recommended_intervention.value,
                rationale=result.rationale,
            )
        )

    scores.sort(key=lambda s: s.priority_score, reverse=True)

    return APIResponse(
        data=GreenInfrastructureReportResponse(
            city=city,
            scores=scores,
            methodology=METHODOLOGY,
            impact_disclaimer=IMPACT_DISCLAIMER,
            wards_missing_green_cover_data=missing_green_cover,
        )
    )
