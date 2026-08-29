from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.water_resource import CityWaterResource


@pytest.mark.asyncio
async def test_sustainability_score_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/sustainability/score?city=Pune")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sustainability_score_defaults_to_pune(
    client: AsyncClient, auth_headers: dict
):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("no network"))
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        resp = await client.get(
            "/api/v1/sustainability/score", headers=auth_headers
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["city"] == "Pune"
    assert data["indicators_total"] == 9
    assert len(data["components"]) == 9
    mobility = next(c for c in data["components"] if c["name"] == "mobility")
    assert mobility["score"] is None
    assert mobility["classification"] == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_sustainability_score_reflects_on_record_city_data(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    city = "SustainabilityEndpointCity"
    db_session.add(
        CityWaterResource(
            city=city,
            reservoir_level_pct=40.0,
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
        resp = await client.get(
            f"/api/v1/sustainability/score?city={city}", headers=auth_headers
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    water = next(c for c in data["components"] if c["name"] == "water")
    assert water["score"] == 40.0
    assert water["classification"] == "OBSERVED"
    assert data["overall_score"] is not None
    assert 0 < data["indicators_available"] < data["indicators_total"]
