from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.core.config import settings


@pytest.fixture(autouse=True)
def _restore_energy_settings():
    original = (
        settings.ENERGY_PROVIDER,
        settings.ENERGY_API_KEY,
        settings.ENERGY_BASE_URL,
        settings.ENERGY_CSV_PATH,
    )
    yield
    (
        settings.ENERGY_PROVIDER,
        settings.ENERGY_API_KEY,
        settings.ENERGY_BASE_URL,
        settings.ENERGY_CSV_PATH,
    ) = original


@pytest.mark.asyncio
async def test_grid_carbon_intensity_requires_auth(client: AsyncClient):
    resp = await client.get(
        "/api/v1/energy/grid-carbon-intensity?latitude=18.52&longitude=73.85"
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_grid_carbon_intensity_unavailable_is_never_fabricated(
    client: AsyncClient, auth_headers: dict
):
    settings.ENERGY_PROVIDER = "live"
    settings.ENERGY_API_KEY = ""

    resp = await client.get(
        "/api/v1/energy/grid-carbon-intensity"
        "?latitude=18.52&longitude=73.85&city=Pune",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["source_type"] == "unavailable"
    assert data["value"] is None
    assert data["freshness_status"] == "unavailable"


@pytest.mark.asyncio
async def test_grid_carbon_intensity_live_success_includes_provenance(
    client: AsyncClient, auth_headers: dict
):
    settings.ENERGY_PROVIDER = "live"
    settings.ENERGY_API_KEY = "test-token"
    settings.ENERGY_BASE_URL = "https://api.electricitymap.org/v3"

    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {
        "carbonIntensity": 640.0,
        "datetime": "2026-08-25T04:15:00.000Z",
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        resp = await client.get(
            "/api/v1/energy/grid-carbon-intensity"
            "?latitude=18.52&longitude=73.85&city=Pune",
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["source_type"] == "live"
    assert data["provider"] == "Electricity Maps"
    assert data["value"] == 640.0
    assert data["unit"] == "gCO2eq/kWh"
    assert data["data_age_seconds"] is not None
