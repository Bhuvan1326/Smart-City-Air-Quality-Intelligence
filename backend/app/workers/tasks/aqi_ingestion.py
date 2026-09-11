import asyncio
import json
import random
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, update
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
    """Create or update the MonitoringStation row for a resolved required
    station, using ONLY OpenAQ's own name/coordinates — never the
    approximate search-seed coordinates from `spec`. Returns the station.

    `existing_station` is whatever the caller already looked up (None on
    first-ever resolution) — passed in rather than re-queried here so
    this never issues a redundant duplicate SELECT.
    """
    from geoalchemy2.elements import WKTElement

    from app.models.monitoring import MonitoringStation

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

    if station is None:
        geom = WKTElement(f"POINT({lon} {lat})", srid=4326)
        station = MonitoringStation(
            id=uuid.uuid4(),
            name=spec.display_name,
            station_code=spec.station_code,
            city=spec.city,
            state=spec.state,
            country=spec.country,
            ward_id=None,
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
        spec.approx_lat, spec.approx_lon, radius_m=pune_stations.SEARCH_RADIUS_M
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

    if station is None or station.openaq_location_id is None:
        candidates = await openaq.search_locations_near(
            spec.approx_lat, spec.approx_lon, radius_m=pune_stations.SEARCH_RADIUS_M
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

    live = await openaq.fetch_location_reading(station.openaq_location_id, station.name)
    if live is None or all(
        v is None for v in (live.pm25, live.pm10, live.no2, live.so2, live.co, live.o3)
    ):
        if getattr(station, "openaq_location_stale_since", None) is None:
            station.openaq_location_stale_since = datetime.now(UTC)
        return "no_current_observation"

    if getattr(station, "openaq_location_stale_since", None) is not None:
        station.openaq_location_stale_since = None

    latest = await session.execute(
        select(AQIReading.timestamp)
        .where(AQIReading.station_id == station.id, AQIReading.is_deleted.is_(False))
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
            quality_flag="good",
            raw_data=json.dumps(
                {
                    "source": "openaq",
                    "openaq_location_id": live.openaq_location_id,
                    "openaq_location_name": live.openaq_location_name,
                    "observed_at": live.observed_at.isoformat(),
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

    await session.execute(
        update(MonitoringStation)
        .where(MonitoringStation.id == station.id)
        .values(last_data_at=live.observed_at)
    )
    return outcome


def _station_code_for_openaq_location(location_id: int) -> str:
    """Stable, idempotent station_code for a discovered OpenAQ location —
    re-running discovery must upsert the same row, never duplicate it."""
    return f"OPENAQ_IN_{location_id}"


def _city_for_location(location: dict) -> str | None:
    locality = (location.get("locality") or "").strip()
    if locality:
        return locality
    name = (location.get("name") or "").strip()
    return name or None


async def _ensure_discovered_station(session, location) -> tuple[object | None, bool]:
    from geoalchemy2.elements import WKTElement

    from app.models.monitoring import MonitoringStation

    if not location.city:
        return None, False

    code = _station_code_for_openaq_location(location.openaq_location_id)

    result = await session.execute(
        select(MonitoringStation.id).where(MonitoringStation.station_code == code)
    )
    row = result.one_or_none()
    if row:
        await session.execute(
            update(MonitoringStation)
            .where(MonitoringStation.id == row[0])
            .values(
                name=(
                    location.name or f"OpenAQ Station {location.openaq_location_id}"
                ).strip(),
                city=location.city,
                state=location.state,
                country="India",
                latitude=location.latitude,
                longitude=location.longitude,
                data_source_url=f"https://explore.openaq.org/locations/{location.openaq_location_id}",
                is_active=True,
            )
        )
        return row[0], False

    geom = WKTElement(f"POINT({location.longitude} {location.latitude})", srid=4326)
    station = MonitoringStation(
        id=uuid.uuid4(),
        name=(location.name or f"OpenAQ Station {location.openaq_location_id}").strip(),
        station_code=code,
        city=location.city,
        ward_id=None,
        operator="OpenAQ (CPCB / state boards)",
        state=location.state,
        latitude=location.latitude,
        longitude=location.longitude,
        geometry=geom,
        is_active=True,
        station_type="OpenAQ",
        data_source_url=(
            f"https://explore.openaq.org/locations/{location.openaq_location_id}"
        ),
    )
    # station.id is already a concrete UUID we generated above (not a
    # DB-assigned identity column), so no flush is needed to know it —
    # the row will be persisted with everything else on commit().
    session.add(station)
    return station.id, True


def discover_and_ingest_india_locations():
    return asyncio.run(_discover_india_locations_async())


async def _discover_india_locations_async(
    max_pages: int | None = None,
    page_size: int | None = None,
) -> dict:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    summary = {
        "configured": openaq.is_configured(),
        "locations_discovered": 0,
        "stations_created": 0,
        "stations_updated": 0,
        "pages_fetched": 0,
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

    try:
        async with AsyncSession() as session:
            for page in range(1, max_pages + 1):
                locations = await openaq.fetch_country_locations(
                    page=page, limit=page_size
                )
                summary["pages_fetched"] += 1
                if locations is None:
                    break
                if not locations:
                    break

                summary["locations_discovered"] += len(locations)
                for location in locations:
                    station_id, was_created = await _ensure_discovered_station(
                        session, location
                    )
                    if station_id is None:
                        continue
                    if was_created:
                        summary["stations_created"] += 1
                    else:
                        summary["stations_updated"] += 1

                await session.commit()

                if len(locations) < page_size:
                    break
    except Exception as exc:
        logger.error("aqi_ingestion.india_discovery_error", error=str(exc))
        raise
    finally:
        await engine.dispose()

    logger.info(
        "aqi_ingestion.india_discovery_complete",
        locations_discovered=summary["locations_discovered"],
        stations_created=summary["stations_created"],
        stations_updated=summary["stations_updated"],
        pages_fetched=summary["pages_fetched"],
    )
    return summary


INDIA_AQI_CURSOR_KEY = "openaq:india:ingestion:cursor"


async def _get_india_station_batch(session, batch_size: int):
    from app.models.monitoring import MonitoringStation

    redis = await get_redis()
    cursor = await redis.get(INDIA_AQI_CURSOR_KEY)

    query = select(MonitoringStation).where(
        MonitoringStation.country == "India",
        MonitoringStation.station_type == "OpenAQ",
        MonitoringStation.is_active.is_(True),
        MonitoringStation.is_deleted.is_(False),
    )
    if cursor:
        query = query.where(MonitoringStation.station_code > cursor)
    query = query.order_by(MonitoringStation.station_code).limit(batch_size)
    result = await session.execute(query)
    stations = list(result.scalars().all())

    if not stations and cursor:
        await redis.delete(INDIA_AQI_CURSOR_KEY)
        query = (
            select(MonitoringStation)
            .where(
                MonitoringStation.country == "India",
                MonitoringStation.station_type == "OpenAQ",
                MonitoringStation.is_active.is_(True),
                MonitoringStation.is_deleted.is_(False),
            )
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
        "errors": 0,
    }

    try:
        async with AsyncSession() as session:
            stations = await _get_india_station_batch(session, batch_size)
            summary["stations_selected"] = len(stations)
            redis = await get_redis()

            for station in stations:
                try:
                    live = await openaq.fetch_location_reading(
                        station.openaq_location_id, station.name
                    )
                    if live is None or live.pm25 is None:
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
                    if latest_ts is None or live.observed_at > latest_ts:
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
                                quality_flag="good",
                                raw_data=json.dumps(
                                    {
                                        "source": "openaq",
                                        "openaq_location_id": live.openaq_location_id,
                                        "openaq_location_name": live.openaq_location_name,
                                        "observed_at": live.observed_at.isoformat(),
                                    }
                                ),
                            )
                        )
                        summary["readings_ingested"] += 1

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

    finally:
        await engine.dispose()

    logger.info("aqi_ingestion.india_batch_complete", **summary)
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
