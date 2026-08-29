"""Urban Energy Intelligence endpoint.

See app/services/energy_provider.py for the provider hierarchy and the
data-truthfulness rules this follows: values are only ever LIVE, CSV
("latest available"), or explicit DEMO — never a fabricated substitute
for a missing live source.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.api.deps import CurrentUser
from app.schemas.base import APIResponse
from app.schemas.energy import EnergyReadingResponse
from app.services.data_freshness import FreshnessStatus, classify_freshness
from app.services.energy_provider import EnergyDataSource, get_grid_carbon_intensity
from fastapi import APIRouter, Query

router = APIRouter(prefix="/energy", tags=["Urban Energy Intelligence"])


@router.get(
    "/grid-carbon-intensity",
    response_model=APIResponse[EnergyReadingResponse],
)
async def get_grid_carbon_intensity_endpoint(
    current_user: CurrentUser,
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    city: str | None = Query(default=None),
) -> APIResponse[EnergyReadingResponse]:
    """Grid carbon intensity (gCO2eq/kWh) for a location, via the energy
    provider hierarchy (live -> csv -> demo -> unavailable). Never returns
    a fabricated value: an UNAVAILABLE source_type means value is null.
    """
    reading = await get_grid_carbon_intensity(latitude, longitude, city)
    fetched_at = datetime.now(UTC)

    if reading.source == EnergyDataSource.UNAVAILABLE:
        freshness = FreshnessStatus.UNAVAILABLE
    else:
        freshness = classify_freshness(
            reading.observed_at, is_synthetic=reading.source == EnergyDataSource.DEMO
        )

    data_age_seconds: float | None = None
    if reading.observed_at is not None:
        observed = (
            reading.observed_at
            if reading.observed_at.tzinfo
            else reading.observed_at.replace(tzinfo=UTC)
        )
        data_age_seconds = max(0.0, (fetched_at - observed).total_seconds())

    return APIResponse(
        data=EnergyReadingResponse(
            metric=reading.metric,
            value=reading.value,
            unit=reading.unit,
            source_type=reading.source.value,
            provider=reading.provider,
            observed_at=reading.observed_at,
            fetched_at=fetched_at,
            data_age_seconds=data_age_seconds,
            freshness_status=freshness.value,
            note=reading.note,
            latitude=latitude,
            longitude=longitude,
            city=city,
        )
    )
