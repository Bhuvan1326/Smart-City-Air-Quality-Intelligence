from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import AQIReading, MonitoringStation
from app.services.aqi_providers import pune_stations

HADAPSAR_SPEC = next(
    s for s in pune_stations.REQUIRED_STATIONS if s.station_code == "PUNE_LIVE_HADAPSAR"
)


async def _create_pune_live_station(
    session: AsyncSession, spec, ward_id: str, openaq_location_id: int = 555
) -> MonitoringStation:
    from geoalchemy2.elements import WKTElement

    station = MonitoringStation(
        name=spec.display_name,
        station_code=spec.station_code,
        city=spec.city,
        state=spec.state,
        country=spec.country,
        operator=f"{spec.provider} (via OpenAQ)",
        latitude=spec.approx_lat,
        longitude=spec.approx_lon,
        geometry=WKTElement(f"POINT({spec.approx_lon} {spec.approx_lat})", srid=4326),
        is_active=True,
        station_type="OpenAQ",
        openaq_location_id=openaq_location_id,
        ward_id=ward_id,
    )
    session.add(station)
    await session.flush()
    return station


async def _create_legacy_ward_fixture_station(
    session: AsyncSession, code: str, ward_id: str
) -> MonitoringStation:
    """A PUNE_00X-style legacy ward CAAQMS fixture — same city, not one of
    the six authoritative real-time stations."""
    from geoalchemy2.elements import WKTElement

    station = MonitoringStation(
        name=f"{ward_id} CAAQMS",
        station_code=code,
        city="Pune",
        operator="MPCB / CPCB",
        latitude=18.52,
        longitude=73.85,
        geometry=WKTElement("POINT(73.85 18.52)", srid=4326),
        is_active=True,
        station_type="CAAQMS",
        ward_id=ward_id,
    )
    session.add(station)
    await session.flush()
    return station


def _add_reading(
    session: AsyncSession,
    station: MonitoringStation,
    *,
    aqi: int,
    quality_flag: str = "good",
) -> AQIReading:
    reading = AQIReading(
        station_id=station.id,
        pm25=68.2,
        pm10=110.0,
        aqi=aqi,
        no2=20.0,
        so2=5.0,
        co=1.0,
        o3=15.0,
        temperature=28.0,
        humidity=45.0,
        wind_speed=2.5,
        wind_direction=210.0,
        timestamp=datetime.now(UTC),
        latitude=station.latitude,
        longitude=station.longitude,
        quality_flag=quality_flag,
    )
    session.add(reading)
    return reading


@pytest.mark.asyncio
async def test_mitigation_recommendations_ignores_synthetic_legacy_reading(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """A legacy fixture station with a deliberately high *synthetic* AQI
    must not be crowned "worst ward" over a real, current station with a
    lower but real reading."""
    real_station = await _create_pune_live_station(db_session, HADAPSAR_SPEC, ward_id="W03")
    _add_reading(db_session, real_station, aqi=120, quality_flag="good")

    legacy_station = await _create_legacy_ward_fixture_station(
        db_session, "PUNE_003", ward_id="W03"
    )
    _add_reading(db_session, legacy_station, aqi=350, quality_flag="synthetic")

    await db_session.commit()

    resp = await client.get(
        "/api/v1/mitigation/recommendations?city=Pune", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["aqi"] == 120


@pytest.mark.asyncio
async def test_health_risk_ignores_synthetic_legacy_reading(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """Same guarantee for /aqi/health-risk's citywide worst-station pick."""
    real_station = await _create_pune_live_station(db_session, HADAPSAR_SPEC, ward_id="W03")
    _add_reading(db_session, real_station, aqi=120, quality_flag="good")

    legacy_station = await _create_legacy_ward_fixture_station(
        db_session, "PUNE_003", ward_id="W03"
    )
    _add_reading(db_session, legacy_station, aqi=350, quality_flag="synthetic")

    await db_session.commit()

    resp = await client.get("/api/v1/aqi/health-risk?city=Pune", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["aqi"] == 120
