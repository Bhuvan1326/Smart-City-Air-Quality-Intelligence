"""Ward demographics (admin-entered) and population exposure scoring.

No population figure is ever seeded or guessed by this platform — see
app/models/demographics.py and app/services/population_exposure.py for the
reasoning. Administrators enter population/sensitive-site counts here from
an authoritative source (e.g. census data), cited in `source_note`.
"""

from typing import Annotated

from app.api.deps import CurrentUser, RequireAdmin, get_db
from app.models.demographics import WardDemographics
from app.repositories.aqi import AQIReadingRepository, MonitoringStationRepository
from app.schemas.base import APIResponse
from app.schemas.demographics import (
    ExposureMapResponse,
    ExposureScoreResponse,
    WardDemographicsCreate,
    WardDemographicsResponse,
    WardDemographicsUpdate,
)
from app.services.population_exposure import METHODOLOGY, score_exposure
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

demographics_router = APIRouter(
    prefix="/exposure/demographics", tags=["Population Exposure"]
)
exposure_router = APIRouter(prefix="/exposure", tags=["Population Exposure"])


@demographics_router.get("", response_model=APIResponse[list[WardDemographicsResponse]])
async def list_demographics(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[list[WardDemographicsResponse]]:
    result = await session.execute(
        select(WardDemographics).where(
            WardDemographics.city == city, WardDemographics.is_deleted.is_(False)
        )
    )
    return APIResponse(
        data=[
            WardDemographicsResponse.model_validate(r) for r in result.scalars().all()
        ]
    )


@demographics_router.post(
    "",
    response_model=APIResponse[WardDemographicsResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[RequireAdmin],
)
async def create_demographics(
    data: WardDemographicsCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[WardDemographicsResponse]:
    existing = await session.execute(
        select(WardDemographics).where(
            WardDemographics.city == data.city,
            WardDemographics.ward_id == data.ward_id,
            WardDemographics.is_deleted.is_(False),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Demographics for ward '{data.ward_id}' in {data.city} already exist. Use PATCH to edit.",
        )
    record = WardDemographics(**data.model_dump())
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return APIResponse(
        data=WardDemographicsResponse.model_validate(record),
        message="Ward demographics recorded",
    )


@demographics_router.patch(
    "/{demographics_id}",
    response_model=APIResponse[WardDemographicsResponse],
    dependencies=[RequireAdmin],
)
async def update_demographics(
    demographics_id: str,
    data: WardDemographicsUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[WardDemographicsResponse]:
    result = await session.execute(
        select(WardDemographics).where(
            WardDemographics.id == demographics_id,
            WardDemographics.is_deleted.is_(False),
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ward demographics record not found",
        )
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    await session.flush()
    await session.refresh(record)
    return APIResponse(
        data=WardDemographicsResponse.model_validate(record),
        message="Ward demographics updated",
    )


@exposure_router.get("/map", response_model=APIResponse[ExposureMapResponse])
async def get_exposure_map(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[ExposureMapResponse]:
    """Estimated environmental exposure per ward, combining current AQI with
    admin-entered population data. Wards with no population record on file
    are returned with exposure_level="unavailable" — never a guessed value.
    """
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
    wards_seen: dict[str, tuple] = {}
    for station in stations:
        if not station.ward_id or station.ward_id in wards_seen:
            continue
        reading = await reading_repo.get_latest_by_station(station.id)
        if reading is not None:
            wards_seen[station.ward_id] = reading

    scores: list[ExposureScoreResponse] = []
    missing_population: list[str] = []
    for ward_id, reading in wards_seen.items():
        demo = demographics_by_ward.get(ward_id)
        result = score_exposure(
            ward_id=ward_id,
            aqi=reading.aqi,
            pm25=reading.pm25,
            pm10=reading.pm10,
            no2=reading.no2,
            co=reading.co,
            o3=reading.o3,
            population=demo.population if demo else None,
            sensitive_sites_count=demo.sensitive_sites_count if demo else None,
            all_city_populations=all_populations,
        )
        if not result.is_population_data_configured:
            missing_population.append(ward_id)
        scores.append(
            ExposureScoreResponse(
                ward_id=result.ward_id,
                aqi=result.aqi,
                pollution_risk=result.pollution_risk.value,
                primary_pollutant=result.primary_pollutant,
                population=result.population,
                population_band=(
                    result.population_band.value if result.population_band else None
                ),
                sensitive_sites_count=result.sensitive_sites_count,
                exposure_level=result.exposure_level.value,
                is_population_data_configured=result.is_population_data_configured,
            )
        )

    return APIResponse(
        data=ExposureMapResponse(
            city=city,
            scores=scores,
            methodology=METHODOLOGY,
            wards_missing_population_data=missing_population,
        )
    )
