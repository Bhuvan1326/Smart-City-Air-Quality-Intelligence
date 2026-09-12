"""DB-backed tests for the GET /exposure/map endpoint.

Regression coverage for requirement 9: a seeded/demo `synthetic` reading
must never be presented as a ward's real current AQI in the Population
Exposure map (see app/api/v1/endpoints/exposure.py::get_exposure_map).
"""

from datetime import UTC, datetime

import pytest
from geoalchemy2.elements import WKTElement
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.demographics import WardDemographics
from app.models.monitoring import AQIReading, MonitoringStation


async def _make_station_with_reading(
    db_session: AsyncSession,
    *,
    station_code: str,
    ward_id: str,
    city: str = "Pune",
    lat: float = 18.52,
    lon: float = 73.85,
    aqi: int = 180,
    quality_flag: str = "good",
) -> MonitoringStation:
    station = MonitoringStation(
        name=f"Station {station_code}",
        station_code=station_code,
        city=city,
        ward_id=ward_id,
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
            aqi=aqi,
            pm25=aqi * 0.6,
            timestamp=datetime.now(UTC),
            latitude=lat,
            longitude=lon,
            quality_flag=quality_flag,
        )
    )
    await db_session.commit()
    return station


async def _make_demographics(
    db_session: AsyncSession, *, city: str = "Pune", ward_id: str
) -> WardDemographics:
    demo = WardDemographics(city=city, ward_id=ward_id, population=100_000)
    db_session.add(demo)
    await db_session.commit()
    return demo


@pytest.mark.asyncio
async def test_exposure_map_endpoint_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/exposure/map?city=Pune")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_exposure_map_uses_ward_station_reading(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    await _make_station_with_reading(
        db_session, station_code="PUNE_003", ward_id="W03", aqi=200
    )
    await _make_demographics(db_session, ward_id="W03")

    resp = await client.get("/api/v1/exposure/map?city=Pune", headers=auth_headers)

    assert resp.status_code == 200
    scores = resp.json()["data"]["scores"]
    assert len(scores) == 1
    assert scores[0]["ward_id"] == "W03"
    assert scores[0]["aqi"] == 200


@pytest.mark.asyncio
async def test_exposure_map_excludes_synthetic_reading(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """Regression test for requirement 9: a synthetic/demo reading must
    not be presented as this ward's current AQI. With no other station
    for the ward, it should be left unscored rather than backfilled with
    the synthetic value."""
    await _make_station_with_reading(
        db_session,
        station_code="PUNE_004",
        ward_id="W04",
        aqi=999,
        quality_flag="synthetic",
    )
    await _make_demographics(db_session, ward_id="W04")

    resp = await client.get("/api/v1/exposure/map?city=Pune", headers=auth_headers)

    assert resp.status_code == 200
    scores = resp.json()["data"]["scores"]
    assert all(s["ward_id"] != "W04" for s in scores)


@pytest.mark.asyncio
async def test_exposure_map_falls_back_to_real_reading_when_synthetic_present(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """When a ward has both a synthetic and a real reading (from two
    different stations), the real one must be used, not the synthetic
    one, regardless of query ordering."""
    await _make_station_with_reading(
        db_session,
        station_code="PUNE_005",
        ward_id="W05",
        aqi=999,
        quality_flag="synthetic",
        lat=18.50,
        lon=73.80,
    )
    await _make_station_with_reading(
        db_session,
        station_code="PUNE_006",
        ward_id="W05",
        aqi=150,
        quality_flag="good",
        lat=18.51,
        lon=73.81,
    )
    await _make_demographics(db_session, ward_id="W05")

    resp = await client.get("/api/v1/exposure/map?city=Pune", headers=auth_headers)

    assert resp.status_code == 200
    scores = [s for s in resp.json()["data"]["scores"] if s["ward_id"] == "W05"]
    assert len(scores) == 1
    assert scores[0]["aqi"] == 150
