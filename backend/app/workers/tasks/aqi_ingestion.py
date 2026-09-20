import asyncio
import json
import random
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.logging import logger
from app.core.redis_client import get_redis
from app.services.aqi_providers import openaq, pune_stations

PUNE_STATIONS = [
    {
        "code": "PUNE_001",
        "name": "Karve Road CAAQMS",
        "ward": "W01",
        "lat": 18.5074,
        "lon": 73.8077,
    },
    {
        "code": "PUNE_002",
        "name": "Shivajinagar CAAQMS",
        "ward": "W02",
        "lat": 18.5308,
        "lon": 73.8475,
    },
    {
        "code": "PUNE_003",
        "name": "Hadapsar CAAQMS",
        "ward": "W03",
        "lat": 18.5089,
        "lon": 73.9259,
    },
    {
        "code": "PUNE_004",
        "name": "Pimpri CAAQMS",
        "ward": "W04",
        "lat": 18.6298,
        "lon": 73.7997,
    },
    {
        "code": "PUNE_005",
        "name": "Katraj CAAQMS",
        "ward": "W05",
        "lat": 18.4530,
        "lon": 73.8618,
    },
    {
        "code": "PUNE_006",
        "name": "Wakad CAAQMS",
        "ward": "W06",
        "lat": 18.5989,
        "lon": 73.7601,
    },
    {
        "code": "PUNE_007",
        "name": "Kothrud CAAQMS",
        "ward": "W07",
        "lat": 18.4968,
        "lon": 73.8126,
    },
    {
        "code": "PUNE_008",
        "name": "Yerawada CAAQMS",
        "ward": "W08",
        "lat": 18.5559,
        "lon": 73.9007,
    },
]

MUMBAI_STATIONS = [
    {
        "code": "MUM_001",
        "name": "Andheri CAAQMS",
        "ward": "K/W",
        "lat": 19.1136,
        "lon": 72.8697,
    },
    {
        "code": "MUM_002",
        "name": "Bandra CAAQMS",
        "ward": "H/W",
        "lat": 19.0596,
        "lon": 72.8295,
    },
    {
        "code": "MUM_003",
        "name": "Worli CAAQMS",
        "ward": "G/S",
        "lat": 19.0177,
        "lon": 72.8139,
    },
    {
        "code": "MUM_004",
        "name": "Chembur CAAQMS",
        "ward": "M/E",
        "lat": 19.0522,
        "lon": 72.8992,
    },
]

ALL_STATIONS = {
    "Pune": PUNE_STATIONS,
    "Mumbai": MUMBAI_STATIONS,
}

# GET /api/v1/aqi/live?city=Pune now bypasses this dict entirely and reads
# only the six real OpenAQ-matched stations (see get_live_aqi in
# app/api/v1/endpoints/aqi.py) — ALL_STATIONS["Pune"] remains here only so
# fetch_live_aqi_all_cities keeps refreshing the ward fixtures for the
# other, unrelated features listed above.


def _sub_index(
    value: float, breakpoints: list[tuple[float, float, int, int]]
) -> int | None:
    """Linear interpolation of a pollutant concentration to its AQI
    sub-index using CPCB-style breakpoint bands. Returns None if the value
    doesn't fall in a known band (caller decides how to handle that)."""
    for c_lo, c_hi, i_lo, i_hi in breakpoints:
        if c_lo <= value <= c_hi:
            return int(((i_hi - i_lo) / (c_hi - c_lo)) * (value - c_lo) + i_lo)
    if breakpoints and value > breakpoints[-1][1]:
        return breakpoints[-1][3]
    return None


# CPCB-style (Indian NAAQS) breakpoint bands per pollutant. PM2.5's table
# matches the one already used by this project; the others complete the
# same methodology for pollutants the pipeline already collects.
_PM25_BREAKPOINTS = [
    (0, 30, 0, 50),
    (30, 60, 51, 100),
    (60, 90, 101, 200),
    (90, 120, 201, 300),
    (120, 250, 301, 400),
    (250, 500, 401, 500),
]
_PM10_BREAKPOINTS = [
    (0, 50, 0, 50),
    (50, 100, 51, 100),
    (100, 250, 101, 200),
    (250, 350, 201, 300),
    (350, 430, 301, 400),
    (430, 510, 401, 500),
]
_NO2_BREAKPOINTS = [
    (0, 40, 0, 50),
    (40, 80, 51, 100),
    (80, 180, 101, 200),
    (180, 280, 201, 300),
    (280, 400, 301, 400),
    (400, 500, 401, 500),
]
_SO2_BREAKPOINTS = [
    (0, 40, 0, 50),
    (40, 80, 51, 100),
    (80, 380, 101, 200),
    (380, 800, 201, 300),
    (800, 1600, 301, 400),
    (1600, 2100, 401, 500),
]
_CO_BREAKPOINTS = [  # mg/m^3
    (0, 1, 0, 50),
    (1, 2, 51, 100),
    (2, 10, 101, 200),
    (10, 17, 201, 300),
    (17, 34, 301, 400),
    (34, 50, 401, 500),
]
_O3_BREAKPOINTS = [
    (0, 50, 0, 50),
    (50, 100, 51, 100),
    (100, 168, 101, 200),
    (168, 208, 201, 300),
    (208, 748, 301, 400),
    (748, 1000, 401, 500),
]


def _calculate_aqi_from_pm25(pm25: float) -> int:
    """AQI from PM2.5 alone using Indian NAAQS breakpoints. Kept for
    callers/tests that only have a PM2.5 reading; prefer
    `calculate_overall_aqi` when other pollutants are available (BUG 017 —
    the true AQI is the max sub-index across all monitored pollutants,
    not PM2.5 alone)."""
    return _sub_index(pm25, _PM25_BREAKPOINTS) or 500


def calculate_overall_aqi(
    *,
    pm25: float | None = None,
    pm10: float | None = None,
    no2: float | None = None,
    so2: float | None = None,
    co: float | None = None,
    o3: float | None = None,
) -> int:
    """Overall AQI = the maximum sub-index across every pollutant that was
    actually measured, per the CPCB Indian National AQI methodology this
    project already follows for PM2.5 — using only PM2.5 while ignoring
    PM10/NO2/SO2/CO/O3 readings that were collected right alongside it
    understates the AQI whenever another pollutant is the worse offender.
    """
    candidates = [
        _sub_index(pm25, _PM25_BREAKPOINTS) if pm25 is not None else None,
        _sub_index(pm10, _PM10_BREAKPOINTS) if pm10 is not None else None,
        _sub_index(no2, _NO2_BREAKPOINTS) if no2 is not None else None,
        _sub_index(so2, _SO2_BREAKPOINTS) if so2 is not None else None,
        _sub_index(co, _CO_BREAKPOINTS) if co is not None else None,
        _sub_index(o3, _O3_BREAKPOINTS) if o3 is not None else None,
    ]
    valid = [c for c in candidates if c is not None]
    if not valid:
        return 500
    return max(valid)


def _generate_realistic_reading(station: dict, hour: int) -> dict:
    """Statistical AQI generator with diurnal patterns and ward-specific
    baselines.

    NOT part of the Live AQI production path (see requirement 4/20 —
    synthetic data must never enter Live AQI, dashboards, heatmap,
    alerts, etc.). Kept only for the unit tests that exercise this
    function directly, as a documented, isolated dev/test simulator
    (classification C, see requirement 20) — nothing in the production
    ingestion path calls it any more. `_build_reading_for_station` /
    `_fetch_aqi_async` below no longer call this: when OpenAQ has no live
    reading for a ward fixture, no reading is written at all rather than
    a fabricated one.
    """
    # Morning and evening traffic peaks
    traffic_factor = 1.0
    if 7 <= hour <= 10 or 17 <= hour <= 20:
        traffic_factor = 1.6
    elif 0 <= hour <= 5:
        traffic_factor = 0.6

    # Industrial wards have higher baseline (Pimpri, Hadapsar)
    baseline_pm25 = 45.0
    if station["ward"] in ("W04", "W03"):
        baseline_pm25 = 75.0

    pm25 = baseline_pm25 * traffic_factor * random.uniform(0.8, 1.2)
    pm10 = pm25 * random.uniform(1.5, 2.2)
    no2 = 30 + traffic_factor * 20 * random.uniform(0.7, 1.3)
    so2 = 8 + random.uniform(0, 12)
    co = 0.8 + traffic_factor * 0.6 * random.uniform(0.8, 1.2)
    o3 = max(0, 40 - traffic_factor * 10 + random.uniform(-10, 10))

    return {
        "pm25": round(pm25, 2),
        "pm10": round(pm10, 2),
        "no2": round(no2, 2),
        "so2": round(so2, 2),
        "co": round(co, 2),
        "o3": round(o3, 2),
        "aqi": calculate_overall_aqi(
            pm25=pm25, pm10=pm10, no2=no2, so2=so2, co=co, o3=o3
        ),
        "temperature": round(22 + random.uniform(-5, 10), 1),
        "humidity": round(55 + random.uniform(-20, 25), 1),
        "wind_speed": round(random.uniform(0.5, 8.0), 1),
        "wind_direction": round(random.uniform(0, 360), 1),
    }


async def _ensure_stations_exist(
    session, city: str, stations: list[dict]
) -> dict[str, str]:
    """Ensure monitoring stations exist in DB, return code->id mapping."""
    from geoalchemy2.elements import WKTElement

    from app.models.monitoring import MonitoringStation

    code_to_id = {}
    for s in stations:
        result = await session.execute(
            select(MonitoringStation.id, MonitoringStation.station_code).where(
                MonitoringStation.station_code == s["code"]
            )
        )
        row = result.one_or_none()
        if row:
            code_to_id[s["code"]] = row.id
        else:
            geom = WKTElement(f"POINT({s['lon']} {s['lat']})", srid=4326)
            station = MonitoringStation(
                name=s["name"],
                station_code=s["code"],
                city=city,
                ward_id=s["ward"],
                operator="MPCB / CPCB",
                latitude=s["lat"],
                longitude=s["lon"],
                geometry=geom,
                is_active=True,
                station_type="CAAQMS",
            )
            session.add(station)
            await session.flush()
            code_to_id[s["code"]] = station.id

    await session.commit()
    return code_to_id


def fetch_live_aqi_all_cities():
    """Pull live AQI data for all configured cities and persist to DB.

    Invoked directly (no Celery) by the "fetch-live-aqi" job in
    app/workers/scheduler.py — this project's in-process asyncio
    scheduler, which is what actually drives every scheduled/background
    job in the existing Render Web Service. There is no separate worker
    process.
    """
    asyncio.run(_fetch_aqi_async())


async def _build_reading_for_station(
    s: dict, hour: int
) -> tuple[dict, str, str] | None:
    """
    Returns (data, quality_flag, raw_data_json) for one station, or None if
    no real OpenAQ observation is available for it right now.

    Tries OpenAQ (real ground-station data) only. This function used to
    fall back to a statistical generator when OpenAQ had nothing — that
    fallback has been removed from the production ingestion path (see
    requirement 4: Live AQI must never contain synthetic/fabricated
    data). `_generate_realistic_reading` still exists for tests/dev use
    but is no longer called here. `hour` is accepted for backward
    compatibility with existing callers/tests but is unused now that
    there's no diurnal synthetic model to feed it into.
    """
    del hour  # unused now that the synthetic fallback is gone
    if not openaq.is_configured():
        return None

    live = await openaq.fetch_nearest_reading(s["lat"], s["lon"])
    if live is None or live.pm25 is None:
        return None

    pm25 = live.pm25
    data = {
        "pm25": pm25,
        "pm10": live.pm10,
        "no2": live.no2,
        "so2": live.so2,
        "co": live.co,
        "o3": live.o3,
        "aqi": calculate_overall_aqi(
            pm25=pm25,
            pm10=live.pm10,
            no2=live.no2,
            so2=live.so2,
            co=live.co,
            o3=live.o3,
        ),
        "temperature": live.temperature,
        "humidity": live.humidity,
        "wind_speed": live.wind_speed,
        "wind_direction": live.wind_direction,
    }
    raw = json.dumps(
        {
            "source": "openaq",
            "openaq_location_id": live.openaq_location_id,
            "openaq_location_name": live.openaq_location_name,
            "distance_meters": live.distance_meters,
            "observed_at": live.observed_at.isoformat(),
        }
    )
    return data, "good", raw


async def _fetch_aqi_async():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.monitoring import AQIReading, MonitoringStation

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

    now = datetime.now(UTC)
    hour = now.hour

    async with AsyncSession() as session:
        for city, stations in ALL_STATIONS.items():
            code_to_id = await _ensure_stations_exist(session, city, stations)
            readings = []
            skipped = 0
            for s in stations:
                station_id = code_to_id[s["code"]]
                built = await _build_reading_for_station(s, hour)
                if built is None:
                    # No real OpenAQ observation for this ward fixture right
                    # now — skip it entirely rather than fabricate one. The
                    # station's last_data_at simply stays where it was, so
                    # any consumer checking freshness sees it go stale.
                    skipped += 1
                    continue
                data, quality_flag, raw = built

                reading = AQIReading(
                    station_id=station_id,
                    **data,
                    timestamp=now,
                    latitude=s["lat"],
                    longitude=s["lon"],
                    quality_flag=quality_flag,
                    raw_data=raw,
                )
                readings.append(reading)

            session.add_all(readings)

            station_ids = [r.station_id for r in readings]
            if station_ids:
                await session.execute(
                    update(MonitoringStation)
                    .where(MonitoringStation.id.in_(station_ids))
                    .values(last_data_at=now)
                )

            await session.commit()
            logger.info(
                "aqi_ingestion.complete",
                city=city,
                count=len(readings),
                live_from_openaq=len(readings),
                skipped_no_live_data=skipped,
            )

    await engine.dispose()


# ═══════════════════════════════════════════════════════════════════════
# Real-time Pune Live AQI: the six authoritative stations, OpenAQ-only,
# every 60 seconds, zero synthetic fallback. See app/services/
# aqi_providers/pune_stations.py for the station registry and matching
# logic. Completely separate station rows (station_code "PUNE_LIVE_*")
# from the ward fixtures above — never conflated.
# ═══════════════════════════════════════════════════════════════════════

PUNE_LIVE_LOCK_KEY = "lock:aqi_ingestion:fetch_live_aqi_pune_stations"
PUNE_LIVE_LOCK_TTL = 55  # seconds — just under the 60s beat interval


async def _get_pune_station_by_code(session, station_code: str):
    from app.models.monitoring import MonitoringStation

    result = await session.execute(
        select(MonitoringStation).where(
            MonitoringStation.station_code == station_code,
            MonitoringStation.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def _ensure_pune_station_row(
    session, spec, matched_location: dict, existing_station=None
):
    from geoalchemy2.elements import WKTElement

    from app.models.monitoring import MonitoringStation
    from app.services import civic_ward_assignment

    coords = matched_location.get("coordinates") or {}
    lat, lon = coords.get("latitude"), coords.get("longitude")
    location_id = matched_location.get("id")
    if lat is None or lon is None or location_id is None:
        # Can't place this on a map or poll it — treat as unresolved
        # rather than persist a half-real row.
        return None

    station = existing_station
    owner_name = (
        (matched_location.get("owner") or {}).get("name")
        or (matched_location.get("provider") or {}).get("name")
        or spec.provider
    )
    openaq_name = (matched_location.get("name") or spec.display_name).strip()

    # Resolve the real ward from the station's authoritative OpenAQ
    # coordinates — never trust the approximate search-seed ward. Only
    # queried when we don't already have one, so a re-resolution that
    # keeps hitting UNAVAILABLE doesn't spam ward_boundaries lookups.
    # `station.ward_id` is only consulted when the station object
    # actually carries that column (real MonitoringStation rows always
    # do); callers that pass a stripped-down stand-in without a
    # ward_id field are signalling ward assignment isn't part of that
    # flow, so we leave it alone rather than guessing.
    if station is None:
        ward_id = None
        needs_ward_lookup = True
    elif hasattr(station, "ward_id"):
        ward_id = station.ward_id
        needs_ward_lookup = ward_id is None
    else:
        ward_id = None
        needs_ward_lookup = False

    if needs_ward_lookup:
        ward_result = await civic_ward_assignment.assign_ward(
            session, city=spec.city, latitude=float(lat), longitude=float(lon)
        )
        ward_id = ward_result.ward_id

    if station is None:
        geom = WKTElement(f"POINT({lon} {lat})", srid=4326)
        station = MonitoringStation(
            id=uuid.uuid4(),
            name=spec.display_name,
            station_code=spec.station_code,
            city=spec.city,
            state=spec.state,
            country=spec.country,
            ward_id=ward_id,
            operator=f"{owner_name} (via OpenAQ)",
            latitude=float(lat),
            longitude=float(lon),
            geometry=geom,
            is_active=True,
            station_type="OpenAQ",
            data_source_url=f"https://explore.openaq.org/locations/{location_id}",
            openaq_location_id=location_id,
        )
        session.add(station)
    else:
        # Re-resolution (e.g. after an OpenAQ location id changed) —
        # refresh the provider-sourced fields in place, never touch the
        # stable local identity (id/station_code).
        station.latitude = float(lat)
        station.longitude = float(lon)
        station.geometry = WKTElement(f"POINT({lon} {lat})", srid=4326)
        station.openaq_location_id = location_id
        station.operator = f"{owner_name} (via OpenAQ)"
        station.data_source_url = f"https://explore.openaq.org/locations/{location_id}"
        station.is_active = True
        if hasattr(station, "ward_id") and station.ward_id is None:
            station.ward_id = ward_id

    logger.info(
        "aqi_ingestion.pune_station_resolved",
        station_code=spec.station_code,
        openaq_location_id=location_id,
        openaq_name=openaq_name,
    )
    return station


async def _acquire_pune_live_lock() -> bool:
    """Best-effort Redis lock so an overlapping/slow-running task
    invocation can't race the next scheduled tick into double-ingesting.
    Returns True if the lock was acquired (caller must release it),
    False if another run currently holds it (caller should skip this
    run entirely rather than partially ingest).
    """
    try:
        client = await get_redis()
        acquired = await client.set(
            PUNE_LIVE_LOCK_KEY, "1", nx=True, ex=PUNE_LIVE_LOCK_TTL
        )
        return bool(acquired)
    except Exception as e:
        logger.warning("aqi_ingestion.pune_live_lock_error", error=str(e))
        return True  # fail open — a missed lock is safer than a stuck pipeline


async def _release_pune_live_lock() -> None:
    try:
        client = await get_redis()
        await client.delete(PUNE_LIVE_LOCK_KEY)
    except Exception as e:
        logger.warning("aqi_ingestion.pune_live_unlock_error", error=str(e))


def fetch_live_aqi_pune_stations():
    return asyncio.run(_fetch_pune_live_stations_async())


async def _fetch_pune_live_stations_async() -> dict:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    summary: dict[str, str] = {}

    if not openaq.is_configured():
        logger.info("aqi_ingestion.pune_live_skipped", reason="openaq_unconfigured")
        return {
            spec.station_code: "openaq_not_configured"
            for spec in pune_stations.REQUIRED_STATIONS
        }

    got_lock = await _acquire_pune_live_lock()
    if not got_lock:
        logger.info("aqi_ingestion.pune_live_skipped", reason="already_running")
        return {"_skipped": "already_running"}

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with AsyncSession() as session:
            for spec in pune_stations.REQUIRED_STATIONS:
                # Each station gets its own commit/rollback boundary
                # (rather than one shared transaction committed once at
                # the end). This was found during production-readiness
                # review to matter for real correctness, not just style:
                # a later station's IntegrityError (e.g. a duplicate
                # OpenAQ location id) requires a session-level
                # `rollback()` to fully recover in this SQLAlchemy/
                # asyncpg combination — a bare SAVEPOINT
                # (`session.begin_nested()`) turned out not to be
                # sufficient on its own. If every station shared one
                # uncommitted transaction, that `rollback()` would
                # silently discard every earlier station's
                # already-flushed-but-uncommitted work too — turning one
                # bad match into six lost readings. Committing per
                # station makes each one's blast radius strictly its own.
                try:
                    status = await _ingest_one_pune_station(session, spec)
                    await session.commit()
                except Exception as e:
                    await session.rollback()
                    logger.error(
                        "aqi_ingestion.pune_station_error",
                        station_code=spec.station_code,
                        error=str(e),
                    )
                    status = "error"
                summary[spec.station_code] = status
    finally:
        await engine.dispose()
        await _release_pune_live_lock()

    logger.info("aqi_ingestion.pune_live_complete", **summary)
    return summary


async def _try_reresolve_pune_station(session, spec, station):
    """Attempt to move a station whose currently cached OpenAQ location
    has been failing to produce a current observation for longer than
    `settings.PUNE_LIVE_RERESOLUTION_STALE_HOURS` to a DIFFERENT,
    currently-reporting OpenAQ location for the same physical station.

    This is the fix for the actual root cause of stations getting stuck
    on dead data: `_ingest_one_pune_station` previously resolved a
    station's OpenAQ location exactly ONCE (caching it forever on
    `station.openaq_location_id`) and never reconsidered that choice, so
    a station whose matched OpenAQ location later went
    inactive/decommissioned would poll that same dead location forever,
    correctly (per the freshness policy) but permanently rejecting every
    reading as `no_current_observation` — with no path back to a working
    location. This never fires for a station's first-ever resolution
    (only once `openaq_location_stale_since` has been set and the
    cooldown has elapsed — see the caller) and never selects a candidate
    by proximity alone: it reuses the exact same conservative
    `pune_stations.match_station` matching as initial resolution, just
    with the known-stuck location excluded from the candidate pool.

    Returns `(station, outcome)`. `outcome` is None if the caller should
    proceed to fetch a reading as normal (using the possibly-updated
    `station.openaq_location_id`); otherwise it's a terminal outcome
    string the caller should return immediately.
    """
    stuck_location_id = station.openaq_location_id

    candidates = await openaq.search_locations_near(
        spec.approx_lat,
        spec.approx_lon,
        radius_m=pune_stations.SEARCH_RADIUS_M,
        limit=100,
    )
    rematch = None
    if candidates:
        rematch = pune_stations.match_station(
            candidates, spec, exclude_location_ids={stuck_location_id}
        )

    if rematch is None or rematch.get("id") == stuck_location_id:
        # Nothing better available on this attempt — keep polling the
        # existing location (never fabricate, never guess), but restart
        # the cooldown clock so this comparatively expensive search
        # endpoint isn't re-hit on every single 60s tick while stuck;
        # the next attempt waits another full
        # PUNE_LIVE_RERESOLUTION_STALE_HOURS window.
        station.openaq_location_stale_since = datetime.now(UTC)
        return station, None

    logger.info(
        "aqi_ingestion.pune_station_reresolved",
        station_code=spec.station_code,
        old_openaq_location_id=stuck_location_id,
        new_openaq_location_id=rematch.get("id"),
    )
    updated = await _ensure_pune_station_row(
        session, spec, rematch, existing_station=station
    )
    if updated is None:
        return station, "unresolved_invalid_location_data"

    updated.openaq_location_stale_since = None
    try:
        await session.flush()
    except IntegrityError:
        # Same reasoning as the initial-resolution conflict handling
        # above: a full rollback (not just a SAVEPOINT) is required to
        # leave the session usable, and it only discards this station's
        # own not-yet-committed work since each station commits
        # independently (see _fetch_pune_live_stations_async).
        await session.rollback()
        logger.error(
            "aqi_ingestion.pune_station_reresolution_conflict",
            station_code=spec.station_code,
            openaq_location_id=rematch.get("id"),
        )
        return updated, "unresolved_location_id_conflict"

    return updated, None


async def _ingest_one_pune_station(session, spec) -> str:
    from app.models.monitoring import AQIReading, MonitoringStation

    station = await _get_pune_station_by_code(session, spec.station_code)

    # Step 1: resolve station -> OpenAQ location, only if not already
    # cached on the row. This is the only part of the loop that ever
    # calls the (comparatively expensive) location-search endpoint.
    if station is None or station.openaq_location_id is None:
        candidates = await openaq.search_locations_near(
            spec.approx_lat,
            spec.approx_lon,
            radius_m=pune_stations.SEARCH_RADIUS_M,
            limit=100,
        )
        if not candidates:
            return "unresolved_no_openaq_candidates"

        matched = pune_stations.match_station(candidates, spec)
        if matched is None:
            return "unresolved_no_confident_match"

        station = await _ensure_pune_station_row(
            session, spec, matched, existing_station=station
        )
        if station is None:
            return "unresolved_invalid_location_data"
        # Make the new/updated row's id visible for the reading insert
        # below without waiting for the caller's end-of-station commit.
        #
        # If this violates the openaq_location_id uniqueness constraint
        # from migration 020_pune_live_stations (e.g. two required
        # stations' searches both matched the same OpenAQ location), we
        # must fully `session.rollback()` — not just recover a SAVEPOINT
        # — to leave the session usable again; verified directly against
        # real Postgres/asyncpg while investigating this exact scenario
        # (a bare `session.begin_nested()` around the flush was NOT
        # sufficient to reset the session here). Because the caller
        # (_fetch_pune_live_stations_async) now commits/rolls back once
        # per station rather than batching all six into one shared
        # transaction, this rollback's blast radius is only this
        # station's own not-yet-committed work — it cannot discard an
        # earlier station's already-committed reading. See
        # test_aqi_pune_live.py::
        # test_duplicate_openaq_location_conflict_does_not_poison_other_stations.
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            logger.error(
                "aqi_ingestion.pune_station_resolution_conflict",
                station_code=spec.station_code,
                openaq_location_id=matched.get("id"),
            )
            return "unresolved_location_id_conflict"

    # Step 1b: if this station's cached OpenAQ location has been failing
    # to produce a current observation for longer than the configured
    # re-resolution cooldown, try a DIFFERENT OpenAQ location before
    # polling the same (likely dead/decommissioned) one yet again. Never
    # runs on a station's first-ever resolution above (freshly
    # created/updated rows have `openaq_location_stale_since` reset to
    # None), and `getattr` tolerates test doubles that don't set the
    # attribute at all.
    stale_since = getattr(station, "openaq_location_stale_since", None)
    if stale_since is not None:
        if stale_since.tzinfo is None:
            stale_since = stale_since.replace(tzinfo=UTC)
        cooldown = timedelta(hours=settings.PUNE_LIVE_RERESOLUTION_STALE_HOURS)
        if datetime.now(UTC) - stale_since >= cooldown:
            station, reresolution_outcome = await _try_reresolve_pune_station(
                session, spec, station
            )
            if reresolution_outcome is not None:
                return reresolution_outcome

    # Step 2: fetch the latest real measurement for the resolved location
    # (possibly just updated by re-resolution above). OpenAQ returns the
    # newest observation currently available; even when it is old, it is a
    # genuine provider observation and must be preserved with STALE quality.
    live = await openaq.fetch_location_reading(station.openaq_location_id, station.name)
    if live is None or all(
        v is None for v in (live.pm25, live.pm10, live.no2, live.so2, live.co, live.o3)
    ):
        # OpenAQ returned no usable observation at all. Do not fabricate a
        # reading. This is the only path that records the location as unable
        # to provide an observation and allows the existing re-resolution
        # mechanism to search for another valid station after its cooldown.
        if getattr(station, "openaq_location_stale_since", None) is None:
            station.openaq_location_stale_since = datetime.now(UTC)
        return "no_current_observation"

    # An observation exists. A stale observation is still real provider data
    # and is intentionally stored; only its quality flag changes. Because
    # OpenAQ is responding with a real observation, clear the unresolved
    # location marker.
    if getattr(station, "openaq_location_stale_since", None) is not None:
        station.openaq_location_stale_since = None

    # Step 3: idempotent insert — only if this is a genuinely new
    # provider observation for this station.
    # Exclude synthetic/demo rows from the "is this a new observation"
    # comparison (mirrors the same exclusion already used by
    # `_ingest_india_station_batch_async` below). Without this, a
    # demo/seed AQIReading stamped with the seeding wall-clock time (e.g.
    # `quality_flag="synthetic"`, `timestamp=now()` at seed time) would
    # permanently outrank every genuine OpenAQ observation — which is
    # frequently minutes/hours/days old by the time it's fetched — so a
    # real, valid, newly-fetched OpenAQ reading would never be judged
    # "newer" than that leftover synthetic row and would never be
    # persisted, even though OpenAQ keeps returning perfectly good data
    # (this was the root cause of `readings_ingested` staying stuck at 0
    # while `openaq.observation_accepted` kept firing).
    latest = await session.execute(
        select(AQIReading.timestamp)
        .where(
            AQIReading.station_id == station.id,
            AQIReading.is_deleted.is_(False),
            AQIReading.quality_flag != "synthetic",
        )
        .order_by(AQIReading.timestamp.desc())
        .limit(1)
    )
    latest_ts = latest.scalar_one_or_none()

    is_new_observation = latest_ts is None or live.observed_at > latest_ts

    if is_new_observation:
        reading = AQIReading(
            station_id=station.id,
            pm25=live.pm25,
            pm10=live.pm10,
            no2=live.no2,
            so2=live.so2,
            co=live.co,
            o3=live.o3,
            aqi=calculate_overall_aqi(
                pm25=live.pm25,
                pm10=live.pm10,
                no2=live.no2,
                so2=live.so2,
                co=live.co,
                o3=live.o3,
            ),
            temperature=live.temperature,
            humidity=live.humidity,
            wind_speed=live.wind_speed,
            wind_direction=live.wind_direction,
            # The provider's own observation timestamp — never local
            # ingestion time (requirement 3/9).
            timestamp=live.observed_at,
            latitude=station.latitude,
            longitude=station.longitude,
            quality_flag="stale" if getattr(live, "is_stale", False) else "good",
            raw_data=json.dumps(
                {
                    "source": "openaq",
                    "openaq_location_id": live.openaq_location_id,
                    "openaq_location_name": live.openaq_location_name,
                    "observed_at": live.observed_at.isoformat(),
                    "age_seconds": getattr(live, "age_seconds", 0.0),
                    "freshness": (
                        "stale" if getattr(live, "is_stale", False) else "current"
                    ),
                }
            ),
        )
        session.add(reading)
        try:
            await session.flush()
        except IntegrityError:
            # Race with another concurrent run (or the 60s beat
            # overlapping a slow-running previous tick) that inserted
            # the exact same (station_id, timestamp) first — the unique
            # index from migration 020_pune_live_stations caught it. Not
            # an error condition — someone else already recorded this
            # exact observation. `session.rollback()` (not just a
            # SAVEPOINT — see the station-resolution step above for why)
            # is safe here: this station's transaction hasn't committed
            # anything else yet, so nothing besides this failed insert
            # attempt is discarded.
            await session.rollback()
            outcome = "duplicate_observation_skipped"
        else:
            outcome = "inserted"
    else:
        outcome = "no_new_observation"

    logger.info(
        "aqi_ingestion.pune_station_observation",
        station_code=spec.station_code,
        openaq_location_id=live.openaq_location_id,
        observed_at=live.observed_at.isoformat(),
        age_seconds=round(getattr(live, "age_seconds", 0.0), 1),
        freshness="stale" if getattr(live, "is_stale", False) else "current",
        quality_flag="stale" if getattr(live, "is_stale", False) else "good",
        outcome=outcome,
    )

    await session.execute(
        update(MonitoringStation)
        .where(MonitoringStation.id == station.id)
        .values(last_data_at=live.observed_at)
    )
    return outcome


def _station_code_for_openaq_location(location_id: int) -> str:
    """Deterministic station_code assigned to a *newly created* discovered
    OpenAQ location. Only ever used at creation time — lookups for an
    existing row must go through `openaq_location_id`
    (see `_ensure_discovered_station`), never reconstruct this code and
    search for it, or a curated PUNE_LIVE_* row (which owns the same
    openaq_location_id under a different station_code) gets a duplicate
    row attempted for it."""
    return f"OPENAQ_IN_{location_id}"


def _city_for_location(location) -> str | None:
    locality = (location.city or "").strip()
    if locality:
        return locality
    name = (location.name or "").strip()
    if name:
        return name
    return f"OpenAQ {location.openaq_location_id}"


# station_codes that must never be overwritten by generic India-wide
# OpenAQ discovery — these six rows are curated/managed exclusively by
# `_ensure_pune_station_row`. Discovery can still discover the *same*
# openaq_location_id (OpenAQ has no way to know it's "already ours"); when
# that happens the existing row must be reused as-is, never duplicated and
# never repainted with generic discovery metadata.
_CURATED_OPENAQ_STATION_CODES = frozenset(
    spec.station_code for spec in pune_stations.REQUIRED_STATIONS
)

_MAX_STATION_NAME_LENGTH = 255
_MAX_CITY_LENGTH = 100
_MAX_STATE_LENGTH = 100


def _normalize_discovered_location(location) -> dict | None:
    """Validate and normalize one OpenAQ-discovered location into the
    shape a MonitoringStation row needs. Returns None (never raises) for
    a location that can't be turned into a valid row — id/coordinates
    missing or out of range — so the caller skips just that one location
    instead of aborting the page. Never fabricates a value: a field that
    isn't reliably known (state) stays None."""
    try:
        location_id = int(location.openaq_location_id)
    except (TypeError, ValueError):
        return None
    if location_id <= 0:
        return None

    try:
        lat = float(location.latitude)
        lon = float(location.longitude)
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None

    name = (location.name or f"OpenAQ Station {location_id}").strip()
    if not name:
        name = f"OpenAQ Station {location_id}"
    name = name[:_MAX_STATION_NAME_LENGTH]

    city = (_city_for_location(location) or f"OpenAQ {location_id}").strip()
    city = city[:_MAX_CITY_LENGTH] or f"OpenAQ {location_id}"

    state = location.state
    state = state.strip()[:_MAX_STATE_LENGTH] if isinstance(state, str) else None
    state = state or None

    return {
        "openaq_location_id": location_id,
        "name": name,
        "city": city,
        "state": state,
        "latitude": lat,
        "longitude": lon,
    }


async def _ensure_discovered_station(session, location) -> tuple[object | None, str]:
    """Idempotently upsert a MonitoringStation row for one India-wide
    OpenAQ-discovered location.

    `openaq_location_id` is the canonical identity used to find an
    existing row — never a reconstructed `station_code` — because the six
    curated PUNE_LIVE_* rows already own their OpenAQ location ids, and
    the exact same ids come back from the India-wide `iso=IN` sweep.
    Looking an existing row up by `OPENAQ_IN_{id}` (a code those curated
    rows never have) used to make discovery attempt a second INSERT for
    an id already covered by the DB's unique constraint on
    `openaq_location_id`, raising an IntegrityError that (without the
    caller's per-location savepoint) aborted every other station on that
    page along with it.

    Returns (station_id, outcome): outcome is "invalid" (station_id is
    None — the location failed validation), "curated_preserved" (an
    existing curated Pune row was reused untouched), "updated" (an
    existing generic discovery row's metadata was refreshed), or
    "created". Raises only for a genuine database error, so the caller's
    per-location SAVEPOINT can isolate and skip it.
    """
    from geoalchemy2.elements import WKTElement

    from app.models.monitoring import MonitoringStation

    normalized = _normalize_discovered_location(location)
    if normalized is None:
        return None, "invalid"

    result = await session.execute(
        select(MonitoringStation.id, MonitoringStation.station_code).where(
            MonitoringStation.openaq_location_id == normalized["openaq_location_id"]
        )
    )
    row = result.one_or_none()

    if row is not None:
        station_id, station_code = row
        if station_code in _CURATED_OPENAQ_STATION_CODES:
            # Never replace curated Pune configuration with generic
            # discovery data — this row is already fully managed by
            # `_ensure_pune_station_row`.
            return station_id, "curated_preserved"

        geom = WKTElement(
            f"POINT({normalized['longitude']} {normalized['latitude']})", srid=4326
        )
        await session.execute(
            update(MonitoringStation)
            .where(MonitoringStation.id == station_id)
            .values(
                name=normalized["name"],
                city=normalized["city"],
                state=normalized["state"],
                country="India",
                latitude=normalized["latitude"],
                longitude=normalized["longitude"],
                geometry=geom,
                data_source_url=(
                    "https://explore.openaq.org/locations/"
                    f"{normalized['openaq_location_id']}"
                ),
                openaq_location_id=normalized["openaq_location_id"],
                is_active=True,
            )
        )
        return station_id, "updated"

    code = _station_code_for_openaq_location(normalized["openaq_location_id"])
    geom = WKTElement(
        f"POINT({normalized['longitude']} {normalized['latitude']})", srid=4326
    )
    station = MonitoringStation(
        id=uuid.uuid4(),
        name=normalized["name"],
        station_code=code,
        city=normalized["city"],
        ward_id=None,
        operator="OpenAQ (CPCB / state boards)",
        country="India",
        state=normalized["state"],
        latitude=normalized["latitude"],
        longitude=normalized["longitude"],
        geometry=geom,
        is_active=True,
        station_type="OpenAQ",
        openaq_location_id=normalized["openaq_location_id"],
        data_source_url=(
            "https://explore.openaq.org/locations/"
            f"{normalized['openaq_location_id']}"
        ),
    )
    session.add(station)
    # Flush (not just add) so a real constraint/data violation for this
    # specific location raises here, inside the caller's per-location
    # SAVEPOINT, rather than surfacing later at the page-level commit
    # where it would roll back every other station from this page too.
    await session.flush()
    return station.id, "created"


def discover_and_ingest_india_locations():
    return asyncio.run(_discover_india_locations_async())


_INDIA_DISCOVERY_PAGE_RETRY_ATTEMPTS = 2
_INDIA_DISCOVERY_PAGE_RETRY_DELAY_SECONDS = 2.0


async def _discover_india_locations_async(
    max_pages: int | None = None,
    page_size: int | None = None,
) -> dict:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    summary = {
        "configured": openaq.is_configured(),
        "pages_processed": 0,
        "locations_discovered": 0,
        "stations_created": 0,
        "stations_updated": 0,
        "stations_existing": 0,
        "stations_skipped": 0,
        "errors": 0,
        "complete": False,
        "capped": False,
    }

    if not openaq.is_configured():
        logger.info(
            "aqi_ingestion.india_discovery_skipped", reason="openaq_unconfigured"
        )
        return summary

    max_pages = max_pages or settings.OPENAQ_INDIA_DISCOVERY_MAX_PAGES
    page_size = page_size or settings.OPENAQ_INDIA_DISCOVERY_PAGE_SIZE
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

    logger.info("india_discovery.start", max_pages=max_pages, page_size=page_size)

    sample_cities: set[str] = set()
    sample_states: set[str] = set()
    reached_max_pages = True

    try:
        async with AsyncSession() as session:
            for page in range(1, max_pages + 1):
                page_result = None
                for attempt in range(_INDIA_DISCOVERY_PAGE_RETRY_ATTEMPTS + 1):
                    # A transient (network/5xx) page failure is worth a
                    # bounded retry; a location that fails *validation*
                    # is a permanent error handled per-location below and
                    # never reaches this retry loop.
                    page_result = await openaq.fetch_country_locations(
                        page=page, limit=page_size
                    )
                    if page_result is not None:
                        break
                    if attempt < _INDIA_DISCOVERY_PAGE_RETRY_ATTEMPTS:
                        logger.warning(
                            "india_discovery.page_retry",
                            page=page,
                            attempt=attempt + 1,
                        )
                        await asyncio.sleep(_INDIA_DISCOVERY_PAGE_RETRY_DELAY_SECONDS)

                summary["pages_processed"] += 1

                if page_result is None:
                    summary["errors"] += 1
                    reached_max_pages = False
                    logger.error(
                        "india_discovery.error", page=page, reason="fetch_failed"
                    )
                    break

                summary["locations_discovered"] += page_result.raw_count

                page_created = 0
                page_updated = 0
                page_existing = 0
                page_skipped = page_result.invalid_count
                seen_in_page: set[int] = set()

                for location in page_result.locations:
                    if location.openaq_location_id in seen_in_page:
                        page_skipped += 1
                        summary["stations_skipped"] += 1
                        continue
                    seen_in_page.add(location.openaq_location_id)

                    try:
                        async with session.begin_nested():
                            _station_id, outcome = await _ensure_discovered_station(
                                session, location
                            )
                    except Exception as exc:
                        page_skipped += 1
                        summary["stations_skipped"] += 1
                        logger.warning(
                            "india_discovery.location_skipped",
                            page=page,
                            openaq_location_id=location.openaq_location_id,
                            error=str(exc),
                        )
                        continue

                    if outcome == "invalid":
                        page_skipped += 1
                        summary["stations_skipped"] += 1
                        continue
                    if outcome == "created":
                        page_created += 1
                        summary["stations_created"] += 1
                    elif outcome == "updated":
                        page_updated += 1
                        summary["stations_updated"] += 1
                    else:  # curated_preserved
                        page_existing += 1
                        summary["stations_existing"] += 1

                    if location.city:
                        sample_cities.add(location.city)
                    if location.state:
                        sample_states.add(location.state)

                await session.commit()

                logger.info(
                    "india_discovery.page",
                    page=page,
                    raw_count=page_result.raw_count,
                    valid_count=len(page_result.locations),
                    invalid_count=page_result.invalid_count,
                    created_count=page_created,
                    updated_count=page_updated,
                    existing_count=page_existing,
                    skipped_count=page_skipped,
                    meta_found=page_result.meta_found,
                )

                if page_result.meta_found is not None:
                    if page * page_result.page_size >= page_result.meta_found:
                        summary["complete"] = True
                        reached_max_pages = False
                        break
                elif page_result.raw_count < page_result.page_size:
                    summary["complete"] = True
                    reached_max_pages = False
                    break

            summary["capped"] = reached_max_pages and not summary["complete"]
    except Exception as exc:
        summary["errors"] += 1
        logger.error("india_discovery.error", error=str(exc))
        raise
    finally:
        await engine.dispose()

    logger.info(
        "india_discovery.complete",
        pages_processed=summary["pages_processed"],
        locations_discovered=summary["locations_discovered"],
        stations_created=summary["stations_created"],
        stations_updated=summary["stations_updated"],
        stations_existing=summary["stations_existing"],
        stations_skipped=summary["stations_skipped"],
        errors=summary["errors"],
        complete=summary["complete"],
        capped=summary["capped"],
        discovered_station_count=summary["stations_created"]
        + summary["stations_updated"]
        + summary["stations_existing"],
        sample_cities=sorted(sample_cities)[:10],
        sample_states=sorted(sample_states)[:10],
    )
    return summary


INDIA_AQI_CURSOR_KEY = "openaq:india:ingestion:cursor"


def _india_openaq_station_conditions():
    """Shared eligibility filter for India OpenAQ ingestion — used both to
    select the next batch and to compute batch-completion progress
    (`_get_india_ingestion_progress`), so "how many stations are there"
    and "which stations get selected" can never silently drift apart."""
    from app.models.monitoring import MonitoringStation

    return (
        MonitoringStation.country == "India",
        MonitoringStation.station_type == "OpenAQ",
        # Belt-and-suspenders alongside station_type == "OpenAQ": a
        # station with no openaq_location_id has nothing for
        # `openaq.fetch_location_reading` to poll, so it must never be
        # selected for OpenAQ ingestion regardless of how it got tagged.
        MonitoringStation.openaq_location_id.isnot(None),
        MonitoringStation.is_active.is_(True),
        MonitoringStation.is_deleted.is_(False),
    )


async def _get_india_ingestion_progress(session, cursor: str | None) -> dict:
    """Cross-batch progress for the `india_batch_complete` log — how many
    of the eligible India OpenAQ stations have been passed by the cursor
    so far, out of the total. Purely a read against the same eligibility
    filter used for selection; never mutates the cursor itself."""
    from app.models.monitoring import MonitoringStation

    conditions = _india_openaq_station_conditions()

    total = (
        await session.execute(
            select(func.count()).select_from(MonitoringStation).where(*conditions)
        )
    ).scalar_one()

    if cursor:
        processed_total = (
            await session.execute(
                select(func.count())
                .select_from(MonitoringStation)
                .where(*conditions, MonitoringStation.station_code <= cursor)
            )
        ).scalar_one()
    else:
        processed_total = 0

    return {
        "total_stations": total,
        "processed_total": processed_total,
        "remaining_count": max(0, total - processed_total),
    }


async def _get_india_station_batch(session, batch_size: int):
    from app.models.monitoring import MonitoringStation

    redis = await get_redis()
    cursor = await redis.get(INDIA_AQI_CURSOR_KEY)

    base_conditions = _india_openaq_station_conditions()

    query = select(MonitoringStation).where(*base_conditions)
    if cursor:
        query = query.where(MonitoringStation.station_code > cursor)
    query = query.order_by(MonitoringStation.station_code).limit(batch_size)
    result = await session.execute(query)
    stations = list(result.scalars().all())

    if not stations and cursor:
        await redis.delete(INDIA_AQI_CURSOR_KEY)
        query = (
            select(MonitoringStation)
            .where(*base_conditions)
            .order_by(MonitoringStation.station_code)
            .limit(batch_size)
        )
        result = await session.execute(query)
        stations = list(result.scalars().all())

    return stations


async def _ingest_india_station_batch_async(batch_size: int | None = None) -> dict:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.monitoring import AQIReading, MonitoringStation

    if not openaq.is_configured():
        return {"configured": False, "stations_selected": 0, "readings_ingested": 0}

    batch_size = batch_size or settings.OPENAQ_INDIA_INGEST_BATCH_SIZE
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
    summary = {
        "configured": True,
        "stations_selected": 0,
        "readings_ingested": 0,
        "no_current_observation": 0,
        # Distinct from `no_current_observation`: OpenAQ *did* return a
        # usable observation, it's just the same one already on file (no
        # newer timestamp yet). Without this counter, `india_ingestion.complete`
        # showing `readings_ingested: 0` was indistinguishable in the logs
        # from a batch where every station's observation was silently
        # dropped for some other reason — the two look identical unless you
        # go find each station's own per-station log line.
        "no_new_observation": 0,
        "duplicate_observation_skipped": 0,
        # Counts readings that WERE inserted (a subset of
        # readings_ingested) but whose OpenAQ observation was already
        # stale at ingest time (see openaq.LiveReading.is_stale) — kept
        # distinct from `no_current_observation`/`no_new_observation`,
        # which mean no usable/no newer observation existed at all.
        "stale_count": 0,
        "errors": 0,
    }

    logger.info("india_ingestion.start", batch_size=batch_size)

    try:
        async with AsyncSession() as session:
            stations = await _get_india_station_batch(session, batch_size)
            summary["stations_selected"] = len(stations)
            redis = await get_redis()

            logger.info(
                "india_ingestion.batch",
                stations_selected=len(stations),
                sample_station_codes=[s.station_code for s in stations][:10],
            )

            for station in stations:
                try:
                    live = await openaq.fetch_location_reading(
                        station.openaq_location_id, station.name
                    )
                    # Any of the six mapped pollutants is enough to accept
                    # the observation — requiring pm25 specifically meant a
                    # station reporting only e.g. pm10/no2 was wrongly
                    # treated as having "no current observation" even
                    # though OpenAQ returned a perfectly usable reading.
                    if live is None or all(
                        v is None
                        for v in (
                            live.pm25,
                            live.pm10,
                            live.no2,
                            live.so2,
                            live.co,
                            live.o3,
                        )
                    ):
                        summary["no_current_observation"] += 1
                        await session.commit()
                        await redis.set(INDIA_AQI_CURSOR_KEY, station.station_code)
                        continue

                    latest_result = await session.execute(
                        select(AQIReading.timestamp)
                        .where(
                            AQIReading.station_id == station.id,
                            AQIReading.is_deleted.is_(False),
                            AQIReading.quality_flag != "synthetic",
                        )
                        .order_by(AQIReading.timestamp.desc())
                        .limit(1)
                    )
                    latest_ts = latest_result.scalar_one_or_none()
                    is_new_observation = (
                        latest_ts is None or live.observed_at > latest_ts
                    )
                    outcome = "no_new_observation"

                    if is_new_observation:
                        session.add(
                            AQIReading(
                                station_id=station.id,
                                pm25=live.pm25,
                                pm10=live.pm10,
                                no2=live.no2,
                                so2=live.so2,
                                co=live.co,
                                o3=live.o3,
                                aqi=calculate_overall_aqi(
                                    pm25=live.pm25,
                                    pm10=live.pm10,
                                    no2=live.no2,
                                    so2=live.so2,
                                    co=live.co,
                                    o3=live.o3,
                                ),
                                temperature=live.temperature,
                                humidity=live.humidity,
                                wind_speed=live.wind_speed,
                                wind_direction=live.wind_direction,
                                timestamp=live.observed_at,
                                latitude=station.latitude,
                                longitude=station.longitude,
                                quality_flag=(
                                    "stale"
                                    if getattr(live, "is_stale", False)
                                    else "good"
                                ),
                                raw_data=json.dumps(
                                    {
                                        "source": "openaq",
                                        "openaq_location_id": live.openaq_location_id,
                                        "openaq_location_name": live.openaq_location_name,
                                        "observed_at": live.observed_at.isoformat(),
                                        "age_seconds": live.age_seconds,
                                        "freshness": (
                                            "stale" if live.is_stale else "current"
                                        ),
                                    }
                                ),
                            )
                        )
                        try:
                            await session.flush()
                        except IntegrityError:
                            # Same race as the six-station path: another
                            # concurrent run (or an overlapping slow tick)
                            # already inserted this exact (station_id,
                            # timestamp) observation first. Not an error —
                            # someone else already recorded it.
                            await session.rollback()
                            outcome = "duplicate_observation_skipped"
                            summary["duplicate_observation_skipped"] += 1
                        else:
                            outcome = "inserted"
                            summary["readings_ingested"] += 1
                            if getattr(live, "is_stale", False):
                                summary["stale_count"] += 1
                    else:
                        summary["no_new_observation"] += 1

                    logger.info(
                        "aqi_ingestion.india_station_observation",
                        station_code=station.station_code,
                        openaq_location_id=live.openaq_location_id,
                        observed_at=live.observed_at.isoformat(),
                        age_seconds=round(getattr(live, "age_seconds", 0.0), 1),
                        freshness=(
                            "stale" if getattr(live, "is_stale", False) else "current"
                        ),
                        latest_stored_at=(
                            latest_ts.isoformat() if latest_ts is not None else None
                        ),
                        outcome=outcome,
                    )

                    await session.execute(
                        update(MonitoringStation)
                        .where(MonitoringStation.id == station.id)
                        .values(last_data_at=live.observed_at)
                    )
                    await session.commit()
                    await redis.set(INDIA_AQI_CURSOR_KEY, station.station_code)
                except Exception as exc:
                    await session.rollback()
                    summary["errors"] += 1
                    logger.error(
                        "aqi_ingestion.india_station_error",
                        station_code=station.station_code,
                        error=str(exc),
                    )
                    # Advance the cursor even on failure — otherwise a
                    # station that reliably errors (a bad OpenAQ id, a
                    # transient parsing issue, ...) would get selected
                    # first in every subsequent batch forever, starving
                    # every station after it in the ordering from ever
                    # being ingested.
                    await redis.set(INDIA_AQI_CURSOR_KEY, station.station_code)

            cursor_after = await redis.get(INDIA_AQI_CURSOR_KEY)
            try:
                progress = await _get_india_ingestion_progress(session, cursor_after)
            except Exception as exc:
                # Progress accounting is diagnostic, not load-bearing —
                # never let a failure here (e.g. a transient DB hiccup)
                # affect a batch that otherwise ingested successfully.
                logger.warning("india_ingestion.progress_query_failed", error=str(exc))
                progress = {
                    "total_stations": None,
                    "processed_total": None,
                    "remaining_count": None,
                }
            summary.update(progress)
            summary["cursor"] = cursor_after

            # Single source of truth for batch-completion progress —
            # required fields per the India OpenAQ backfill spec so a
            # batch's outcome and the backfill's overall progress can be
            # read off one log line without cross-referencing others.
            logger.info(
                "india_batch_complete",
                batch_size=batch_size,
                inserted_count=summary["readings_ingested"],
                no_new_count=summary["no_new_observation"],
                unavailable_count=summary["no_current_observation"],
                stale_count=summary["stale_count"],
                error_count=summary["errors"],
                duplicate_observation_skipped=summary["duplicate_observation_skipped"],
                processed_total=progress["processed_total"],
                remaining_count=progress["remaining_count"],
                total_stations=progress["total_stations"],
                cursor=cursor_after,
            )

    finally:
        await engine.dispose()

    logger.info("india_ingestion.complete", **summary)
    return summary


def ingest_india_latest_measurements():
    return asyncio.run(_ingest_india_station_batch_async())


def fetch_weather_data():
    """Fetch meteorological data from Open-Meteo for all cities."""
    asyncio.run(_fetch_weather_async())


async def _fetch_weather_async():
    city_coords = {
        "Pune": (18.5204, 73.8567),
        "Mumbai": (19.0760, 72.8777),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        for city, (lat, lon) in city_coords.items():
            try:
                url = (
                    f"{settings.OPEN_METEO_BASE_URL}/forecast"
                    f"?latitude={lat}&longitude={lon}"
                    f"&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,precipitation"
                    f"&forecast_days=3"
                )
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    logger.info(
                        "weather_fetch.success",
                        city=city,
                        hours=len(data.get("hourly", {}).get("time", [])),
                    )
                else:
                    logger.warning(
                        "weather_fetch.failed", city=city, status=resp.status_code
                    )
            except Exception as e:
                logger.error("weather_fetch.error", city=city, error=str(e))
