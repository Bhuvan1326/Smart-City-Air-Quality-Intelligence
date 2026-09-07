from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.repositories.aqi import AQIReadingRepository, MonitoringStationRepository
from app.schemas.base import APIResponse
from app.schemas.green_infrastructure import (
    GreenInfrastructureReportResponse,
    GreenInfrastructureScoreResponse,
)
from app.services.aqi_providers import openaq, pune_stations
from app.services.data_freshness import classify_freshness
from app.services.green_infrastructure import (
    IMPACT_DISCLAIMER,
    METHODOLOGY,
    score_green_infrastructure,
)
from app.services.population_exposure import ExposureLevel, score_exposure

router = APIRouter(prefix="/green-infrastructure", tags=["Green Infrastructure"])


def _unavailable_result(
    spec: pune_stations.RequiredStation,
    *,
    reason: str,
    station_id: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    reading_timestamp=None,
    data_source: str = "unavailable",
    status: str = "unavailable",
) -> GreenInfrastructureScoreResponse:

    return GreenInfrastructureScoreResponse(
        station_id=station_id,
        station_code=spec.station_code,
        station_name=spec.display_name,
        operator=spec.provider,
        area=spec.display_name,
        latitude=latitude,
        longitude=longitude,
        aqi=None,
        pollution_risk=None,
        exposure_level=ExposureLevel.UNAVAILABLE.value,
        traffic_level=None,
        is_traffic_data_configured=False,
        green_cover_pct=None,
        is_green_cover_configured=False,
        priority=None,
        priority_score=None,
        recommended_intervention=None,
        rationale=[reason],
        reading_timestamp=reading_timestamp,
        data_source=data_source,
        is_live=False,
        is_synthetic=False,
        status=status,
    )


@router.get(
    "/priority",
    response_model=APIResponse[GreenInfrastructureReportResponse],
)
async def get_green_infrastructure_priority(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[GreenInfrastructureReportResponse]:
    if city.strip().lower() != "pune":

        return APIResponse(
            data=GreenInfrastructureReportResponse(
                city=city,
                scores=[],
                methodology=METHODOLOGY,
                impact_disclaimer=IMPACT_DISCLAIMER,
                stations_missing_green_cover_data=[],
                unavailable_stations=[
                    spec.display_name for spec in pune_stations.REQUIRED_STATIONS
                ],
            )
        )

    station_repo = MonitoringStationRepository(session)
    reading_repo = AQIReadingRepository(session)

    codes = [spec.station_code for spec in pune_stations.REQUIRED_STATIONS]
    stations_by_code = await station_repo.get_by_station_codes(codes)

    openaq_configured = openaq.is_configured()

    scores: list[GreenInfrastructureScoreResponse] = []
    missing_green_cover: list[str] = []
    unavailable: list[str] = []

    for spec in pune_stations.REQUIRED_STATIONS:
        station = stations_by_code.get(spec.station_code)

        if station is None:
            if not openaq_configured:
                reason = (
                    "The OpenAQ air-quality provider is not configured for "
                    "this deployment (OPENAQ_API_KEY is unset) — no station "
                    "can be resolved or scored until it is."
                )
            else:
                reason = (
                    "This station has not yet been matched to a real "
                    "OpenAQ location — no reading is available."
                )

            scores.append(
                _unavailable_result(
                    spec,
                    reason=reason,
                )
            )
            unavailable.append(spec.display_name)
            continue

        # A MonitoringStation row can exist before the OpenAQ resolver has
        # successfully attached an OpenAQ location ID. In that state the
        # station is still unresolved, even though a local database row
        # exists. Do NOT query its readings and report "no fresh reading":
        # that would hide the more important fact that the station itself
        # has not been matched to OpenAQ yet.
        if station.openaq_location_id is None:
            if not openaq_configured:
                reason = (
                    "The OpenAQ air-quality provider is not configured for "
                    "this deployment (OPENAQ_API_KEY is unset) — no station "
                    "can be resolved or scored until it is."
                )
            else:
                reason = (
                    "This station has not yet been matched to a real "
                    "OpenAQ location — no reading is available."
                )

            scores.append(
                _unavailable_result(
                    spec,
                    reason=reason,
                    station_id=str(station.id),
                    latitude=station.latitude,
                    longitude=station.longitude,
                )
            )
            unavailable.append(spec.display_name)
            continue

        reading = await reading_repo.get_latest_valid_by_station(station.id)

        if reading is None:
            scores.append(
                _unavailable_result(
                    spec,
                    reason=(
                        "No fresh live AQI reading is currently available "
                        "from OpenAQ."
                    ),
                    station_id=str(station.id),
                    latitude=station.latitude,
                    longitude=station.longitude,
                )
            )
            unavailable.append(spec.display_name)
            continue

        freshness = classify_freshness(
            reading.timestamp,
            is_synthetic=(reading.quality_flag == "synthetic"),
        )

        if not freshness.is_reliable:
            scores.append(
                _unavailable_result(
                    spec,
                    reason=(
                        "The latest reading for this station is older than "
                        "the freshness threshold and was not used as "
                        "current AQI."
                    ),
                    station_id=str(station.id),
                    latitude=station.latitude,
                    longitude=station.longitude,
                    reading_timestamp=reading.timestamp,
                    data_source="stale",
                    status="stale",
                )
            )
            unavailable.append(spec.display_name)
            continue

        exposure = score_exposure(
            ward_id=spec.station_code,
            aqi=reading.aqi,
            pm25=reading.pm25,
            pm10=reading.pm10,
            no2=reading.no2,
            co=reading.co,
            o3=reading.o3,
            population=None,
            sensitive_sites_count=None,
            all_city_populations=[],
        )
        traffic_level = None

        green_cover_pct = None
        missing_green_cover.append(spec.display_name)

        result = score_green_infrastructure(
            ward_id=spec.station_code,
            aqi=reading.aqi,
            pm25=reading.pm25,
            pm10=reading.pm10,
            no2=reading.no2,
            co=reading.co,
            o3=reading.o3,
            exposure_level=exposure.exposure_level,
            traffic_level=traffic_level,
            green_cover_pct=green_cover_pct,
        )

        scores.append(
            GreenInfrastructureScoreResponse(
                station_id=str(station.id),
                station_code=spec.station_code,
                station_name=spec.display_name,
                operator=station.operator or spec.provider,
                area=spec.display_name,
                latitude=station.latitude,
                longitude=station.longitude,
                aqi=result.aqi,
                pollution_risk=result.pollution_risk.value,
                exposure_level=result.exposure_level.value,
                traffic_level=(
                    result.traffic_level.value if result.traffic_level else None
                ),
                is_traffic_data_configured=result.is_traffic_data_configured,
                green_cover_pct=result.green_cover_pct,
                is_green_cover_configured=result.is_green_cover_configured,
                priority=result.priority.value,
                priority_score=result.priority_score,
                recommended_intervention=(result.recommended_intervention.value),
                rationale=result.rationale,
                reading_timestamp=reading.timestamp,
                data_source="OpenAQ",
                is_live=True,
                is_synthetic=False,
                status="ok",
            )
        )

    scores.sort(
        key=lambda s: (
            s.priority_score is not None,
            s.priority_score or 0,
        ),
        reverse=True,
    )

    return APIResponse(
        data=GreenInfrastructureReportResponse(
            city=city,
            scores=scores,
            methodology=METHODOLOGY,
            impact_disclaimer=IMPACT_DISCLAIMER,
            stations_missing_green_cover_data=missing_green_cover,
            unavailable_stations=unavailable,
        )
    )
