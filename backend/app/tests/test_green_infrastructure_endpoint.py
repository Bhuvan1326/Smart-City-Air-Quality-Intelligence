"""Integration tests for GET /green-infrastructure/priority.

Mirrors the DB-fixture pattern used by test_aqi_pune_live.py
(`_create_pune_live_station`) since this endpoint now shares the same
six-real-station, never-fabricate contract as GET /aqi/live. Requires a
live Postgres test database (see conftest.py TEST_DATABASE_URL) — these
tests are skipped/fail-to-collect in environments without one, same as
the rest of this project's DB-backed test suite.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import AQIReading, MonitoringStation
from app.services.aqi_providers import pune_stations

HADAPSAR_SPEC = next(
    s for s in pune_stations.REQUIRED_STATIONS if s.station_code == "PUNE_LIVE_HADAPSAR"
)
NIGDI_SPEC = next(
    s for s in pune_stations.REQUIRED_STATIONS if s.station_code == "PUNE_LIVE_NIGDI"
)


async def _create_pune_live_station(
    session: AsyncSession, spec, openaq_location_id: int = 100
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
        ward_id=None,
    )
    session.add(station)
    await session.flush()
    return station


async def _create_legacy_ward_fixture_station(
    session: AsyncSession, code: str, ward_id: str
) -> MonitoringStation:
    """A PUNE_00X-style legacy ward CAAQMS fixture — same city, but NOT
    one of the six required real-time stations. Used to prove Green
    Infrastructure never picks these up as if they were the real
    stations."""
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
    timestamp=None,
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
        timestamp=timestamp or datetime.now(UTC),
        latitude=station.latitude,
        longitude=station.longitude,
        quality_flag=quality_flag,
    )
    session.add(reading)
    return reading


@pytest.mark.asyncio
async def test_returns_exactly_six_entries_when_db_empty(
    client: AsyncClient, auth_headers: dict
):
    """No Pune stations resolved yet at all -> still 200, still exactly
    six entries (one per required station), all reported unavailable
    rather than omitted or fabricated."""
    resp = await client.get(
        "/api/v1/green-infrastructure/priority?city=Pune", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["scores"]) == 6
    assert all(s["status"] == "unavailable" for s in data["scores"])
    assert all(s["aqi"] is None for s in data["scores"])
    assert len(data["unavailable_stations"]) == 6


@pytest.mark.asyncio
async def test_fresh_valid_reading_is_scored_and_labeled_live(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    station = await _create_pune_live_station(db_session, HADAPSAR_SPEC)
    _add_reading(db_session, station, aqi=142)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/green-infrastructure/priority?city=Pune", headers=auth_headers
    )
    data = resp.json()["data"]
    hadapsar = next(
        s for s in data["scores"] if s["station_code"] == "PUNE_LIVE_HADAPSAR"
    )
    assert hadapsar["status"] == "ok"
    assert hadapsar["aqi"] == 142
    assert hadapsar["is_live"] is True
    assert hadapsar["is_synthetic"] is False
    assert hadapsar["data_source"] == "OpenAQ"
    assert hadapsar["priority"] is not None
    assert hadapsar["priority_score"] is not None


@pytest.mark.asyncio
async def test_synthetic_reading_never_used_as_current_aqi(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """A synthetic-flagged reading against one of the six real station
    rows must never be scored as if it were a genuine live observation —
    the station is reported unavailable instead of getting a fabricated
    priority."""
    station = await _create_pune_live_station(db_session, HADAPSAR_SPEC)
    _add_reading(db_session, station, aqi=500, quality_flag="synthetic")
    await db_session.commit()

    resp = await client.get(
        "/api/v1/green-infrastructure/priority?city=Pune", headers=auth_headers
    )
    data = resp.json()["data"]
    hadapsar = next(
        s for s in data["scores"] if s["station_code"] == "PUNE_LIVE_HADAPSAR"
    )
    assert hadapsar["status"] == "unavailable"
    assert hadapsar["aqi"] is None
    assert hadapsar["is_live"] is False
    assert hadapsar["priority"] is None


@pytest.mark.asyncio
async def test_stale_reading_is_reported_stale_not_scored_as_current(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    station = await _create_pune_live_station(db_session, HADAPSAR_SPEC)
    stale_timestamp = datetime.now(UTC) - timedelta(hours=5)
    _add_reading(db_session, station, aqi=142, timestamp=stale_timestamp)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/green-infrastructure/priority?city=Pune", headers=auth_headers
    )
    data = resp.json()["data"]
    hadapsar = next(
        s for s in data["scores"] if s["station_code"] == "PUNE_LIVE_HADAPSAR"
    )
    assert hadapsar["status"] == "stale"
    assert hadapsar["aqi"] is None
    assert hadapsar["priority"] is None
    assert hadapsar["reading_timestamp"] is not None


@pytest.mark.asyncio
async def test_legacy_ward_fixtures_are_never_used(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """PUNE_001..008 (W01..W08) ward CAAQMS fixtures must never stand in
    for one of the six required real-time stations, even when they have
    fresh readings and even though they share city='Pune'."""
    ward_station = await _create_legacy_ward_fixture_station(
        db_session, "PUNE_003", "W03"
    )
    _add_reading(db_session, ward_station, aqi=222)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/green-infrastructure/priority?city=Pune", headers=auth_headers
    )
    data = resp.json()["data"]
    codes = {s["station_code"] for s in data["scores"]}
    # Only the six PUNE_LIVE_* codes ever appear.
    assert codes == {s.station_code for s in pune_stations.REQUIRED_STATIONS}
    # The ward fixture reading (AQI 222) must not surface anywhere.
    assert all(s["aqi"] != 222 for s in data["scores"])
    # With no PUNE_LIVE_* station resolved, every entry is still unavailable.
    assert all(s["status"] == "unavailable" for s in data["scores"])


@pytest.mark.asyncio
async def test_traffic_and_demographics_are_reported_unavailable_not_fabricated(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    station = await _create_pune_live_station(db_session, NIGDI_SPEC)
    _add_reading(db_session, station, aqi=90)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/green-infrastructure/priority?city=Pune", headers=auth_headers
    )
    data = resp.json()["data"]
    nigdi = next(s for s in data["scores"] if s["station_code"] == "PUNE_LIVE_NIGDI")
    assert nigdi["traffic_level"] is None
    assert nigdi["is_traffic_data_configured"] is False
    assert nigdi["green_cover_pct"] is None
    assert nigdi["is_green_cover_configured"] is False
    assert nigdi["exposure_level"] == "unavailable"
    assert any("traffic data is unavailable" in r.lower() for r in nigdi["rationale"])


@pytest.mark.asyncio
async def test_non_pune_city_returns_no_fabricated_scores(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get(
        "/api/v1/green-infrastructure/priority?city=Mumbai", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["scores"] == []
    assert len(data["unavailable_stations"]) == 6
