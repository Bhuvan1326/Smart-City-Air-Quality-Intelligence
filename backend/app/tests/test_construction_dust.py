"""Tests for app.services.construction_dust (no DB) and for the
GET /sources/construction-dust-risk endpoint (DB-backed, marked
`integration`).

The endpoint tests exist because the unit tests above never touch the
database and so never would have caught the real production bug: the
`EmissionSource.extra_data` column was mapped to a column name that
didn't exist in the Alembic-migrated schema (the migration named it
"metadata"), so every `select(EmissionSource)` — including this
endpoint's query — raised `UndefinedColumnError` and surfaced to the
frontend as "Couldn't load construction/dust site data." See
app/models/emission_source.py for the fix (an explicit column-name
override) and ARCHITECTURE.md / the fix changelog for details.
"""

from datetime import UTC, datetime

import pytest
from geoalchemy2.elements import WKTElement
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.emission_source import EmissionSource, EmissionSourceType, PermitStatus
from app.models.monitoring import AQIReading, MonitoringStation
from app.services.construction_dust import DustRiskLevel, assess_construction_dust_risk


def test_low_pm10_and_valid_permit_gives_low_risk():
    result = assess_construction_dust_risk(
        source_name="Wakad Metro Construction",
        source_type="construction",
        ward_id="W06",
        permit_status="valid",
        violation_count=0,
        nearest_station_name="Wakad Station",
        nearest_station_distance_km=0.8,
        pm10=40,
    )
    assert result.risk_level == DustRiskLevel.LOW


def test_elevated_pm10_flags_as_supporting_observation():
    result = assess_construction_dust_risk(
        source_name="Site A",
        source_type="construction",
        ward_id="W06",
        permit_status="valid",
        violation_count=0,
        nearest_station_name="Station A",
        nearest_station_distance_km=1.0,
        pm10=180,
    )
    assert result.risk_level == DustRiskLevel.HIGH
    assert any("Elevated PM10" in o for o in result.supporting_observations)


def test_never_claims_confirmed_source():
    result = assess_construction_dust_risk(
        source_name="Site B",
        source_type="construction",
        ward_id="W06",
        permit_status="none",
        violation_count=5,
        nearest_station_name="Station B",
        nearest_station_distance_km=0.5,
        pm10=200,
    )
    assert result.requires_verification is True
    assert all("confirmed" not in o.lower() for o in result.supporting_observations)


def test_multiple_weak_signals_escalate_moderate_to_high():
    result = assess_construction_dust_risk(
        source_name="Site C",
        source_type="construction",
        ward_id="W06",
        permit_status="expired",
        violation_count=2,
        nearest_station_name="Station C",
        nearest_station_distance_km=1.0,
        pm10=90,  # moderate band
        construction_attribution_pct=35,
    )
    assert result.risk_level == DustRiskLevel.HIGH


def test_no_pm10_data_does_not_crash_or_fabricate():
    result = assess_construction_dust_risk(
        source_name="Site D",
        source_type="dust",
        ward_id=None,
        permit_status="valid",
        violation_count=0,
        nearest_station_name=None,
        nearest_station_distance_km=None,
        pm10=None,
    )
    assert result.pm10 is None
    assert result.risk_level == DustRiskLevel.LOW
    assert any("no recent pm10" in o.lower() for o in result.supporting_observations)


def test_far_station_flagged_as_caveat():
    result = assess_construction_dust_risk(
        source_name="Site E",
        source_type="construction",
        ward_id="W06",
        permit_status="valid",
        violation_count=0,
        nearest_station_name="Far Station",
        nearest_station_distance_km=5.5,
        pm10=60,
    )
    assert any("km away" in o for o in result.supporting_observations)


# ─── Endpoint / DB integration tests ──────────────────────────────────────
#
# These exercise the real ORM query path (the thing that was actually
# broken), not just the pure risk-assessment function above.


async def _make_source(
    db_session: AsyncSession,
    *,
    name: str,
    source_type: EmissionSourceType,
    city: str = "Pune",
    ward_id: str | None = "W02",
    lat: float = 18.535,
    lon: float = 73.851,
    is_active: bool = True,
    is_deleted: bool = False,
    permit_status: PermitStatus = PermitStatus.VALID,
    violation_count: int = 0,
) -> EmissionSource:
    source = EmissionSource(
        name=name,
        source_type=source_type,
        city=city,
        ward_id=ward_id,
        latitude=lat,
        longitude=lon,
        geometry=WKTElement(f"POINT({lon} {lat})", srid=4326),
        permit_status=permit_status,
        violation_count=violation_count,
        is_active=is_active,
        is_deleted=is_deleted,
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


async def _make_station_with_reading(
    db_session: AsyncSession,
    *,
    city: str = "Pune",
    lat: float = 18.535,
    lon: float = 73.851,
    pm10: float = 180.0,
) -> MonitoringStation:
    station = MonitoringStation(
        name="Test Station",
        station_code=f"TEST-{lat}-{lon}",
        city=city,
        latitude=lat,
        longitude=lon,
        geometry=WKTElement(f"POINT({lon} {lat})", srid=4326),
        operator="Test Operator",
        is_active=True,
    )
    db_session.add(station)
    await db_session.commit()
    await db_session.refresh(station)

    reading = AQIReading(
        station_id=station.id,
        pm10=pm10,
        pm25=pm10 * 0.6,
        aqi=150,
        timestamp=datetime.now(UTC),
        latitude=lat,
        longitude=lon,
    )
    db_session.add(reading)
    await db_session.commit()

    return station


@pytest.mark.asyncio
async def test_endpoint_requires_authentication(client: AsyncClient):
    resp = await client.get("/api/v1/sources/construction-dust-risk?city=Pune")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_endpoint_returns_real_db_backed_sites(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """Regression test for the extra_data/metadata column-name bug: this
    query previously raised UndefinedColumnError on any real Postgres
    connection because it selects every mapped column of EmissionSource."""
    await _make_source(
        db_session,
        name="Test Construction Site",
        source_type=EmissionSourceType.CONSTRUCTION,
        violation_count=1,
        permit_status=PermitStatus.EXPIRED,
    )
    await _make_station_with_reading(db_session, pm10=180.0)

    resp = await client.get(
        "/api/v1/sources/construction-dust-risk?city=Pune", headers=auth_headers
    )

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["city"] == "Pune"
    assert len(body["sites"]) == 1
    site = body["sites"][0]
    assert site["source_name"] == "Test Construction Site"
    assert site["pm10"] == pytest.approx(180.0)
    assert site["risk_level"] == "high"
    assert site["requires_verification"] is True


@pytest.mark.asyncio
async def test_endpoint_city_filtering(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    await _make_source(
        db_session,
        name="Pune Site",
        source_type=EmissionSourceType.CONSTRUCTION,
        city="Pune",
    )
    await _make_source(
        db_session,
        name="Mumbai Site",
        source_type=EmissionSourceType.DUST,
        city="Mumbai",
        lat=19.076,
        lon=72.877,
    )

    resp = await client.get(
        "/api/v1/sources/construction-dust-risk?city=Mumbai", headers=auth_headers
    )

    assert resp.status_code == 200
    sites = resp.json()["data"]["sites"]
    assert len(sites) == 1
    assert sites[0]["source_name"] == "Mumbai Site"


@pytest.mark.asyncio
async def test_endpoint_excludes_inactive_and_deleted_sources(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    await _make_source(
        db_session,
        name="Inactive Site",
        source_type=EmissionSourceType.CONSTRUCTION,
        is_active=False,
    )
    await _make_source(
        db_session,
        name="Deleted Site",
        source_type=EmissionSourceType.CONSTRUCTION,
        is_deleted=True,
    )
    await _make_source(
        db_session,
        name="Other Type Site",
        source_type=EmissionSourceType.INDUSTRIAL,
    )

    resp = await client.get(
        "/api/v1/sources/construction-dust-risk?city=Pune", headers=auth_headers
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["sites"] == []


@pytest.mark.asyncio
async def test_endpoint_honest_empty_state_for_city_with_no_sources(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """No sites for a city must return an honest empty list, never
    fabricated data."""
    resp = await client.get(
        "/api/v1/sources/construction-dust-risk?city=Nagpur", headers=auth_headers
    )

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["sites"] == []
    assert body["city"] == "Nagpur"


@pytest.mark.asyncio
async def test_endpoint_defaults_city_to_pune(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    await _make_source(
        db_session,
        name="Default City Site",
        source_type=EmissionSourceType.CONSTRUCTION,
    )

    resp = await client.get(
        "/api/v1/sources/construction-dust-risk", headers=auth_headers
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["city"] == "Pune"
    assert len(resp.json()["data"]["sites"]) == 1


@pytest.mark.asyncio
async def test_endpoint_coordinates_pass_through_unmodified(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    await _make_source(
        db_session,
        name="Coordinate Check Site",
        source_type=EmissionSourceType.DUST,
        lat=18.5074,
        lon=73.8077,
    )

    resp = await client.get(
        "/api/v1/sources/construction-dust-risk?city=Pune", headers=auth_headers
    )

    site = resp.json()["data"]["sites"][0]
    assert site["latitude"] == pytest.approx(18.5074)
    assert site["longitude"] == pytest.approx(73.8077)
