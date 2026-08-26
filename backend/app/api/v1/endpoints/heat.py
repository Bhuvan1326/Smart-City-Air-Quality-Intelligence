"""Urban Heat-Island Intelligence endpoint.

Combines a genuinely live current-temperature reading (Open-Meteo, see
app/services/weather_provider.py) with an optional satellite vegetation
signal (Sentinel-2 NDVI, see app/services/satellite/sentinel_hub.py — the
same client already used for construction-dust attribution, reused here
rather than duplicated) into a CALCULATED heat-risk assessment. See
app/services/urban_heat.py for the full methodology and honesty rules:
no land-surface-temperature or built-up-density value is ever reported
since this platform has no such data source, and a failed live weather
call returns UNAVAILABLE rather than a fabricated temperature.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser
from app.schemas.base import APIResponse
from app.schemas.heat import HeatAssessmentResponse
from app.services.satellite.sentinel_hub import SentinelHubClient
from app.services.urban_heat import METHODOLOGY, assess_heat_risk
from app.services.weather_provider import get_current_weather
from app.workers.tasks.satellite import WARD_BBOXES

router = APIRouter(prefix="/heat", tags=["Urban Heat Intelligence"])


@router.get("/current", response_model=APIResponse[HeatAssessmentResponse])
async def get_current_heat_assessment(
    current_user: CurrentUser,
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    ward_id: str | None = Query(default=None),
) -> APIResponse[HeatAssessmentResponse]:
    fetched_at = datetime.now(UTC)
    weather = await get_current_weather(latitude, longitude)

    if weather is None:
        return APIResponse(
            data=HeatAssessmentResponse(
                latitude=latitude,
                longitude=longitude,
                ward_id=ward_id,
                air_temperature_c=None,
                air_temperature_source_type="unavailable",
                air_temperature_provider=None,
                air_temperature_observed_at=None,
                apparent_temperature_c=None,
                vegetation_data_available=False,
                mean_ndvi=None,
                ndvi_source_type=None,
                ndvi_observed_date=None,
                heat_risk=None,
                base_risk_from_temperature=None,
                escalated_for_low_vegetation=False,
                cooling_priority=False,
                rationale=[
                    "Live weather provider (Open-Meteo) did not return a "
                    "value for this location — no temperature was fabricated, "
                    "so no heat-risk assessment could be calculated."
                ],
                methodology=METHODOLOGY,
                fetched_at=fetched_at,
            )
        )

    mean_ndvi: float | None = None
    ndvi_observed_date: date | None = None
    if ward_id and ward_id in WARD_BBOXES:
        sentinel = SentinelHubClient()
        if sentinel.is_configured:
            week_ago = fetched_at.date().fromordinal(fetched_at.date().toordinal() - 14)
            band_summary = await sentinel.fetch_ward_indices(
                ward_id, WARD_BBOXES[ward_id], week_ago, fetched_at.date()
            )
            if band_summary is not None and band_summary.mean_ndvi is not None:
                mean_ndvi = band_summary.mean_ndvi
                ndvi_observed_date = band_summary.observed_date

    assessment = assess_heat_risk(
        latitude=latitude,
        longitude=longitude,
        air_temperature_c=weather.temperature_c,
        air_temperature_observed_at=weather.observed_at,
        apparent_temperature_c=weather.apparent_temperature_c,
        weather_provider=weather.provider,
        ward_id=ward_id,
        mean_ndvi=mean_ndvi,
        ndvi_observed_date=ndvi_observed_date,
    )

    return APIResponse(
        data=HeatAssessmentResponse(
            latitude=latitude,
            longitude=longitude,
            ward_id=ward_id,
            air_temperature_c=assessment.air_temperature_c,
            air_temperature_source_type="live",
            air_temperature_provider=assessment.weather_provider,
            air_temperature_observed_at=assessment.air_temperature_observed_at,
            apparent_temperature_c=assessment.apparent_temperature_c,
            vegetation_data_available=assessment.vegetation_data_available,
            mean_ndvi=assessment.mean_ndvi,
            ndvi_source_type=(
                "satellite_observation"
                if assessment.vegetation_data_available
                else None
            ),
            ndvi_observed_date=assessment.ndvi_observed_date,
            heat_risk=assessment.heat_risk.value,
            base_risk_from_temperature=assessment.base_risk_from_temperature.value,
            escalated_for_low_vegetation=assessment.escalated_for_low_vegetation,
            cooling_priority=assessment.cooling_priority,
            rationale=assessment.rationale,
            methodology=assessment.methodology,
            fetched_at=fetched_at,
        )
    )
