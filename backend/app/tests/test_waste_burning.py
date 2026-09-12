"""Unit tests for app.services.waste_burning (no DB dependency), plus
DB-backed tests for the GET /waste-burning/events endpoint covering
requirement 1/7: Pune's per-station PM2.5 signal must come exclusively
from the six authoritative PUNE_LIVE_* stations, never the legacy
PUNE_001..PUNE_008 ward fixtures.
"""

from datetime import UTC, datetime, timedelta

import pytest
from geoalchemy2.elements import WKTElement
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import AQIReading, MonitoringStation
from app.services.waste_burning import WasteBurningConfidence, assess_waste_burning_risk


def test_no_signals_gives_none_confidence():
    result = assess_waste_burning_risk(ward_id="W07", current_pm25=30, baseline_pm25=28)
    assert result.confidence == WasteBurningConfidence.NONE
    assert result.circular_economy_recommendations == []


def test_pm25_spike_alone_gives_low_confidence():
    result = assess_waste_burning_risk(
        ward_id="W07", current_pm25=180, baseline_pm25=60
    )
    assert result.confidence == WasteBurningConfidence.LOW
    assert any("sudden pm2.5" in o.lower() for o in result.supporting_observations)


def test_multiple_signals_escalate_confidence():
    result = assess_waste_burning_risk(
        ward_id="W07",
        current_pm25=180,
        baseline_pm25=60,
        nearest_biomass_source_name="Kothrud Residential Burning",
        nearest_biomass_source_distance_km=0.9,
        biomass_attribution_pct=35,
    )
    assert result.confidence == WasteBurningConfidence.HIGH
    assert len(result.supporting_observations) >= 3


def test_status_always_requires_verification():
    result = assess_waste_burning_risk(
        ward_id="W07",
        current_pm25=200,
        baseline_pm25=50,
        satellite_hotspot_nearby=True,
        satellite_configured=True,
    )
    assert result.status == "requires_verification"
    assert "confirmed" not in result.detected.lower()


def test_unconfigured_satellite_labeled_unavailable_not_skipped():
    result = assess_waste_burning_risk(
        ward_id="W07",
        current_pm25=30,
        baseline_pm25=28,
        satellite_hotspot_nearby=False,
        satellite_configured=False,
    )
    assert any("unavailable" in o.lower() for o in result.supporting_observations)


def test_circular_economy_recommendations_present_when_flagged():
    result = assess_waste_burning_risk(
        ward_id="W07", current_pm25=180, baseline_pm25=60
    )
    assert len(result.circular_economy_recommendations) > 0
    assert any("compost" in r.lower() for r in result.circular_economy_recommendations)


def test_no_data_does_not_crash():
    result = assess_waste_burning_risk(
        ward_id=None, current_pm25=None, baseline_pm25=None
    )
    assert result.confidence == WasteBurningConfidence.NONE


# ─── Endpoint / DB integration tests ──────────────────────────────────────


async def _make_station_with_readings(
    db_session: AsyncSession,
    *,
    station_code: str,
    city: str = "Pune",
    lat: float = 18.55,
    lon: float = 73.85,
    current_pm25: float = 180.0,
    baseline_pm25: float = 60.0,
) -> MonitoringStation:
    station = MonitoringStation(
        name=f"Station {station_code}",
        station_code=station_code,
        city=city,
        latitude=lat,
        longitude=lon,
        geometry=WKTElement(f"POINT({lon} {lat})", srid=4326),
        operator="Test Operator",
        is_active=True,
    )
    db_session.add(station)
    await db_session.flush()

    db_session.add(
        AQIReading(
            station_id=station.id,
            pm25=current_pm25,
            aqi=150,
            timestamp=datetime.now(UTC) - timedelta(minutes=5),
            latitude=lat,
            longitude=lon,
            quality_flag="good",
        )
    )
    db_session.add(
        AQIReading(
            station_id=station.id,
            pm25=baseline_pm25,
            aqi=90,
            timestamp=datetime.now(UTC) - timedelta(hours=12),
            latitude=lat,
            longitude=lon,
            quality_flag="good",
        )
    )
    await db_session.commit()
    return station


@pytest.mark.asyncio
async def test_waste_burning_endpoint_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/waste-burning/events?city=Pune")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_waste_burning_endpoint_detects_pm25_spike_at_live_station(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    await _make_station_with_readings(db_session, station_code="PUNE_LIVE_SPPU")

    resp = await client.get(
        "/api/v1/waste-burning/events?city=Pune", headers=auth_headers
    )

    assert resp.status_code == 200
    events = resp.json()["data"]["events"]
    assert len(events) == 1
    assert events[0]["current_pm25"] == pytest.approx(180.0)
    assert events[0]["confidence"] != "none"


@pytest.mark.asyncio
async def test_waste_burning_endpoint_ignores_legacy_ward_fixture_station(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """Regression test for requirement 1/7: a legacy PUNE_00X-style
    station with an even bigger PM2.5 spike must NOT surface as a
    waste-burning event for Pune -- only the six authoritative
    PUNE_LIVE_* stations are eligible."""
    await _make_station_with_readings(
        db_session,
        station_code="PUNE_003",
        current_pm25=300.0,
        baseline_pm25=50.0,
    )

    resp = await client.get(
        "/api/v1/waste-burning/events?city=Pune", headers=auth_headers
    )

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["events"] == []


@pytest.mark.asyncio
async def test_waste_burning_endpoint_non_pune_city_still_uses_any_active_station(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """Cities other than Pune have no legacy/live station split, so any
    active station's PM2.5 spike should still surface."""
    await _make_station_with_readings(
        db_session,
        station_code="MUMBAI_001",
        city="Mumbai",
        lat=19.076,
        lon=72.877,
    )

    resp = await client.get(
        "/api/v1/waste-burning/events?city=Mumbai", headers=auth_headers
    )

    assert resp.status_code == 200
    events = resp.json()["data"]["events"]
    assert len(events) == 1
    assert events[0]["current_pm25"] == pytest.approx(180.0)
