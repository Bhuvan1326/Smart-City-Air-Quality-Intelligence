from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from app.core.config import settings
from app.core.logging import logger


def _base_url() -> str:
    return settings.OPENAQ_BASE_URL or "https://api.openaq.org/v3"


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

# OpenAQ rate-limits aggressively (HTTP 429) once more than a handful of
# requests land in a short window — exactly what happens when Celery Beat
# fires `discover_and_ingest_india_locations` and
# `fetch_live_aqi_pune_stations` at (roughly) the same tick, each firing a
# burst of concurrent lookups. A single 429 used to be treated exactly
# like "no data" (return None), which then cascaded into every one of
# that cycle's stations coming back "unresolved_no_openaq_candidates" even
# though OpenAQ genuinely had the data — it just needed a moment. Retry
# with backoff before giving up.
_MAX_RETRIES = 4
_RETRY_BASE_DELAY = 0.75  # seconds


async def _get_with_retry(
    client: httpx.AsyncClient, url: str, *, params: dict | None = None
) -> httpx.Response | None:
    """GET with bounded retry/backoff on 429 (rate limited) and 5xx
    (transient provider errors). Returns the response (whatever its final
    status code) once retries are exhausted, or None if every attempt
    raised a transport-level error. Never raises."""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = await client.get(url, params=params)
        except (httpx.HTTPError, TimeoutError):
            resp = None
        else:
            if resp.status_code != 429 and resp.status_code < 500:
                return resp

        if attempt == _MAX_RETRIES:
            return resp  # final attempt: hand back whatever we have (may be None)

        # Respect Retry-After when OpenAQ sends one; otherwise exponential
        # backoff with jitter so a burst of concurrent workers doesn't
        # retry in lockstep and immediately re-trip the rate limit.
        retry_after = resp.headers.get("retry-after") if resp is not None else None
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = _RETRY_BASE_DELAY * (2**attempt)
        else:
            delay = _RETRY_BASE_DELAY * (2**attempt)
        delay += random.uniform(0, delay * 0.25)
        await asyncio.sleep(delay)

    return None  # unreachable, but keeps type checkers happy


def _server_now(resp: httpx.Response) -> datetime:
    """Reference "now" for freshness comparisons, taken from the
    responding server's own HTTP `Date` header rather than this
    machine's local clock.

    Comparing a provider timestamp against `datetime.now()` assumes the
    local clock is correct. In practice (and concretely observed running
    this stack under WSL2, whose clock is known to drift out of sync with
    the Windows host — see Microsoft/WSL issue tracker) that assumption
    doesn't hold, and a multi-hour local clock skew makes genuinely
    current OpenAQ observations look stale (or, in the other direction,
    would make stale data look current) purely as an artifact of the
    machine running the code, not the data's actual age. Anchoring "now"
    to the HTTP `Date` header of the very response that carried the
    observation keeps the comparison entirely within the provider's own
    clock, which is what "is this reading stale" should actually mean.
    Falls back to the local clock only if the header is absent/unparsable.
    """
    date_header = resp.headers.get("date")
    if date_header:
        try:
            parsed = parsedate_to_datetime(date_header)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc)


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


@dataclass
class CountryLocation:
    openaq_location_id: int
    name: str
    latitude: float
    longitude: float
    city: str | None
    state: str | None
    country_code: str | None
    sensor_parameters: list[str]


INDIA_COUNTRY_CODE = "IN"
_MAX_PAGE_LIMIT = 1000


def is_configured() -> bool:
    return bool(settings.OPENAQ_API_KEY)


async def search_locations_near(
    lat: float, lon: float, radius_m: int = 15_000, limit: int = 20
) -> list[dict] | None:
    """Raw OpenAQ `/locations` results near (lat, lon) — the candidate set
    for robust name/provider-based station matching (see
    app/services/aqi_providers/pune_stations.py), as distinct from
    `fetch_nearest_reading` which picks the single nearest station and is
    used only where "nearest" genuinely is the right matching strategy.

    Returns None (never raises) if OpenAQ is unconfigured, unreachable, or
    the request fails. Returns [] if the request succeeded but found
    nothing nearby.
    """
    if not is_configured():
        return None

    headers = {"X-API-Key": settings.OPENAQ_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            resp = await _get_with_retry(
                client,
                f"{_base_url()}/locations",
                params={
                    "coordinates": f"{lat},{lon}",
                    "radius": radius_m,
                    "limit": limit,
                },
            )
            if resp is None or resp.status_code != 200:
                logger.warning(
                    "openaq.search_locations_failed",
                    status=resp.status_code if resp is not None else None,
                    lat=lat,
                    lon=lon,
                )
                return None
            return (resp.json() or {}).get("results", [])
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
        logger.warning("openaq.search_locations_error", error=str(e), lat=lat, lon=lon)
        return None


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
            loc_resp = await _get_with_retry(
                client,
                f"{_base_url()}/locations",
                params={
                    "coordinates": f"{lat},{lon}",
                    "radius": radius_m,
                    "limit": 5,
                },
            )
            if loc_resp is None or loc_resp.status_code != 200:
                logger.warning(
                    "openaq.locations_failed",
                    status=loc_resp.status_code if loc_resp is not None else None,
                    lat=lat,
                    lon=lon,
                )
                return None

            locations = (loc_resp.json() or {}).get("results", [])
            if not locations:
                return None

            locations.sort(key=lambda loc: loc.get("distance") or float("inf"))

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
                resp = await _get_with_retry(
                    client,
                    f"{_base_url()}/locations",
                    params={
                        "iso": "IN",
                        "limit": page_size,
                        "page": page,
                    },
                )
                if resp is None or resp.status_code != 200:
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


async def fetch_country_locations(
    country_code: str = INDIA_COUNTRY_CODE,
    page: int = 1,
    limit: int = 100,
) -> list[CountryLocation] | None:
    """Discover OpenAQ monitoring locations across an entire country
    (India by default), paginated — the India-level counterpart to
    `fetch_nearest_reading`: "what stations exist across India at all?"
    rather than "what's nearest to this known point?". Pair with
    `fetch_location_reading` per discovered location.

    Returns None (never raises) if OpenAQ is unconfigured, unreachable, or
    the request otherwise fails. Returns an empty list (distinct from
    None) if the request succeeded but this page had no results.

    CAVEAT: like `fetch_nearest_reading`, this could not be exercised
    against the live OpenAQ service from this sandbox (no network
    egress) — smoke-test against a real API key before relying on it.
    """
    if not is_configured():
        return None

    if page < 1:
        raise ValueError("page must be >= 1")
    if not (1 <= limit <= _MAX_PAGE_LIMIT):
        raise ValueError(f"limit must be between 1 and {_MAX_PAGE_LIMIT}")

    headers = {"X-API-Key": settings.OPENAQ_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            resp = await _get_with_retry(
                client,
                f"{_base_url()}/locations",
                params={"iso": country_code, "limit": limit, "page": page},
            )
            if resp is None or resp.status_code != 200:
                logger.warning(
                    "openaq.country_locations_failed",
                    status=resp.status_code if resp is not None else None,
                    country_code=country_code,
                    page=page,
                )
                return None

            results = (resp.json() or {}).get("results", [])
            locations: list[CountryLocation] = []
            for loc in results:
                location_id = loc.get("id")
                coords = loc.get("coordinates") or {}
                lat = coords.get("latitude")
                lon = coords.get("longitude")
                if location_id is None or lat is None or lon is None:
                    continue  # can't place on a map — skip, don't fabricate

                country_field = loc.get("country") or {}
                sensor_params = [
                    (s.get("parameter") or {}).get("name")
                    for s in (loc.get("sensors") or [])
                    if (s.get("parameter") or {}).get("name")
                ]

                locations.append(
                    CountryLocation(
                        openaq_location_id=location_id,
                        name=loc.get("name", "unknown"),
                        latitude=float(lat),
                        longitude=float(lon),
                        city=loc.get("locality"),
                        # OpenAQ v3 does not reliably expose state/province
                        # on /locations — never guessed from locality/name.
                        state=None,
                        country_code=country_field.get("code"),
                        sensor_parameters=sensor_params,
                    )
                )

            return locations

    except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
        logger.warning(
            "openaq.country_locations_error",
            error=str(e),
            country_code=country_code,
            page=page,
        )
        return None


async def fetch_location_reading(
    location_id: int, location_name: str
) -> LiveReading | None:
    """Fetch the latest reading for a single already-known OpenAQ location
    (e.g. one returned by `fetch_country_locations`). Reuses the exact
    same parsing/staleness logic as `fetch_nearest_reading`
    (`_fetch_location_latest`) rather than duplicating it.
    """
    if not is_configured():
        return None

    headers = {"X-API-Key": settings.OPENAQ_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            loc_resp = await _get_with_retry(
                client, f"{_base_url()}/locations/{location_id}"
            )
            if loc_resp is None or loc_resp.status_code != 200:
                return None
            location = (loc_resp.json() or {}).get("results", [{}])[0]
            location.setdefault("id", location_id)
            location.setdefault("name", location_name)
            return await _fetch_location_latest(client, location)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as e:
        logger.warning(
            "openaq.location_reading_error", error=str(e), location_id=location_id
        )
        return None


async def fetch_location_latest(
    client: httpx.AsyncClient, location: dict
) -> LiveReading | None:
    location_id = location["id"]

    latest_resp = await _get_with_retry(
        client, f"{_base_url()}/locations/{location_id}/latest"
    )
    if latest_resp is None or latest_resp.status_code != 200:
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

    # Anchor "now" to the server's own HTTP Date header (see _server_now)
    # rather than this machine's local clock, so local clock drift can't
    # make a genuinely current OpenAQ observation look stale.
    reference_now = _server_now(latest_resp)
    age_seconds = (reference_now - newest_ts).total_seconds()
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


async def _fetch_location_latest(
    client: httpx.AsyncClient, location: dict
) -> LiveReading | None:
    """Compatibility alias for callers that use the private helper name."""
    return await fetch_location_latest(client, location)
