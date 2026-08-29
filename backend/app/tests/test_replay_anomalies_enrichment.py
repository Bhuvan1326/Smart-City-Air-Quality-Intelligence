from datetime import UTC, datetime, timedelta

import pytest
from app.api.v1.endpoints.replay import _severity_from_spike
from app.models.analytics import AnomalyEvent
from app.models.monitoring import MonitoringStation
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.parametrize(
    "spike,expected",
    [
        (100, "moderate"),
        (150, "moderate"),
        (151, "high"),
        (200, "high"),
        (201, "severe"),
        (300, "severe"),
        (301, "critical"),
        (500, "critical"),
    ],
)
def test_severity_from_spike_thresholds(spike, expected):
    assert _severity_from_spike(spike) == expected


async def _create_station(session: AsyncSession, code: str = "ANOMALY_001"):
    from geoalchemy2.elements import WKTElement

    station = MonitoringStation(
        name="Anomaly Test Station",
        station_code=code,
        city="Pune",
        ward_id="W03",
        operator="MPCB",
        latitude=18.52,
        longitude=73.85,
        geometry=WKTElement("POINT(73.85 18.52)", srid=4326),
        is_active=True,
    )
    session.add(station)
    await session.flush()
    return station


async def _create_anomaly(
    session: AsyncSession,
    station: MonitoringStation,
    spike: int = 220,
    cause_category: str = "vehicular",
    is_resolved: bool = False,
):
    anomaly = AnomalyEvent(
        station_id=station.id,
        ward_id=station.ward_id,
        city=station.city,
        detected_at=datetime.now(UTC) - timedelta(hours=1),
        aqi_spike_value=spike,
        baseline_aqi=90,
        probable_cause="Heavy traffic congestion detected near arterial road",
        cause_category=cause_category,
        confidence_score=0.82,
        is_resolved=is_resolved,
    )
    session.add(anomaly)
    await session.flush()
    return anomaly


@pytest.mark.asyncio
async def test_anomalies_endpoint_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/replay/anomalies?city=Pune")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_anomalies_endpoint_enriches_with_severity_and_coordinates(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    station = await _create_station(db_session, "ANOMALY_ENRICH")
    await _create_anomaly(db_session, station, spike=220, cause_category="vehicular")
    await db_session.commit()

    resp = await client.get(
        "/api/v1/replay/anomalies?city=Pune&hours=48", headers=auth_headers
    )
    assert resp.status_code == 200
    events = resp.json()["data"]
    assert len(events) == 1
    event = events[0]
    assert event["severity"] == "severe"  # 220 -> severe band
    assert event["pollutant"] == "no2"  # vehicular -> no2
    assert event["observed_value"] == 220
    assert event["expected_value"] == 90
    assert event["anomaly_score"] == pytest.approx(0.82)
    assert event["detection_method"] == "statistical_zscore"
    assert event["latitude"] == pytest.approx(18.52)
    assert event["longitude"] == pytest.approx(73.85)


@pytest.mark.asyncio
async def test_anomalies_endpoint_filters_by_min_severity(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    station = await _create_station(db_session, "ANOMALY_SEV_FILTER")
    await _create_anomaly(db_session, station, spike=140)  # moderate
    await db_session.commit()

    resp = await client.get(
        "/api/v1/replay/anomalies?city=Pune&hours=48&min_severity=high",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_anomalies_endpoint_filters_by_pollutant(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    station = await _create_station(db_session, "ANOMALY_POLLUTANT_FILTER")
    await _create_anomaly(db_session, station, cause_category="industrial")
    await db_session.commit()

    matching = await client.get(
        "/api/v1/replay/anomalies?city=Pune&hours=48&pollutant=so2",
        headers=auth_headers,
    )
    assert len(matching.json()["data"]) == 1

    non_matching = await client.get(
        "/api/v1/replay/anomalies?city=Pune&hours=48&pollutant=o3",
        headers=auth_headers,
    )
    assert non_matching.json()["data"] == []


@pytest.mark.asyncio
async def test_anomalies_endpoint_filters_by_resolved_status(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    station = await _create_station(db_session, "ANOMALY_RESOLVED_FILTER")
    await _create_anomaly(db_session, station, is_resolved=True)
    await db_session.commit()

    unresolved_only = await client.get(
        "/api/v1/replay/anomalies?city=Pune&hours=48&resolved=false",
        headers=auth_headers,
    )
    assert unresolved_only.json()["data"] == []

    resolved_only = await client.get(
        "/api/v1/replay/anomalies?city=Pune&hours=48&resolved=true",
        headers=auth_headers,
    )
    assert len(resolved_only.json()["data"]) == 1
