"""Unit tests for app.services.industrial_pollution (no DB) and for the
GET /sources/industrial-risk endpoint (DB-backed, marked `integration`).

The endpoint tests exist because the unit tests below never touch a real
database and so would never catch a real ORM/column-mapping regression
(the same class of bug construction_dust.py's endpoint tests document for
EmissionSource.extra_data) or verify that the frontend-facing response
actually carries the measured pm25/pm10/no2 and attribution data the
service computes.
"""

from datetime import UTC, datetime, timedelta

import pytest
from geoalchemy2.elements import WKTElement
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import PollutionAttribution
from app.models.emission_source import EmissionSource, EmissionSourceType, PermitStatus
from app.models.monitoring import AQIReading, MonitoringStation
from app.services.industrial_pollution import DeviationLevel, assess_industrial_zone


def test_no_deviation_when_current_matches_baseline():
    result = assess_industrial_zone(
        source_name="Site A",
        ward_id="W08",
        permit_status="valid",
        violation_count=0,
        current_aqi=100,
        historical_baseline_aqi=95,
    )
    assert result.deviation_level == DeviationLevel.NORMAL
    assert result.status == "normal"


def test_significant_deviation_flagged():
    result = assess_industrial_zone(
        source_name="Yerawada Brick Kiln",
        ward_id="W08",
        permit_status="suspended",
        violation_count=7,
        current_aqi=250,
        historical_baseline_aqi=100,
    )
    assert result.deviation_level == DeviationLevel.SIGNIFICANT
    assert result.status == "environmental_anomaly_detected"


def test_never_confirms_source_only_possible():
    result = assess_industrial_zone(
        source_name="Site B",
        ward_id="W08",
        permit_status="suspended",
        violation_count=5,
        current_aqi=280,
        historical_baseline_aqi=100,
    )
    assert result.possible_contributing_source is True
    assert all("confirmed" not in o.lower() for o in result.supporting_observations)


def test_deviation_without_regulatory_signal_not_flagged_as_source():
    # Elevated AQI relative to baseline, but the site is fully compliant and
    # attribution isn't elevated — should NOT flag as a possible contributing source.
    result = assess_industrial_zone(
        source_name="Compliant Site",
        ward_id="W08",
        permit_status="valid",
        violation_count=0,
        current_aqi=200,
        historical_baseline_aqi=100,
    )
    assert result.deviation_level != DeviationLevel.NORMAL
    assert result.possible_contributing_source is False


def test_no_baseline_data_does_not_crash():
    result = assess_industrial_zone(
        source_name="Site C",
        ward_id=None,
        permit_status="valid",
        violation_count=0,
        current_aqi=120,
        historical_baseline_aqi=None,
    )
    assert result.deviation_level == DeviationLevel.NORMAL
    assert any(
        "no historical baseline" in o.lower() for o in result.supporting_observations
    )


def test_attribution_alone_can_trigger_contributing_source_flag():
    result = assess_industrial_zone(
        source_name="Site D",
        ward_id="W08",
        permit_status="valid",
        violation_count=0,
        current_aqi=200,
        historical_baseline_aqi=100,
        industrial_attribution_pct=45,
    )
    assert result.possible_contributing_source is True


# ─── Endpoint / DB integration tests ──────────────────────────────────────
#
# These exercise the real ORM query path and the full response shape, not
# just the pure risk-assessment function above.


async def _make_source(
    db_session: AsyncSession,
    *,
    name: str,
    source_type: EmissionSourceType = EmissionSourceType.INDUSTRIAL,
    city: str = "Pune",
    ward_id: str | None = "W04",
    lat: float = 18.6298,
    lon: float = 73.7997,
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
    lat: float = 18.6298,
    lon: float = 73.7997,
    aqi: int = 250,
    pm25: float = 140.0,
    pm10: float = 210.0,
    no2: float = 55.0,
    station_code: str | None = None,
) -> MonitoringStation:
    # For Pune, this must be one of the six authoritative PUNE_LIVE_* codes
    # (see app.services.pune_current_aqi.get_pune_live_stations) -- the
    # endpoint now only considers those as "nearest station" candidates for
    # Pune, so an arbitrary TEST-IND-* code would silently be excluded
    # (requirement 1/7). Non-Pune cities are unaffected.
    if station_code is None:
        station_code = "PUNE_LIVE_SPPU" if city == "Pune" else f"TEST-IND-{lat}-{lon}"
    station = MonitoringStation(
        name="Test Industrial Station",
        station_code=station_code,
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
        aqi=aqi,
        pm25=pm25,
        pm10=pm10,
        no2=no2,
        timestamp=datetime.now(UTC),
        latitude=lat,
        longitude=lon,
    )
    db_session.add(reading)

    # Baseline window: readings 2h-3d old, averaging to a lower AQI so the
    # endpoint's baseline SQL and the deviation math both have real data
    # to work with instead of falling back to "no baseline available".
    for hours_ago, baseline_aqi in ((6, 100), (30, 110), (54, 90)):
        db_session.add(
            AQIReading(
                station_id=station.id,
                aqi=baseline_aqi,
                pm25=baseline_aqi * 0.5,
                pm10=baseline_aqi * 0.8,
                no2=30.0,
                timestamp=datetime.now(UTC) - timedelta(hours=hours_ago),
                latitude=lat,
                longitude=lon,
            )
        )
    await db_session.commit()

    return station


async def _make_attribution(
    db_session: AsyncSession,
    *,
    ward_id: str = "W04",
    city: str = "Pune",
    industrial_pct: float = 42.0,
    confidence: float = 0.8,
) -> PollutionAttribution:
    attribution = PollutionAttribution(
        ward_id=ward_id,
        city=city,
        timestamp=datetime.now(UTC),
        vehicular_pct=20.0,
        industrial_pct=industrial_pct,
        construction_pct=10.0,
        biomass_pct=8.0,
        secondary_aerosol_pct=10.0,
        dust_pct=5.0,
        domestic_pct=100.0 - (20.0 + industrial_pct + 10.0 + 8.0 + 10.0 + 5.0),
        overall_confidence=confidence,
        model_version="test-v1",
    )
    db_session.add(attribution)
    await db_session.commit()
    return attribution


@pytest.mark.asyncio
async def test_endpoint_requires_authentication(client: AsyncClient):
    resp = await client.get("/api/v1/sources/industrial-risk?city=Pune")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_endpoint_returns_real_db_backed_zones_with_full_field_set(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """Regression test for the ORM query path (same class of bug
    construction_dust.py's endpoint tests document for
    EmissionSource.extra_data) and for the pm25/pm10/no2/attribution
    fields, which the service already computed but the endpoint
    previously discarded instead of returning to the frontend."""
    await _make_source(
        db_session,
        name="Pimpri Test Cluster",
        violation_count=2,
        permit_status=PermitStatus.EXPIRED,
    )
    await _make_station_with_reading(db_session)
    await _make_attribution(db_session, industrial_pct=42.0, confidence=0.8)

    resp = await client.get(
        "/api/v1/sources/industrial-risk?city=Pune", headers=auth_headers
    )

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["city"] == "Pune"
    assert len(body["zones"]) == 1
    zone = body["zones"][0]
    assert zone["source_name"] == "Pimpri Test Cluster"
    assert zone["current_aqi"] == 250
    assert zone["pm25"] == pytest.approx(140.0)
    assert zone["pm10"] == pytest.approx(210.0)
    assert zone["no2"] == pytest.approx(55.0)
    assert zone["industrial_attribution_pct"] == pytest.approx(42.0)
    assert zone["attribution_confidence"] == pytest.approx(0.8)
    assert zone["nearest_station_name"] == "Test Industrial Station"
    assert zone["nearest_station_distance_km"] == pytest.approx(0.0, abs=0.1)
    assert zone["status"] == "environmental_anomaly_detected"
    assert zone["possible_contributing_source"] is True
    # Never a confirmed-source claim, only ever "possible".
    assert all("confirmed" not in o.lower() for o in zone["supporting_observations"])


@pytest.mark.asyncio
async def test_endpoint_city_filtering(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    await _make_source(db_session, name="Pune Facility", city="Pune")
    await _make_source(
        db_session, name="Mumbai Facility", city="Mumbai", lat=19.076, lon=72.877
    )

    resp = await client.get(
        "/api/v1/sources/industrial-risk?city=Mumbai", headers=auth_headers
    )

    assert resp.status_code == 200
    zones = resp.json()["data"]["zones"]
    assert len(zones) == 1
    assert zones[0]["source_name"] == "Mumbai Facility"


@pytest.mark.asyncio
async def test_endpoint_excludes_inactive_deleted_and_other_source_types(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    await _make_source(db_session, name="Inactive Facility", is_active=False)
    await _make_source(db_session, name="Deleted Facility", is_deleted=True)
    await _make_source(
        db_session,
        name="Construction Site, Not Industrial",
        source_type=EmissionSourceType.CONSTRUCTION,
    )

    resp = await client.get(
        "/api/v1/sources/industrial-risk?city=Pune", headers=auth_headers
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["zones"] == []


@pytest.mark.asyncio
async def test_endpoint_honest_empty_state_for_city_with_no_sources(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    resp = await client.get(
        "/api/v1/sources/industrial-risk?city=Nagpur", headers=auth_headers
    )

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["zones"] == []
    assert body["city"] == "Nagpur"
    assert body["disclaimer"]


@pytest.mark.asyncio
async def test_endpoint_defaults_city_to_pune(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    await _make_source(db_session, name="Default City Facility")

    resp = await client.get("/api/v1/sources/industrial-risk", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["data"]["city"] == "Pune"
    assert len(resp.json()["data"]["zones"]) == 1


@pytest.mark.asyncio
async def test_endpoint_handles_missing_station_and_attribution_gracefully(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """No monitoring station and no attribution snapshot nearby must not
    crash the endpoint — every derived field should just come back null."""
    await _make_source(db_session, name="No Station Nearby", ward_id="W99")

    resp = await client.get(
        "/api/v1/sources/industrial-risk?city=Pune", headers=auth_headers
    )

    assert resp.status_code == 200
    zone = resp.json()["data"]["zones"][0]
    assert zone["current_aqi"] is None
    assert zone["pm25"] is None
    assert zone["industrial_attribution_pct"] is None
    assert zone["status"] == "normal"
    assert zone["possible_contributing_source"] is False


@pytest.mark.asyncio
async def test_endpoint_coordinates_and_percentages_pass_through_unmodified(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """Guards against the '40% becomes 4000%' class of bug: the raw
    percentage stored on PollutionAttribution must reach the response
    unchanged, not re-scaled or multiplied."""
    await _make_source(
        db_session, name="Coordinate Check Facility", lat=18.5074, lon=73.8077
    )
    await _make_attribution(db_session, industrial_pct=33.3, confidence=0.65)

    resp = await client.get(
        "/api/v1/sources/industrial-risk?city=Pune", headers=auth_headers
    )

    zone = resp.json()["data"]["zones"][0]
    assert zone["latitude"] == pytest.approx(18.5074)
    assert zone["longitude"] == pytest.approx(73.8077)
    assert 0 <= zone["industrial_attribution_pct"] <= 100
    assert zone["industrial_attribution_pct"] == pytest.approx(33.3)


@pytest.mark.asyncio
async def test_endpoint_ignores_legacy_ward_fixture_station_for_pune(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """Regression test for requirement 1/7: a legacy PUNE_00X-style
    station right next to a Pune industrial zone must NOT be used as its
    "nearest station" -- only the six authoritative PUNE_LIVE_* stations
    are eligible for Pune."""
    await _make_source(db_session, name="Legacy Fixture Adjacent Facility")
    await _make_station_with_reading(db_session, aqi=300, station_code="PUNE_003")

    resp = await client.get(
        "/api/v1/sources/industrial-risk?city=Pune", headers=auth_headers
    )

    assert resp.status_code == 200
    zone = resp.json()["data"]["zones"][0]
    assert zone["current_aqi"] is None
    assert zone["nearest_station_name"] is None


@pytest.mark.asyncio
async def test_endpoint_non_pune_city_still_uses_any_active_station(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """Cities other than Pune have no legacy/live station split, so any
    active station should still be usable as the nearest station."""
    await _make_source(
        db_session, name="Mumbai Facility", city="Mumbai", lat=19.076, lon=72.877
    )
    await _make_station_with_reading(
        db_session, city="Mumbai", lat=19.076, lon=72.877, aqi=180
    )

    resp = await client.get(
        "/api/v1/sources/industrial-risk?city=Mumbai", headers=auth_headers
    )

    assert resp.status_code == 200
    zone = resp.json()["data"]["zones"][0]
    assert zone["current_aqi"] == 180
