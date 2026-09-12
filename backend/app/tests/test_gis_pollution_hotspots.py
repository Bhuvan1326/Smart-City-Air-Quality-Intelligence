from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.gis.operations import GISService
from app.models.monitoring import AQIReading, MonitoringStation

# Two of the six authoritative Pune stations (see
# app.services.aqi_providers.pune_stations.REQUIRED_STATIONS) — Pollution
# Ward/hotspots must source current-AQI clustering exclusively from these,
# never from the legacy PUNE_001..PUNE_008 ward fixtures (requirement 1/4).
LIVE_CODE_A = "PUNE_LIVE_SPPU"
LIVE_CODE_B = "PUNE_LIVE_HADAPSAR"


async def _create_station(
    session: AsyncSession, code: str, lat: float, lon: float
) -> MonitoringStation:
    from geoalchemy2.elements import WKTElement

    station = MonitoringStation(
        name=f"Hotspot Station {code}",
        station_code=code,
        city="Pune",
        ward_id="W01",
        operator="MPCB",
        latitude=lat,
        longitude=lon,
        geometry=WKTElement(f"POINT({lon} {lat})", srid=4326),
        is_active=True,
    )
    session.add(station)
    await session.flush()
    return station


async def _create_reading(
    session: AsyncSession,
    station: MonitoringStation,
    aqi: int,
    hours_ago: float = 0.1,
    pm25: float = 90.0,
    quality_flag: str = "good",
) -> AQIReading:
    reading = AQIReading(
        station_id=station.id,
        pm25=pm25,
        pm10=110.0,
        aqi=aqi,
        no2=30.0,
        so2=10.0,
        co=1.2,
        o3=25.0,
        temperature=28.0,
        humidity=50.0,
        wind_speed=2.5,
        wind_direction=180.0,
        timestamp=datetime.now(UTC) - timedelta(hours=hours_ago),
        latitude=station.latitude,
        longitude=station.longitude,
        quality_flag=quality_flag,
    )
    session.add(reading)
    await session.flush()
    return reading


@pytest.mark.asyncio
async def test_pollution_hotspots_clusters_nearby_unhealthy_stations(
    db_session: AsyncSession,
):
    # Two authoritative Pune Live stations ~200m apart (well within the
    # default 1.5km radius) both reporting unhealthy AQI should merge into
    # a single cluster.
    station_a = await _create_station(db_session, LIVE_CODE_A, 18.5200, 73.8500)
    station_b = await _create_station(db_session, LIVE_CODE_B, 18.5218, 73.8500)
    await _create_reading(db_session, station_a, aqi=160)
    await _create_reading(db_session, station_b, aqi=180)
    await db_session.commit()

    svc = GISService(db_session)
    hotspots = await svc.pollution_hotspots("Pune")

    assert len(hotspots) == 1
    cluster = hotspots[0]
    assert cluster["point_count"] == 2
    assert cluster["peak_aqi"] == pytest.approx(180.0)
    assert cluster["avg_aqi"] == pytest.approx(170.0)
    assert cluster["aqi_category"] in ("Unhealthy", "Very Unhealthy")
    assert cluster["dominant_pollutant"] in ("pm25", "pm10", "no2", "so2", "o3")
    assert cluster["approx_radius_m"] >= 200.0


@pytest.mark.asyncio
async def test_pollution_hotspots_excludes_legacy_ward_fixture_stations(
    db_session: AsyncSession,
):
    """Regression test for requirement 1/4: a legacy PUNE_00X-style
    station reporting unhealthy AQI must NOT surface as a current-AQI
    pollution hotspot for Pune, even though it shares `city="Pune"` with
    the authoritative stations."""
    legacy_station = await _create_station(db_session, "PUNE_003", 18.50, 73.80)
    await _create_reading(db_session, legacy_station, aqi=250)
    await db_session.commit()

    svc = GISService(db_session)
    hotspots = await svc.pollution_hotspots("Pune")

    assert hotspots == []


@pytest.mark.asyncio
async def test_pollution_hotspots_ignores_synthetic_readings(
    db_session: AsyncSession,
):
    """A synthetic/demo reading on an otherwise-authoritative station must
    never be presented as a current pollution hotspot (requirement 9)."""
    station = await _create_station(db_session, LIVE_CODE_A, 18.50, 73.80)
    await _create_reading(db_session, station, aqi=220, quality_flag="synthetic")
    await db_session.commit()

    svc = GISService(db_session)
    hotspots = await svc.pollution_hotspots("Pune")

    assert hotspots == []


@pytest.mark.asyncio
async def test_pollution_hotspots_keeps_distant_stations_as_separate_clusters(
    db_session: AsyncSession,
):
    # The six authoritative Pune stations are real ~20km-scale locations
    # across the city -- well outside the default 1.5km clustering radius.
    station_a = await _create_station(db_session, LIVE_CODE_A, 18.50, 73.80)
    station_b = await _create_station(db_session, LIVE_CODE_B, 18.70, 73.80)
    await _create_reading(db_session, station_a, aqi=150)
    await _create_reading(db_session, station_b, aqi=155)
    await db_session.commit()

    svc = GISService(db_session)
    hotspots = await svc.pollution_hotspots("Pune")

    assert len(hotspots) == 2
    assert {h["point_count"] for h in hotspots} == {1}


@pytest.mark.asyncio
async def test_pollution_hotspots_excludes_stations_below_aqi_threshold(
    db_session: AsyncSession,
):
    station = await _create_station(db_session, LIVE_CODE_A, 18.50, 73.80)
    await _create_reading(db_session, station, aqi=45)
    await db_session.commit()

    svc = GISService(db_session)
    hotspots = await svc.pollution_hotspots("Pune")

    assert hotspots == []


@pytest.mark.asyncio
async def test_pollution_hotspots_ignores_stale_readings(db_session: AsyncSession):
    station = await _create_station(db_session, LIVE_CODE_A, 18.50, 73.80)
    # Reading from 5 hours ago is outside the "last hour" window this
    # endpoint uses to represent *current* conditions.
    await _create_reading(db_session, station, aqi=200, hours_ago=5)
    await db_session.commit()

    svc = GISService(db_session)
    hotspots = await svc.pollution_hotspots("Pune")

    assert hotspots == []


@pytest.mark.asyncio
async def test_pollution_hotspots_non_pune_city_unaffected_by_station_filter(
    db_session: AsyncSession,
):
    """Cities other than Pune have no legacy/live station split, so any
    active station reporting unhealthy AQI should still surface."""
    from geoalchemy2.elements import WKTElement

    station = MonitoringStation(
        name="Mumbai Station",
        station_code="MUMBAI_001",
        city="Mumbai",
        ward_id="M01",
        operator="MPCB",
        latitude=19.07,
        longitude=72.87,
        geometry=WKTElement("POINT(72.87 19.07)", srid=4326),
        is_active=True,
    )
    db_session.add(station)
    await db_session.flush()
    await _create_reading(db_session, station, aqi=180)
    await db_session.commit()

    svc = GISService(db_session)
    hotspots = await svc.pollution_hotspots("Mumbai")

    assert len(hotspots) == 1


@pytest.mark.asyncio
async def test_pollution_hotspots_endpoint_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/gis/pollution-hotspots?city=Pune")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pollution_hotspots_endpoint_returns_list(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    station = await _create_station(db_session, LIVE_CODE_A, 18.50, 73.80)
    await _create_reading(db_session, station, aqi=170)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/gis/pollution-hotspots?city=Pune", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["point_count"] == 1
