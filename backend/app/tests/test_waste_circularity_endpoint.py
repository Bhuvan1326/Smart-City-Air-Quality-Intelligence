from datetime import date

import pytest
from app.models.demographics import WardDemographics
from app.models.monitoring import MonitoringStation
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_station(session: AsyncSession, ward_id: str, code: str) -> None:
    from geoalchemy2.elements import WKTElement

    station = MonitoringStation(
        name=f"Station {code}",
        station_code=code,
        city="Pune",
        ward_id=ward_id,
        operator="MPCB",
        latitude=18.52,
        longitude=73.85,
        geometry=WKTElement("POINT(73.85 18.52)", srid=4326),
        is_active=True,
    )
    session.add(station)
    await session.flush()


@pytest.mark.asyncio
async def test_waste_circularity_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/waste/circularity?city=Pune")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_waste_circularity_reports_unavailable_when_no_data_on_file(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    await _create_station(db_session, "W01", "WASTE-W01")
    await db_session.commit()

    resp = await client.get("/api/v1/waste/circularity?city=Pune", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    ward = next(w for w in data["wards"] if w["ward_id"] == "W01")
    assert ward["circularity_score"] is None
    assert (
        ward["circularity_unavailable_reason"]
        == "Insufficient verified waste-flow data"
    )
    assert "W01" in data["wards_with_no_data_on_file"]


@pytest.mark.asyncio
async def test_waste_circularity_computes_score_from_admin_entered_data(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    await _create_station(db_session, "W02", "WASTE-W02")
    db_session.add(
        WardDemographics(
            city="Pune",
            ward_id="W02",
            waste_generation_tons_per_day=120.0,
            waste_collection_efficiency_pct=85.0,
            waste_recycling_pct=25.0,
            waste_composting_pct=15.0,
            waste_landfill_pct=55.0,
            waste_data_as_of=date(2026, 6, 1),
            source_note="PMC Solid Waste Management Annual Report 2026",
        )
    )
    await db_session.commit()

    resp = await client.get("/api/v1/waste/circularity?city=Pune", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    ward = next(w for w in data["wards"] if w["ward_id"] == "W02")
    assert ward["recovery_rate_pct"] == 40.0
    assert ward["circularity_score"] is not None
    assert ward["is_data_configured"] is True
    assert ward["freshness_label"] in (
        "latest_available",
        "latest_available_possibly_outdated",
    )
