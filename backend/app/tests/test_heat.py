from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_heat_current_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/heat/current?latitude=18.52&longitude=73.85")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_heat_current_unavailable_when_weather_fails(
    client: AsyncClient, auth_headers: dict
):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("boom"))
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        resp = await client.get(
            "/api/v1/heat/current?latitude=18.52&longitude=73.85",
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["air_temperature_source_type"] == "unavailable"
    assert data["air_temperature_c"] is None
    assert data["heat_risk"] is None


@pytest.mark.asyncio
async def test_heat_current_live_success_includes_provenance(
    client: AsyncClient, auth_headers: dict
):
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {
        "current": {
            "time": "2026-08-25T12:00",
            "temperature_2m": 38.5,
            "relative_humidity_2m": 30.0,
            "apparent_temperature": 41.0,
            "precipitation": 0.0,
            "wind_speed_10m": 8.0,
        }
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        resp = await client.get(
            "/api/v1/heat/current?latitude=18.52&longitude=73.85",
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["air_temperature_source_type"] == "live"
    assert data["air_temperature_c"] == 38.5
    assert data["heat_risk"] == "high"
    assert data["vegetation_data_available"] is False
    assert data["mean_ndvi"] is None
