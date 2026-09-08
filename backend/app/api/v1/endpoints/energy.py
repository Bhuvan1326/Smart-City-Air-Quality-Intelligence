"""Urban Energy Intelligence endpoint.

See app/services/energy_provider.py for the provider hierarchy and the
data-truthfulness rules this follows: values are only ever LIVE, CSV
("latest available"), or explicit DEMO — never a fabricated substitute
for a missing live source.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser
from app.core.config import settings
from app.schemas.base import APIResponse
from app.schemas.energy import (
    EnergyReadingResponse,
    FuelMixResponse,
    FuelSourceItem,
    RenewableTrendResponse,
    YearlyStats,
)
from app.services.data_freshness import FreshnessStatus, classify_freshness
from app.services.energy_provider import (
    EnergyDataSource,
    get_fuel_mix,
    get_grid_carbon_intensity,
    get_renewable_trend,
)

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


@router.get("/fuel-mix", response_model=APIResponse[FuelMixResponse])
async def get_fuel_mix_endpoint(
    current_user: CurrentUser,
) -> APIResponse[FuelMixResponse]:
    """India national grid fuel mix breakdown (% per source) from the CEA
    dataset. Not real-time — reflects the most recent day in the local CSV.
    """
    if not settings.ENERGY_CSV_PATH:
        raise HTTPException(status_code=503, detail="ENERGY_CSV_PATH is not configured.")

    reading = get_fuel_mix(settings.ENERGY_CSV_PATH)
    if reading is None:
        raise HTTPException(status_code=503, detail="No fuel mix data available in the configured CSV.")

    return APIResponse(
        data=FuelMixResponse(
            sources=[
                FuelSourceItem(
                    name=s.name,
                    value_mw=s.value_mw,
                    percentage=s.percentage,
                    category=s.category,
                )
                for s in reading.sources
            ],
            total_mw=reading.total_mw,
            as_of=reading.as_of,
            renewable_pct=reading.renewable_pct,
            fossil_pct=reading.fossil_pct,
            nuclear_pct=reading.nuclear_pct,
            note=(
                f"India national grid generation mix as of {reading.as_of}. "
                "Source: Central Electricity Authority (CEA). "
                "Applies to all Indian cities — city-level breakdowns are not available in this dataset."
            ),
        )
    )


@router.get("/renewable-trend", response_model=APIResponse[RenewableTrendResponse])
async def get_renewable_trend_endpoint(
    current_user: CurrentUser,
) -> APIResponse[RenewableTrendResponse]:
    """India national grid renewable share by year (2018 → present), derived
    from the CEA daily generation dataset. Renewable = hydro + wind + solar + biomass.
    """
    if not settings.ENERGY_CSV_PATH:
        raise HTTPException(status_code=503, detail="ENERGY_CSV_PATH is not configured.")

    trend = get_renewable_trend(settings.ENERGY_CSV_PATH)
    if not trend:
        raise HTTPException(status_code=503, detail="No trend data available in the configured CSV.")

    return APIResponse(
        data=RenewableTrendResponse(
            trend=[
                YearlyStats(
                    year=y.year,
                    renewable_pct=y.renewable_pct,
                    fossil_pct=y.fossil_pct,
                    nuclear_pct=y.nuclear_pct,
                )
                for y in trend
            ],
            note=(
                "India national grid renewable share by year. "
                "Source: Central Electricity Authority (CEA). "
                "Renewable = hydro + wind + solar + biomass."
            ),
        )
    )
