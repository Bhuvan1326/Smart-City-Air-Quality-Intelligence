import asyncio
import json
import random
from datetime import UTC, datetime

import httpx
from sqlalchemy import select, update

from app.core.config import settings
from app.core.logging import logger
from app.services.aqi_providers import openaq
from app.workers.celery_app import celery_app

# Pune ward monitoring stations (real coordinates)
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
    """Generate realistic AQI with diurnal patterns and ward-specific baselines."""
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


@celery_app.task(
    name="app.workers.tasks.aqi_ingestion.fetch_live_aqi_all_cities",
    bind=True,
    max_retries=3,
)
def fetch_live_aqi_all_cities(self):
    """Pull live AQI data for all configured cities and persist to DB."""
    asyncio.run(_fetch_aqi_async())


async def _build_reading_for_station(s: dict, hour: int) -> tuple[dict, str, str]:
    """
    Returns (data, quality_flag, raw_data_json) for one station.

    Tries OpenAQ first (real ground-station data). Falls back to the
    statistical generator — clearly flagged as such via quality_flag and
    raw_data — if OpenAQ is unconfigured, has no nearby station, is
    unreachable, or only has stale data for this location.
    """
    if openaq.is_configured():
        live = await openaq.fetch_nearest_reading(s["lat"], s["lon"])
        if live is not None and live.pm25 is not None:
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

    # Fallback: no provider configured, no nearby station, or fetch failed.
    data = _generate_realistic_reading(s, hour)
    raw = json.dumps(
        {
            "source": "synthetic_fallback",
            "reason": (
                "openaq_unconfigured"
                if not openaq.is_configured()
                else "no_live_reading_available"
            ),
        }
    )
    return data, "synthetic", raw


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
            live_count = 0
            for s in stations:
                station_id = code_to_id[s["code"]]
                data, quality_flag, raw = await _build_reading_for_station(s, hour)
                if quality_flag == "good":
                    live_count += 1

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

            # Update each station's last_data_at so the station API/UI
            # reflects the actual latest successfully-ingested observation
            # time, instead of staying permanently null/stale.
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
                live_from_openaq=live_count,
                synthetic_fallback=len(readings) - live_count,
            )

    await engine.dispose()


@celery_app.task(
    name="app.workers.tasks.aqi_ingestion.fetch_weather_data", bind=True, max_retries=3
)
def fetch_weather_data(self):
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
            except Exception as e:  # noqa: BLE001 -- optional weather API, fail open
                logger.error("weather_fetch.error", city=city, error=str(e))
