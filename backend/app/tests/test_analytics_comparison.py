from datetime import UTC, datetime, timedelta

import pytest
from app.models.enforcement import EnforcementAction
from app.models.monitoring import AQIReading, MonitoringStation
from app.models.user import User
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_station(session: AsyncSession, code: str, city: str = "Pune"):
    from geoalchemy2.elements import WKTElement

    station = MonitoringStation(
        name=f"Comparison Station {code}",
        station_code=code,
        city=city,
        ward_id="W02",
        operator="MPCB",
        latitude=18.55,
        longitude=73.83,
        geometry=WKTElement("POINT(73.83 18.55)", srid=4326),
        is_active=True,
    )
    session.add(station)
    await session.flush()
    return station


async def _create_reading(
    session: AsyncSession, station: MonitoringStation, aqi: int, hours_ago: float
):
    reading = AQIReading(
        station_id=station.id,
        pm25=60.0,
        pm10=90.0,
        aqi=aqi,
        no2=20.0,
        so2=6.0,
        co=0.9,
        o3=18.0,
        temperature=27.0,
        humidity=50.0,
        wind_speed=3.0,
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
async def test_comparison_endpoint_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/analytics/comparison?cities=Pune")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_comparison_reports_no_data_for_city_with_no_readings(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get(
        "/api/v1/analytics/comparison?cities=NoDataCityXYZ&days=30",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    entry = data["cities"]["NoDataCityXYZ"]
    assert entry["has_data"] is False
    assert entry["current_aqi"] is None
    assert entry["avg_aqi"] is None
    assert entry["unhealthy_days"] == 0
    assert entry["enforcement_actions"] == 0
    assert "period_start" in data
    assert "period_end" in data
    assert "generated_at" in data


@pytest.mark.asyncio
async def test_comparison_computes_real_stats_for_city_with_data(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict, test_admin: User
):
    station = await _create_station(db_session, "COMPARE_A", city="ComparisonCityA")
    for i in range(5):
        await _create_reading(db_session, station, aqi=120 + i, hours_ago=i * 0.5)
    action = EnforcementAction(
        officer_id=test_admin.id,
        source_id=None,
        city="ComparisonCityA",
        action_type="notice",
        status="issued",
        title="Test enforcement action for comparison stats",
    )
    db_session.add(action)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/analytics/comparison?cities=ComparisonCityA&days=30",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    entry = resp.json()["data"]["cities"]["ComparisonCityA"]

    assert entry["has_data"] is True
    assert entry["avg_aqi"] == pytest.approx(122.0, abs=0.5)
    assert entry["max_aqi"] == 124
    assert entry["min_aqi"] == 120
    assert entry["current_aqi"] is not None
    assert entry["avg_pm25"] == pytest.approx(60.0)
    assert entry["trend"] in ("improving", "worsening", "stable")
    assert entry["enforcement_actions"] == 1
    assert entry["unhealthy_days"] >= 1  # all readings are AQI > 100


@pytest.mark.asyncio
async def test_comparison_respects_custom_date_range(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    station = await _create_station(db_session, "COMPARE_RANGE", city="ComparisonCityB")
    await _create_reading(db_session, station, aqi=140, hours_ago=1)
    await db_session.commit()

    today = datetime.now(UTC).date()
    start = (today - timedelta(days=2)).isoformat()
    end = today.isoformat()

    resp = await client.get(
        f"/api/v1/analytics/comparison?cities=ComparisonCityB&start_date={start}&end_date={end}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["period_start"] == start
    assert data["period_end"] == end
    assert data["cities"]["ComparisonCityB"]["has_data"] is True


@pytest.mark.asyncio
async def test_comparison_caps_at_six_cities(client: AsyncClient, auth_headers: dict):
    cities = [f"CapCity{i}" for i in range(8)]
    query = "&".join(f"cities={c}" for c in cities)

    resp = await client.get(
        f"/api/v1/analytics/comparison?{query}", headers=auth_headers
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]["cities"]) == 6
