"""Water–Climate Intelligence endpoint.

Combines a genuinely live precipitation/temperature/humidity reading
(Open-Meteo, via app/services/weather_provider.py — the same provider
built for Urban Heat Intelligence, reused rather than duplicated) with
admin-entered municipal water data (app.models.water_resource.
CityWaterResource) into a CALCULATED flood/drought/water-stress
assessment. See app/services/water_climate.py for the full methodology
and the honesty rules: no rainfall anomaly is ever computed (no
climatological baseline available), and drought/water-stress are
Unavailable — never guessed from rainfall alone — when no reservoir
figure is on file for the city.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, RequireAdmin, get_db
from app.models.water_resource import CityWaterResource
from app.schemas.base import APIResponse
from app.schemas.water import (
    CityWaterResourceCreate,
    CityWaterResourceResponse,
    CityWaterResourceUpdate,
    WaterClimateResponse,
)
from app.services.water_climate import assess_water_climate
from app.services.weather_provider import get_current_weather

router = APIRouter(prefix="/water", tags=["Water-Climate Intelligence"])


@router.get("/current", response_model=APIResponse[WaterClimateResponse])
async def get_current_water_climate(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    city: str = Query(default="Pune"),
) -> APIResponse[WaterClimateResponse]:
    fetched_at = datetime.now(UTC)
    weather = await get_current_weather(latitude, longitude)

    result = await session.execute(
        select(CityWaterResource).where(
            CityWaterResource.city == city, CityWaterResource.is_deleted.is_(False)
        )
    )
    water_resource = result.scalar_one_or_none()

    assessment = assess_water_climate(
        city=city,
        latitude=latitude,
        longitude=longitude,
        precipitation_mm=weather.precipitation_mm if weather else None,
        temperature_c=weather.temperature_c if weather else None,
        relative_humidity_pct=weather.relative_humidity_pct if weather else None,
        weather_observed_at=weather.observed_at if weather else None,
        weather_provider=weather.provider if weather else None,
        reservoir_level_pct=(
            water_resource.reservoir_level_pct if water_resource else None
        ),
        water_consumption_mld=(
            water_resource.water_consumption_mld if water_resource else None
        ),
        groundwater_level_m=(
            water_resource.groundwater_level_m if water_resource else None
        ),
        municipal_data_as_of=water_resource.data_as_of if water_resource else None,
    )

    return APIResponse(
        data=WaterClimateResponse(
            city=assessment.city,
            latitude=assessment.latitude,
            longitude=assessment.longitude,
            precipitation_mm=assessment.precipitation_mm,
            temperature_c=assessment.temperature_c,
            relative_humidity_pct=assessment.relative_humidity_pct,
            weather_observed_at=assessment.weather_observed_at,
            weather_provider=assessment.weather_provider,
            weather_available=assessment.weather_available,
            reservoir_level_pct=assessment.reservoir_level_pct,
            water_consumption_mld=assessment.water_consumption_mld,
            groundwater_level_m=assessment.groundwater_level_m,
            municipal_data_as_of=assessment.municipal_data_as_of,
            municipal_data_available=assessment.municipal_data_available,
            flood_conducive_risk=(
                assessment.flood_conducive_risk.value
                if assessment.flood_conducive_risk
                else None
            ),
            drought_risk=(
                assessment.drought_risk.value if assessment.drought_risk else None
            ),
            water_stress=(
                assessment.water_stress.value if assessment.water_stress else None
            ),
            rationale=assessment.rationale,
            methodology=assessment.methodology,
            fetched_at=fetched_at,
        )
    )


@router.get("/resource", response_model=APIResponse[CityWaterResourceResponse | None])
async def get_water_resource(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[CityWaterResourceResponse | None]:
    result = await session.execute(
        select(CityWaterResource).where(
            CityWaterResource.city == city, CityWaterResource.is_deleted.is_(False)
        )
    )
    record = result.scalar_one_or_none()
    return APIResponse(
        data=CityWaterResourceResponse.model_validate(record) if record else None
    )


@router.post(
    "/resource",
    response_model=APIResponse[CityWaterResourceResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[RequireAdmin],
)
async def create_water_resource(
    data: CityWaterResourceCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[CityWaterResourceResponse]:
    existing = await session.execute(
        select(CityWaterResource).where(
            CityWaterResource.city == data.city,
            CityWaterResource.is_deleted.is_(False),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Water resource data for '{data.city}' already exists. Use PATCH to edit.",
        )
    record = CityWaterResource(**data.model_dump())
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return APIResponse(
        data=CityWaterResourceResponse.model_validate(record),
        message="City water resource data recorded",
    )


@router.patch(
    "/resource/{resource_id}",
    response_model=APIResponse[CityWaterResourceResponse],
    dependencies=[RequireAdmin],
)
async def update_water_resource(
    resource_id: str,
    data: CityWaterResourceUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[CityWaterResourceResponse]:
    result = await session.execute(
        select(CityWaterResource).where(
            CityWaterResource.id == resource_id,
            CityWaterResource.is_deleted.is_(False),
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="City water resource record not found",
        )
    for field_name, value in data.model_dump(exclude_unset=True).items():
        setattr(record, field_name, value)
    await session.flush()
    await session.refresh(record)
    return APIResponse(
        data=CityWaterResourceResponse.model_validate(record),
        message="City water resource data updated",
    )
