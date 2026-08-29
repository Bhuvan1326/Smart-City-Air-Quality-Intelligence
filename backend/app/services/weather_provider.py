"""Current-weather provider.

Open-Meteo (https://open-meteo.com) is used elsewhere in this codebase for
ingestion-time forecast data (see app/workers/tasks/aqi_ingestion.py) but
there was no reusable, importable "give me the current weather for this
location" service — this module is that shared provider. Open-Meteo's
non-commercial tier is genuinely free and requires no API key
(https://open-meteo.com/en/pricing), and its `current=` parameter is a
real live observation/nowcast, not a forecast — so this is one of the few
metrics in this platform that can honestly be labeled LIVE without any
credential configuration at all.

Failure handling: any HTTP error, timeout, or malformed response returns
None — callers must treat that as UNAVAILABLE and must never substitute a
fabricated temperature.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from app.core.config import settings

_TIMEOUT_SECONDS = 6.0


@dataclass
class CurrentWeather:
    temperature_c: float
    apparent_temperature_c: float | None
    relative_humidity_pct: float | None
    wind_speed_kmh: float | None
    precipitation_mm: float | None
    observed_at: datetime
    provider: str = "Open-Meteo"


async def get_current_weather(
    latitude: float, longitude: float
) -> CurrentWeather | None:
    """Live current-weather reading for a location. Returns None (never
    raises) on any failure — callers must report UNAVAILABLE rather than
    invent a value.
    """
    url = f"{settings.OPEN_METEO_BASE_URL}/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,"
            "precipitation,wind_speed_10m"
        ),
        "timezone": "UTC",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(url, params=params)
            if response.status_code != 200:
                return None
            payload = response.json()
    except Exception:  # noqa: BLE001 -- optional live provider, must fail open
        return None

    current = payload.get("current")
    if not current:
        return None
    temperature = current.get("temperature_2m")
    raw_time = current.get("time")
    if temperature is None or raw_time is None:
        return None

    try:
        observed_at = datetime.fromisoformat(str(raw_time))
    except ValueError:
        return None
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)

    return CurrentWeather(
        temperature_c=float(temperature),
        apparent_temperature_c=(
            float(current["apparent_temperature"])
            if current.get("apparent_temperature") is not None
            else None
        ),
        relative_humidity_pct=(
            float(current["relative_humidity_2m"])
            if current.get("relative_humidity_2m") is not None
            else None
        ),
        wind_speed_kmh=(
            float(current["wind_speed_10m"])
            if current.get("wind_speed_10m") is not None
            else None
        ),
        precipitation_mm=(
            float(current["precipitation"])
            if current.get("precipitation") is not None
            else None
        ),
        observed_at=observed_at,
    )
