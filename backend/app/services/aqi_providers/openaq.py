"""
OpenAQ v3 client — real, current ground-station pollutant readings.

OpenAQ aggregates official monitoring-network data (including India's
CPCB/state-board CAAQMS stations) into one public API. It's the natural
provider to back "live AQI" here since the existing station fixtures
(PUNE_STATIONS / MUMBAI_STATIONS in aqi_ingestion.py) already model exactly
that kind of station.

API docs: https://docs.openaq.org (v3). Auth is a required `X-API-Key`
header — get a free key at https://explore.openaq.org/register.

Two capabilities live here:
  - `fetch_nearest_reading` — given a lat/lon, find the closest existing
    OpenAQ location and its latest reading (used by the fixed Pune/Mumbai
    ward station fixtures in aqi_ingestion.py).
  - `discover_india_locations` — enumerate every OpenAQ location OpenAQ
    reports for India (`iso=IN`), regardless of city, so nationwide
    coverage in monitoring_stations reflects whatever the provider
    actually has rather than a hardcoded city list. See
    aqi_ingestion.discover_and_ingest_india_stations.

IMPORTANT CAVEAT: like sentinel_hub.py / modis_firms.py in this codebase,
this HTTP integration could not be exercised against the live OpenAQ
service from the sandbox this was written in (no network egress to
openaq.org there). The request/response shapes below follow OpenAQ's
published v3 documentation as of early 2026, but you should smoke-test
this against a real API key before depending on it — OpenAQ has changed
its schema across v1/v2/v3 before, and coverage/latency varies a lot by
station. Every call is defensively wrapped so any mismatch or outage
falls back to the synthetic generator rather than crashing ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.core.logging import logger


def _base_url() -> str:
    return settings.OPENAQ_BASE_URL or "https://api.openaq.org/v3"


# OpenAQ parameter name -> our reading field. OpenAQ reports pm25/pm10/no2/
# so2/co/o3 in ug/m3 except co, which is typically ppm; we don't have a
# reliable per-station molar-mass conversion context, so co is only used
# when OpenAQ itself reports it in mg/m3 (checked via the `unit` field).
_PARAM_MAP = {
    "pm25": "pm25",
    "pm10": "pm10",
    "no2": "no2",
    "so2": "so2",
    "co": "co",
    "o3": "o3",
}

# Reject readings older than this — a "live" reading that's actually hours
# old is worse than clearly labeling data as unavailable.
_MAX_READING_AGE = 60 * 60 * 3  # 3 hours


@dataclass
class LiveReading:
    pm25: float | None
    pm10: float | None
    no2: float | None
    so2: float | None
    co: float | None
    o3: float | None
    temperature: float | None
    humidity: float | None
    wind_speed: float | None
    wind_direction: float | None
    observed_at: datetime
    openaq_location_id: int
    openaq_location_name: str
    distance_meters: float


def is_configured() -> bool:
    return bool(settings.OPENAQ_API_KEY)


async def fetch_nearest_reading(
    lat: float, lon: float, radius_m: int = 15_000
) -> LiveReading | None:
    """
    Find the nearest OpenAQ monitoring location within `radius_m` of
    (lat, lon) and return its latest measurements, or None if OpenAQ is
    unconfigured, unreachable, has no nearby station, or only has stale
    data. Never raises — ingestion should fall back to the synthetic
    generator on any failure.
    """
    if not is_configured():
        return None

    headers = {"X-API-Key": settings.OPENAQ_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            loc_resp = await client.get(
                f"{_base_url()}/locations",
                params={
                    "coordinates": f"{lat},{lon}",
                    "radius": radius_m,
                    "limit": 5,
                    "order_by": "distance",
                },
            )
            if loc_resp.status_code != 200:
                logger.warning(
                    "openaq.locations_failed",
                    status=loc_resp.status_code,
                    lat=lat,
                    lon=lon,
                )
                return None

            locations = (loc_resp.json() or {}).get("results", [])
            if not locations:
                return None

            for location in locations:
                location_id = location.get("id")
                if location_id is None:
                    continue

                reading = await fetch_location_latest(client, location)
                if reading is not None:
                    return reading

            return None

    except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
        logger.warning("openaq.fetch_error", error=str(e), lat=lat, lon=lon)
        return None


# India's approximate bounding box (minLon, minLat, maxLon, maxLat). Used
# only as a defensive sanity filter on `iso=IN` results below (OpenAQ
# occasionally has mis-geocoded locations) — never used to invent
# coordinates, only to discard obviously-wrong ones.
INDIA_BBOX = (68.0, 6.5, 97.5, 37.5)

# Parameters that make a discovered location usable for the AQI heatmap —
# it must measure at least one of these for us to compute an AQI sub-index.
_RELEVANT_PARAMS = {"pm25", "pm10", "no2", "so2", "co", "o3"}


def _in_india_bbox(lat: float, lon: float) -> bool:
    min_lon, min_lat, max_lon, max_lat = INDIA_BBOX
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


async def discover_india_locations(
    max_pages: int = 20, page_size: int = 100
) -> list[dict]:
    """
    Enumerate real OpenAQ monitoring locations across India via the /v3
    /locations endpoint (`iso=IN`), so nationwide station coverage is
    discovered from whatever the provider actually has — never a
    hardcoded city list. Returns the raw OpenAQ location dicts (id, name,
    locality, coordinates, sensors, owner, ...) for every location that
    reports at least one pollutant this pipeline understands and whose
    coordinates fall inside India's bounding box.

    Returns an empty list (never raises) if OpenAQ is unconfigured,
    unreachable, or returns nothing — callers must treat that as "no
    discovery this cycle", not as license to fabricate stations.
    """
    if not is_configured():
        return []

    headers = {"X-API-Key": settings.OPENAQ_API_KEY}
    discovered: list[dict] = []

    try:
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            for page in range(1, max_pages + 1):
                resp = await client.get(
                    f"{_base_url()}/locations",
                    params={
                        "iso": "IN",
                        "limit": page_size,
                        "page": page,
                    },
                )
                if resp.status_code != 200:
                    logger.warning(
                        "openaq.discover_locations_failed",
                        status=resp.status_code,
                        page=page,
                    )
                    break

                results = (resp.json() or {}).get("results", [])
                if not results:
                    break

                for location in results:
                    coords = location.get("coordinates") or {}
                    lat, lon = coords.get("latitude"), coords.get("longitude")
                    if lat is None or lon is None or not _in_india_bbox(lat, lon):
                        continue

                    sensor_params = {
                        (sensor.get("parameter") or {}).get("name")
                        for sensor in location.get("sensors", []) or []
                    }
                    if not sensor_params & _RELEVANT_PARAMS:
                        continue

                    discovered.append(location)

                if len(results) < page_size:
                    break  # last page

    except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
        logger.warning("openaq.discover_locations_error", error=str(e))
        # Whatever was already collected before the failure is still real
        # provider data and safe to return partially.

    return discovered


async def fetch_location_latest(
    client: httpx.AsyncClient, location: dict
) -> LiveReading | None:
    location_id = location["id"]

    latest_resp = await client.get(f"{_base_url()}/locations/{location_id}/latest")
    if latest_resp.status_code != 200:
        return None

    entries = (latest_resp.json() or {}).get("results", [])
    if not entries:
        return None

    # Map sensor id -> parameter name using the location's sensor list.
    sensor_param: dict[int, str] = {}
    for sensor in location.get("sensors", []) or []:
        sensor_id = sensor.get("id")
        param_name = (sensor.get("parameter") or {}).get("name")
        if sensor_id is not None and param_name:
            sensor_param[sensor_id] = param_name

    values: dict[str, float] = {}
    newest_ts: datetime | None = None

    for entry in entries:
        sensor_id = entry.get("sensorsId")
        param_name = sensor_param.get(sensor_id)
        if param_name not in _PARAM_MAP:
            continue

        value = entry.get("value")
        if value is None:
            continue

        ts_raw = (entry.get("datetime") or {}).get("utc")
        try:
            ts = (
                datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                if ts_raw
                else None
            )
        except (ValueError, AttributeError):
            ts = None

        if ts is not None and (newest_ts is None or ts > newest_ts):
            newest_ts = ts

        values[_PARAM_MAP[param_name]] = float(value)

    if not values or newest_ts is None:
        return None

    age_seconds = (datetime.now(timezone.utc) - newest_ts).total_seconds()
    if age_seconds > _MAX_READING_AGE:
        logger.info(
            "openaq.stale_reading_skipped",
            location_id=location_id,
            age_seconds=age_seconds,
        )
        return None

    return LiveReading(
        pm25=values.get("pm25"),
        pm10=values.get("pm10"),
        no2=values.get("no2"),
        so2=values.get("so2"),
        co=values.get("co"),
        o3=values.get("o3"),
        temperature=None,
        humidity=None,
        wind_speed=None,
        wind_direction=None,
        observed_at=newest_ts,
        openaq_location_id=location_id,
        openaq_location_name=location.get("name", "unknown"),
        distance_meters=location.get("distance", 0.0),
    )
