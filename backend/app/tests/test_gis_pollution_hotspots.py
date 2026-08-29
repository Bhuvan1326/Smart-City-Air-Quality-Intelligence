from datetime import UTC, datetime, timedelta

import pytest
from app.gis.operations import GISService
from app.models.monitoring import AQIReading, MonitoringStation
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


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
        quality_flag="good",
    )
    session.add(reading)
    await session.flush()
    return reading


@pytest.mark.asyncio
async def test_pollution_hotspots_clusters_nearby_unhealthy_stations(
    db_session: AsyncSession,
):
    # Two stations ~200m apart (well within the default 1.5km radius) both
    # reporting unhealthy AQI should merge into a single cluster.
    station_a = await _create_station(db_session, "HOT_A", 18.5200, 73.8500)
    station_b = await _create_station(db_session, "HOT_B", 18.5218, 73.8500)
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
async def test_pollution_hotspots_keeps_distant_stations_as_separate_clusters(
    db_session: AsyncSession,
):
    # ~20km apart -- well outside the default 1.5km clustering radius.
    station_a = await _create_station(db_session, "FAR_A", 18.50, 73.80)
    station_b = await _create_station(db_session, "FAR_B", 18.70, 73.80)
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
    station = await _create_station(db_session, "CLEAN_001", 18.50, 73.80)
    await _create_reading(db_session, station, aqi=45)
    await db_session.commit()

    svc = GISService(db_session)
    hotspots = await svc.pollution_hotspots("Pune")

    assert hotspots == []


@pytest.mark.asyncio
async def test_pollution_hotspots_ignores_stale_readings(db_session: AsyncSession):
    station = await _create_station(db_session, "STALE_001", 18.50, 73.80)
    # Reading from 5 hours ago is outside the "last hour" window this
    # endpoint uses to represent *current* conditions.
    await _create_reading(db_session, station, aqi=200, hours_ago=5)
    await db_session.commit()

    svc = GISService(db_session)
    hotspots = await svc.pollution_hotspots("Pune")

    assert hotspots == []


@pytest.mark.asyncio
async def test_pollution_hotspots_endpoint_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/gis/pollution-hotspots?city=Pune")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pollution_hotspots_endpoint_returns_list(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    station = await _create_station(db_session, "ENDPOINT_HOT", 18.50, 73.80)
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
