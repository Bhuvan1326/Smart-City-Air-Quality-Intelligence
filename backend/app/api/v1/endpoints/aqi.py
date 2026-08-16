from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.core.redis_client import cache_get, cache_set
from app.repositories.aqi import (AQIReadingRepository,
                                  MonitoringStationRepository)
from app.schemas.aqi import (AQIReadingResponse,
                             LiveAQIResponse, StationResponse,
                             get_aqi_category)
from app.schemas.base import APIResponse, PaginatedResponse

router = APIRouter(prefix="/aqi", tags=["AQI Monitoring"])


@router.get("/stations", response_model=APIResponse[PaginatedResponse[StationResponse]])
async def list_stations(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> APIResponse[PaginatedResponse[StationResponse]]:
    repo = MonitoringStationRepository(session)
    filters = {}
    if city:
        filters["city"] = city
    stations, total = await repo.get_all(
        skip=(page - 1) * page_size,
        limit=page_size,
        filters=filters,
    )
    items = [StationResponse.model_validate(s) for s in stations]
    return APIResponse(data=PaginatedResponse.create(items, total, page, page_size))


@router.get("/live", response_model=APIResponse[list[LiveAQIResponse]])
async def get_live_aqi(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(..., description="City name"),
) -> APIResponse[list[LiveAQIResponse]]:
    cache_key = f"live_aqi:{city}"
    cached = await cache_get(cache_key)
    if cached:
        return APIResponse(data=cached)

    station_repo = MonitoringStationRepository(session)
    reading_repo = AQIReadingRepository(session)
    stations = await station_repo.get_active_by_city(city)

    results: list[LiveAQIResponse] = []
    for station in stations:
        reading = await reading_repo.get_latest_by_station(station.id)
        if reading is None:
            continue
        category, health_msg = get_aqi_category(reading.aqi or 0)
        results.append(
            LiveAQIResponse(
                station=StationResponse.model_validate(station),
                reading=AQIReadingResponse.model_validate(reading),
                aqi_category=category,
                health_message=health_msg,
                trend="stable",  # computed by forecast service in production
                data_source=(
                    "openaq" if reading.quality_flag == "good" else "synthetic"
                ),
            )
        )

    serialized = [r.model_dump(mode="json") for r in results]
    await cache_set(cache_key, serialized, ttl=300)
    return APIResponse(data=results)


@router.get("/history", response_model=APIResponse[list[dict]])
async def get_aqi_history(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    station_id: UUID | None = Query(None),
    city: str | None = Query(None),
    ward_id: str | None = Query(None),
    start_time: datetime = Query(
        default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=7)
    ),
    end_time: datetime = Query(default_factory=lambda: datetime.now(timezone.utc)),
    interval: str = Query("1h", pattern="^(15m|1h|6h|24h)$"),
) -> APIResponse[list[dict]]:
    if not station_id and not city:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either station_id or city is required",
        )

    repo = AQIReadingRepository(session)
    data = await repo.get_history(station_id, start_time, end_time, interval)
    return APIResponse(data=data)
