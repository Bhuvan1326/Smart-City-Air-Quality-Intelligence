"""Urban Heat-Island Intelligence endpoints.

Combines a genuinely live current-temperature reading (Open-Meteo) with an
optional satellite vegetation signal (Sentinel-2 NDVI) into a CALCULATED
heat-risk assessment. New endpoints add hourly forecast, 7-day outlook,
ward-level parallel assessment, and 30-day history from the heat_readings
table.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.core.config import settings
from app.models.heat import HeatReading
from app.schemas.base import APIResponse
from app.schemas.heat import (
    HeatAssessmentResponse,
    HeatForecastDay,
    HeatForecastResponse,
    HeatHistoryPoint,
    HeatHistoryResponse,
    HeatHourlyPoint,
    HeatHourlyResponse,
    WardHeatAssessment,
    WardHeatResponse,
)
from app.services.satellite.sentinel_hub import SentinelHubClient
from app.services.urban_heat import (
    METHODOLOGY,
    _band_for_temperature,
    assess_heat_risk,
    compute_heat_index,
)
from app.services.weather_provider import get_current_weather
from app.workers.tasks.satellite import WARD_BBOXES

DBSession = Annotated[AsyncSession, Depends(get_db)]

router = APIRouter(prefix="/heat", tags=["Urban Heat Intelligence"])

_OPEN_METEO_TIMEOUT = 8.0


# ---------------------------------------------------------------------------
# /current — existing endpoint, now also persists to heat_readings
# ---------------------------------------------------------------------------

@router.get("/current", response_model=APIResponse[HeatAssessmentResponse])
async def get_current_heat_assessment(
    current_user: CurrentUser,
    db: DBSession,
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    ward_id: str | None = Query(default=None),
    city: str | None = Query(default=None),
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
                relative_humidity_pct=None,
                heat_index_c=None,
                vegetation_data_available=False,
                mean_ndvi=None,
                ndvi_source_type=None,
                ndvi_observed_date=None,
                heat_risk=None,
                base_risk_from_temperature=None,
                escalated_for_low_vegetation=False,
                heat_index_used_for_risk=False,
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
        relative_humidity_pct=weather.relative_humidity_pct,
        weather_provider=weather.provider,
        ward_id=ward_id,
        mean_ndvi=mean_ndvi,
        ndvi_observed_date=ndvi_observed_date,
    )

    # Persist to history (fire-and-forget — never block response on DB write)
    try:
        reading = HeatReading(
            recorded_at=fetched_at,
            city=city,
            latitude=latitude,
            longitude=longitude,
            ward_id=ward_id,
            air_temperature_c=assessment.air_temperature_c,
            apparent_temperature_c=assessment.apparent_temperature_c,
            relative_humidity_pct=assessment.relative_humidity_pct,
            heat_index_c=assessment.heat_index_c,
            heat_risk=assessment.heat_risk.value,
            mean_ndvi=assessment.mean_ndvi,
            cooling_priority=assessment.cooling_priority,
        )
        db.add(reading)
        await db.commit()
    except Exception:  # noqa: BLE001
        await db.rollback()

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
            relative_humidity_pct=assessment.relative_humidity_pct,
            heat_index_c=assessment.heat_index_c,
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
            heat_index_used_for_risk=assessment.heat_index_used_for_risk,
            cooling_priority=assessment.cooling_priority,
            rationale=assessment.rationale,
            methodology=assessment.methodology,
            fetched_at=fetched_at,
        )
    )


# ---------------------------------------------------------------------------
# /hourly — today's 24-hour temperature + risk strip
# ---------------------------------------------------------------------------

@router.get("/hourly", response_model=APIResponse[HeatHourlyResponse])
async def get_hourly_forecast(
    current_user: CurrentUser,
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
) -> APIResponse[HeatHourlyResponse]:
    fetched_at = datetime.now(UTC)
    url = f"{settings.OPEN_METEO_BASE_URL}/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,apparent_temperature,relative_humidity_2m",
        "forecast_days": 1,
        "timezone": "UTC",
    }
    try:
        async with httpx.AsyncClient(timeout=_OPEN_METEO_TIMEOUT) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return APIResponse(data=HeatHourlyResponse(hours=[], fetched_at=fetched_at))
            payload = resp.json()
    except Exception:  # noqa: BLE001
        return APIResponse(data=HeatHourlyResponse(hours=[], fetched_at=fetched_at))

    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    apparent = hourly.get("apparent_temperature", [])
    humidity = hourly.get("relative_humidity_2m", [])

    points: list[HeatHourlyPoint] = []
    for i, t in enumerate(times):
        temp_c = temps[i] if i < len(temps) and temps[i] is not None else None
        if temp_c is None:
            continue
        rh = humidity[i] if i < len(humidity) and humidity[i] is not None else None
        hi = compute_heat_index(temp_c, rh) if rh is not None else None
        risk_temp = hi if (hi is not None and hi > temp_c) else temp_c
        risk = _band_for_temperature(risk_temp)

        try:
            dt = datetime.fromisoformat(str(t))
        except ValueError:
            continue

        hour_label = dt.strftime("%-I %p").lstrip("0") if hasattr(dt, "strftime") else t

        points.append(
            HeatHourlyPoint(
                hour=t,
                hour_label=hour_label,
                temperature_c=round(temp_c, 1),
                apparent_temperature_c=round(apparent[i], 1) if i < len(apparent) and apparent[i] is not None else None,
                relative_humidity_pct=round(rh, 1) if rh is not None else None,
                heat_index_c=round(hi, 1) if hi is not None else None,
                heat_risk=risk.value,
            )
        )

    return APIResponse(data=HeatHourlyResponse(hours=points, fetched_at=fetched_at))


# ---------------------------------------------------------------------------
# /forecast — 7-day daily outlook
# ---------------------------------------------------------------------------

@router.get("/forecast", response_model=APIResponse[HeatForecastResponse])
async def get_daily_forecast(
    current_user: CurrentUser,
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
) -> APIResponse[HeatForecastResponse]:
    fetched_at = datetime.now(UTC)
    url = f"{settings.OPEN_METEO_BASE_URL}/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "temperature_2m_max,apparent_temperature_max,relative_humidity_2m_mean,precipitation_sum",
        "forecast_days": 7,
        "timezone": "UTC",
    }
    try:
        async with httpx.AsyncClient(timeout=_OPEN_METEO_TIMEOUT) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return APIResponse(data=HeatForecastResponse(days=[], fetched_at=fetched_at))
            payload = resp.json()
    except Exception:  # noqa: BLE001
        return APIResponse(data=HeatForecastResponse(days=[], fetched_at=fetched_at))

    daily = payload.get("daily", {})
    dates = daily.get("time", [])
    max_temps = daily.get("temperature_2m_max", [])
    apparent_max = daily.get("apparent_temperature_max", [])
    mean_humidity = daily.get("relative_humidity_2m_mean", [])
    precip = daily.get("precipitation_sum", [])

    days: list[HeatForecastDay] = []
    for i, d in enumerate(dates):
        temp_c = max_temps[i] if i < len(max_temps) and max_temps[i] is not None else None
        if temp_c is None:
            continue
        rh = mean_humidity[i] if i < len(mean_humidity) and mean_humidity[i] is not None else None
        hi = compute_heat_index(temp_c, rh) if rh is not None else None
        risk_temp = hi if (hi is not None and hi > temp_c) else temp_c
        risk = _band_for_temperature(risk_temp)

        try:
            day_date = date.fromisoformat(str(d))
            date_label = day_date.strftime("%a %b %d").replace(" 0", " ")
        except ValueError:
            date_label = str(d)

        days.append(
            HeatForecastDay(
                date=d,
                date_label=date_label,
                max_temperature_c=round(temp_c, 1),
                apparent_temperature_max_c=round(apparent_max[i], 1) if i < len(apparent_max) and apparent_max[i] is not None else None,
                mean_humidity_pct=round(rh, 1) if rh is not None else None,
                precipitation_mm=round(precip[i], 1) if i < len(precip) and precip[i] is not None else None,
                heat_risk=risk.value,
            )
        )

    return APIResponse(data=HeatForecastResponse(days=days, fetched_at=fetched_at))


# ---------------------------------------------------------------------------
# /wards — parallel ward-level heat assessment (Pune only)
# ---------------------------------------------------------------------------

async def _assess_ward(
    ward_id: str,
    bbox: tuple[float, float, float, float],
) -> WardHeatAssessment:
    min_lon, min_lat, max_lon, max_lat = bbox
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2

    weather = await get_current_weather(center_lat, center_lon)
    if weather is None:
        return WardHeatAssessment(
            ward_id=ward_id,
            bbox=list(bbox),
            center_lat=center_lat,
            center_lon=center_lon,
            temperature_c=None,
            heat_risk=None,
            mean_ndvi=None,
            cooling_priority=False,
        )

    assessment = assess_heat_risk(
        latitude=center_lat,
        longitude=center_lon,
        air_temperature_c=weather.temperature_c,
        air_temperature_observed_at=weather.observed_at,
        apparent_temperature_c=weather.apparent_temperature_c,
        relative_humidity_pct=weather.relative_humidity_pct,
        ward_id=ward_id,
    )

    return WardHeatAssessment(
        ward_id=ward_id,
        bbox=list(bbox),
        center_lat=center_lat,
        center_lon=center_lon,
        temperature_c=round(assessment.air_temperature_c, 1),
        heat_risk=assessment.heat_risk.value,
        mean_ndvi=None,  # NDVI fetch skipped in parallel ward mode (rate-limit sensitive)
        cooling_priority=assessment.cooling_priority,
    )


@router.get("/wards", response_model=APIResponse[WardHeatResponse])
async def get_ward_heat_assessment(
    current_user: CurrentUser,
) -> APIResponse[WardHeatResponse]:
    fetched_at = datetime.now(UTC)
    results = await asyncio.gather(
        *[_assess_ward(ward_id, bbox) for ward_id, bbox in WARD_BBOXES.items()],
        return_exceptions=True,
    )
    wards = [r for r in results if isinstance(r, WardHeatAssessment)]
    return APIResponse(data=WardHeatResponse(wards=wards, fetched_at=fetched_at))


# ---------------------------------------------------------------------------
# /history — 30-day trend from heat_readings table
# ---------------------------------------------------------------------------

@router.get("/history", response_model=APIResponse[HeatHistoryResponse])
async def get_heat_history(
    current_user: CurrentUser,
    db: DBSession,
    city: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=90),
) -> APIResponse[HeatHistoryResponse]:
    fetched_at = datetime.now(UTC)

    # One reading per day — pick the latest reading for each calendar day
    if city:
        stmt = (
            select(HeatReading)
            .where(
                HeatReading.city == city,
                HeatReading.is_deleted.is_(False),
                text(f"recorded_at >= now() - interval '{days} days'"),
            )
            .order_by(desc(HeatReading.recorded_at))
        )
    else:
        stmt = (
            select(HeatReading)
            .where(
                HeatReading.is_deleted.is_(False),
                text(f"recorded_at >= now() - interval '{days} days'"),
            )
            .order_by(desc(HeatReading.recorded_at))
        )

    result = await db.execute(stmt)
    rows = result.scalars().all()

    # Deduplicate: keep one row per calendar day (already DESC-ordered)
    seen_dates: set[str] = set()
    points: list[HeatHistoryPoint] = []
    for row in rows:
        day_key = row.recorded_at.strftime("%Y-%m-%d")
        if day_key in seen_dates:
            continue
        seen_dates.add(day_key)
        points.append(
            HeatHistoryPoint(
                recorded_at=row.recorded_at,
                date_label=row.recorded_at.strftime("%b %d").replace(" 0", " "),
                air_temperature_c=row.air_temperature_c,
                heat_index_c=row.heat_index_c,
                relative_humidity_pct=row.relative_humidity_pct,
                heat_risk=row.heat_risk,
                cooling_priority=row.cooling_priority,
            )
        )

    # Return in ascending chronological order for charts
    points.sort(key=lambda p: p.recorded_at)

    return APIResponse(
        data=HeatHistoryResponse(points=points, city=city, fetched_at=fetched_at)
    )
