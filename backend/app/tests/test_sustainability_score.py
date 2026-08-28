"""Tests for app.services.sustainability_score. DB-backed (auto-marked
integration via the db_session fixture) since the service aggregates
real repository/model queries rather than being a pure function.
"""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.civic_issue import CivicIssue, CivicIssueStatus
from app.models.demographics import WardDemographics
from app.models.monitoring import AQIReading, MonitoringStation, QualityFlag
from app.models.water_resource import CityWaterResource
from app.services.sustainability_score import compute_city_sustainability_score


async def _create_station_with_reading(
    session: AsyncSession, city: str, code: str, aqi: int
) -> None:
    from geoalchemy2.elements import WKTElement

    station = MonitoringStation(
        name=f"Station {code}",
        station_code=code,
        city=city,
        ward_id="W01",
        operator="MPCB",
        latitude=18.52,
        longitude=73.85,
        geometry=WKTElement("POINT(73.85 18.52)", srid=4326),
        is_active=True,
    )
    session.add(station)
    await session.flush()
    session.add(
        AQIReading(
            station_id=station.id,
            aqi=aqi,
            pm25=aqi * 0.6,
            pm10=aqi * 0.8,
            timestamp=datetime.now(UTC),
            latitude=18.52,
            longitude=73.85,
            quality_flag=QualityFlag.GOOD,
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_no_data_at_all_reports_unavailable_everywhere(db_session: AsyncSession):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("no network"))
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        result = await compute_city_sustainability_score(db_session, "NoDataCityXYZ")

    assert result.overall_score is None
    assert result.indicators_available == 0
    assert result.indicators_total == 9
    assert all(c.score is None for c in result.components)
    assert all(c.classification == "UNAVAILABLE" for c in result.components)


@pytest.mark.asyncio
async def test_partial_data_yields_partial_score(db_session: AsyncSession):
    city = "PartialDataCity"
    await _create_station_with_reading(db_session, city, "SUS-001", 80)
    db_session.add(
        WardDemographics(
            city=city,
            ward_id="W01",
            population=100_000,
            green_cover_pct=22.0,
        )
    )
    await db_session.commit()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("no network"))
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        result = await compute_city_sustainability_score(db_session, city)

    aqi_component = next(c for c in result.components if c.name == "air_quality")
    assert aqi_component.score is not None
    assert aqi_component.classification == "CALCULATED"

    green_component = next(
        c for c in result.components if c.name == "green_infrastructure"
    )
    assert green_component.score == 22.0

    water_component = next(c for c in result.components if c.name == "water")
    assert water_component.score is None
    assert water_component.classification == "UNAVAILABLE"

    mobility_component = next(c for c in result.components if c.name == "mobility")
    assert mobility_component.score is None

    assert result.overall_score is not None
    assert 0 < result.indicators_available < result.indicators_total


@pytest.mark.asyncio
async def test_water_component_uses_reservoir_level_directly(db_session: AsyncSession):
    city = "WaterOnlyCity"
    db_session.add(
        CityWaterResource(
            city=city,
            reservoir_level_pct=64.0,
            data_as_of=date(2026, 6, 1),
            source_note="Test bulletin",
        )
    )
    await db_session.commit()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("no network"))
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        result = await compute_city_sustainability_score(db_session, city)

    water_component = next(c for c in result.components if c.name == "water")
    assert water_component.score == 64.0
    assert water_component.classification == "OBSERVED"


@pytest.mark.asyncio
async def test_civic_component_reflects_resolution_rate(
    db_session: AsyncSession, test_admin
):
    city = "CivicScoreCity"
    for i, status in enumerate(
        [CivicIssueStatus.RESOLVED, CivicIssueStatus.CLOSED, CivicIssueStatus.SUBMITTED]
    ):
        db_session.add(
            CivicIssue(
                reporter_id=test_admin.id,
                city=city,
                ward_id="W01",
                ward_assignment_method="unavailable",
                latitude=18.5,
                longitude=73.8,
                issue_type="pothole",
                classification_source="citizen_reported",
                severity="moderate",
                status=status.value,
                sla_hours=72.0,
                sla_deadline=datetime.now(UTC),
                is_overdue=False,
            )
        )
    await db_session.commit()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("no network"))
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        result = await compute_city_sustainability_score(db_session, city)

    civic_component = next(
        c for c in result.components if c.name == "civic_performance"
    )
    assert civic_component.score == pytest.approx(66.7, abs=0.1)
