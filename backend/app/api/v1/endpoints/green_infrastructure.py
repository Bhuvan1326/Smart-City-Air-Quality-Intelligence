"""Green Infrastructure Optimization endpoint.

Ranks Pune's six real, OpenAQ-matched monitoring stations (see
app.services.aqi_providers.pune_stations.REQUIRED_STATIONS) for
tree-planting / green-corridor investment by combining current pollution
severity with whatever population-exposure, traffic, and green-cover
inputs genuinely exist — never fabricating any of them. See
app/services/green_infrastructure.py for the scoring methodology and its
explicit no-fabricated-impact guarantee.

This intentionally mirrors the six-station, never-fabricate pattern
already used by GET /aqi/live (see `_get_pune_live_aqi` in
app/api/v1/endpoints/aqi.py):

- Exactly the six required stations are considered — never the legacy
  W01-W08 CAAQMS ward fixtures, which are a separate, unrelated
  station set used by other features (see the note in
  app/workers/tasks/aqi_ingestion.py).
- A station that hasn't been matched to a real OpenAQ location yet, has
  no valid (non-synthetic) reading, or whose latest reading has aged past
  the platform's shared freshness threshold (app.services.data_freshness)
  is reported as unavailable/stale rather than scored with a fabricated
  or outdated AQI.
- Traffic is only ever scored when a genuine live/configured reading
  exists. This platform has no live traffic provider (see
  app.services.traffic_provider), so traffic is always excluded here and
  reported as null with an explanatory rationale line.
- Population exposure and green cover are only scored when
  WardDemographics data is genuinely configured for the relevant area;
  the six real stations currently have no deterministic (non-fabricated)
  mapping onto that ward-fixture geography, so both are reported
  unavailable/unconfigured rather than guessed.
"""

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
from app.services.aqi_providers import pune_stations
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
    """An honest "no result" entry for one required station — never a
    fabricated AQI/priority. Used when the station hasn't been matched to
    a real OpenAQ location, has no valid live reading, or its latest
    reading is stale."""
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


@router.get("/priority", response_model=APIResponse[GreenInfrastructureReportResponse])
async def get_green_infrastructure_priority(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[GreenInfrastructureReportResponse]:
    if city.strip().lower() != "pune":
        # The real-time six-station pipeline (see pune_stations.py) is
        # Pune-specific. Rather than silently falling back to the
        # unrelated legacy ward-fixture data for other cities, say so
        # plainly and return no scores.
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

    scores: list[GreenInfrastructureScoreResponse] = []
    missing_green_cover: list[str] = []
    unavailable: list[str] = []

    for spec in pune_stations.REQUIRED_STATIONS:
        station = stations_by_code.get(spec.station_code)
        if station is None:
            scores.append(
                _unavailable_result(
                    spec,
                    reason=(
                        "This station has not yet been matched to a real "
                        "OpenAQ location — no reading is available."
                    ),
                )
            )
            unavailable.append(spec.display_name)
            continue

        reading = await reading_repo.get_latest_valid_by_station(station.id)
        if reading is None:
            scores.append(
                _unavailable_result(
                    spec,
                    reason="No fresh live AQI reading is currently available from OpenAQ.",
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
                        "The latest reading for this station is older than the "
                        "freshness threshold and was not used as current AQI."
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

        # Population exposure: no deterministic mapping exists from these
        # six real stations to the WardDemographics ward fixtures (see
        # module docstring), so population/sensitive-site inputs are
        # never supplied here — score_exposure reports this honestly as
        # ExposureLevel.UNAVAILABLE rather than defaulting anything.
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

        # Traffic: this platform has no live traffic provider (see
        # app.services.traffic_provider) — its only implementations are a
        # time-of-day heuristic and a static CSV, neither of which is a
        # genuine live/real-time reading, so neither is used to score a
        # feature presented as real-time.
        traffic_level = None

        # Green cover: same reasoning as population above — no genuine,
        # non-fabricated green-cover figure is on file for these station
        # areas, so this is always reported unconfigured here.
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
                recommended_intervention=result.recommended_intervention.value,
                rationale=result.rationale,
                reading_timestamp=reading.timestamp,
                data_source="OpenAQ",
                is_live=True,
                is_synthetic=False,
                status="ok",
            )
        )

    # Stations with a genuine score sort by priority_score (highest
    # first); unavailable/stale entries (priority_score=None) sort last
    # rather than being coerced into a fake 0/low ranking.
    scores.sort(
        key=lambda s: (s.priority_score is not None, s.priority_score or 0),
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
