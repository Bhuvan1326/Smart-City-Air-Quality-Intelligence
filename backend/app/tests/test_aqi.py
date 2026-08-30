from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import AQIReading, MonitoringStation


async def _create_station(
    session: AsyncSession, code: str = "TEST_001"
) -> MonitoringStation:
    from geoalchemy2.elements import WKTElement

    station = MonitoringStation(
        name="Test Station",
        station_code=code,
        city="Pune",
        ward_id="W01",
        operator="MPCB",
        latitude=18.52,
        longitude=73.85,
        geometry=WKTElement("POINT(73.85 18.52)", srid=4326),
        is_active=True,
    )
    session.add(station)
    await session.flush()
    return station


async def _create_reading(
    session: AsyncSession, station_id, aqi: int = 120
) -> AQIReading:
    reading = AQIReading(
        station_id=station_id,
        pm25=55.0,
        pm10=90.0,
        aqi=aqi,
        no2=30.0,
        so2=10.0,
        co=1.2,
        o3=25.0,
        temperature=27.0,
        humidity=60.0,
        wind_speed=3.0,
        wind_direction=180.0,
        timestamp=datetime.now(UTC),
        latitude=18.52,
        longitude=73.85,
        quality_flag="good",
    )
    session.add(reading)
    await session.flush()
    return reading


@pytest.mark.asyncio
async def test_list_stations_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/aqi/stations")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_stations(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    await _create_station(db_session, "LIST_001")
    resp = await client.get("/api/v1/aqi/stations?city=Pune", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "items" in body["data"]


@pytest.mark.asyncio
async def test_live_aqi_empty_city(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/aqi/live?city=NonExistentCity", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_live_aqi_with_data(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    station = await _create_station(db_session, "LIVE_001")
    await _create_reading(db_session, station.id, aqi=150)
    await db_session.commit()

    resp = await client.get("/api/v1/aqi/live?city=Pune", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_live_aqi_requires_city_when_no_scope(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get("/api/v1/aqi/live", headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_live_aqi_scope_all_returns_stations_across_cities(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    from geoalchemy2.elements import WKTElement

    pune_station = await _create_station(db_session, "ALL_PUNE_001")
    await _create_reading(db_session, pune_station.id, aqi=110)

    mumbai_station = MonitoringStation(
        name="Mumbai Test Station",
        station_code="ALL_MUM_001",
        city="Mumbai",
        ward_id="H/W",
        operator="MPCB",
        latitude=19.06,
        longitude=72.83,
        geometry=WKTElement("POINT(72.83 19.06)", srid=4326),
        is_active=True,
    )
    db_session.add(mumbai_station)
    await db_session.flush()
    await _create_reading(db_session, mumbai_station.id, aqi=95)
    await db_session.commit()

    resp = await client.get("/api/v1/aqi/live?scope=all", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    cities = {item["station"]["city"] for item in data}
    assert "Pune" in cities
    assert "Mumbai" in cities


@pytest.mark.asyncio
async def test_live_aqi_contract_city_scope_all_and_missing_both(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """Explicit contract check for GET /aqi/live:
    - city=<name>            -> 200, that city's stations
    - scope=all               -> 200, stations across every city
    - neither city nor scope  -> 422 (city is required unless scope=all)
    """
    station = await _create_station(db_session, "CONTRACT_001")
    await _create_reading(db_session, station.id, aqi=80)
    await db_session.commit()

    city_resp = await client.get("/api/v1/aqi/live?city=Pune", headers=auth_headers)
    assert city_resp.status_code == 200

    all_resp = await client.get("/api/v1/aqi/live?scope=all", headers=auth_headers)
    assert all_resp.status_code == 200

    neither_resp = await client.get("/api/v1/aqi/live", headers=auth_headers)
    assert neither_resp.status_code == 422


@pytest.mark.asyncio
async def test_aqi_history_requires_city_or_station(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get(
        "/api/v1/aqi/history?start_time=2024-01-01T00:00:00Z&end_time=2024-01-02T00:00:00Z",
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert "status" in body
    assert "checks" in body
