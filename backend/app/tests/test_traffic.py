from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.traffic import _congestion_category, _traffic_level_for_hour
from app.models.monitoring import MonitoringStation


async def _create_station(session: AsyncSession, code: str = "TRAFFIC_001"):
    from geoalchemy2.elements import WKTElement

    station = MonitoringStation(
        name="Traffic Test Station",
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


def test_traffic_level_is_higher_during_morning_rush_hour_than_at_night():
    rush_hour = _traffic_level_for_hour(hour=8, day_of_week=1)
    late_night = _traffic_level_for_hour(hour=3, day_of_week=1)
    assert rush_hour > late_night


def test_traffic_level_is_higher_during_evening_rush_hour_than_midday():
    evening_rush = _traffic_level_for_hour(hour=18, day_of_week=2)
    midday = _traffic_level_for_hour(hour=13, day_of_week=2)
    assert evening_rush > midday


def test_traffic_level_is_lower_on_weekends_than_weekdays_at_same_hour():
    weekday = _traffic_level_for_hour(hour=8, day_of_week=1)  # Tuesday
    weekend = _traffic_level_for_hour(hour=8, day_of_week=5)  # Saturday
    assert weekend < weekday


def test_traffic_level_is_always_clamped_to_0_100_range():
    assert 0.0 <= _traffic_level_for_hour(hour=8, day_of_week=1, offset=1000) <= 100.0
    assert 0.0 <= _traffic_level_for_hour(hour=3, day_of_week=6, offset=-1000) <= 100.0


@pytest.mark.parametrize(
    "level,expected",
    [
        (5, "free_flow"),
        (30, "light"),
        (55, "moderate"),
        (75, "heavy"),
        (95, "gridlock"),
    ],
)
def test_congestion_category_thresholds(level, expected):
    assert _congestion_category(level) == expected


@pytest.mark.asyncio
async def test_traffic_current_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/traffic/current?city=Pune")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_traffic_current_is_always_marked_simulated(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    await _create_station(db_session, "TRAFFIC_CURRENT")
    await db_session.commit()

    resp = await client.get("/api/v1/traffic/current?city=Pune", headers=auth_headers)
    assert resp.status_code == 200
    readings = resp.json()["data"]
    assert isinstance(readings, list)
    for reading in readings:
        assert reading["is_simulated"] is True
        assert reading["congestion_category"] in (
            "free_flow",
            "light",
            "moderate",
            "heavy",
            "gridlock",
        )
        assert 0.0 <= reading["traffic_level"] <= 100.0


@pytest.mark.asyncio
async def test_traffic_correlation_reports_insufficient_data_when_no_readings(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get(
        "/api/v1/traffic/correlation?city=NonExistentCityForCorrelation",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_simulated"] is True
    assert data["correlation_coefficient"] is None
    assert data["strength"] == "insufficient_data"
    assert data["samples"] == []


@pytest.mark.asyncio
async def test_traffic_correlation_computes_real_coefficient_from_paired_series(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    from app.models.monitoring import AQIReading

    station = await _create_station(db_session, "TRAFFIC_CORR")
    now = datetime.now(UTC)
    for i in range(10):
        reading = AQIReading(
            station_id=station.id,
            pm25=50.0,
            pm10=80.0,
            aqi=100 + i,
            no2=25.0,
            so2=8.0,
            co=1.0,
            o3=20.0,
            temperature=27.0,
            humidity=55.0,
            wind_speed=3.0,
            wind_direction=180.0,
            timestamp=now - timedelta(hours=i),
            latitude=18.52,
            longitude=73.85,
            quality_flag="good",
        )
        db_session.add(reading)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/traffic/correlation?city=Pune&hours=24", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_simulated"] is True
    assert data["sample_count"] >= 5
    assert data["strength"] in ("weak", "moderate", "strong")
    assert -1.0 <= data["correlation_coefficient"] <= 1.0
    assert len(data["samples"]) == data["sample_count"]
    for sample in data["samples"]:
        assert "traffic_level" in sample
        assert "aqi" in sample
