"""Unit tests for app.services.energy_provider. No DB dependency."""

import tempfile
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.config import settings
from app.services.energy_provider import (
    EnergyDataSource,
    _demo_grid_carbon_intensity,
    get_grid_carbon_intensity,
)


def _reset_csv_cache():
    import app.services.energy_provider as mod

    mod._csv_cache = None
    mod._csv_cache_path = None


def _reset_settings(provider, api_key, base_url, csv_path):
    settings.ENERGY_PROVIDER = provider
    settings.ENERGY_API_KEY = api_key
    settings.ENERGY_BASE_URL = base_url
    settings.ENERGY_CSV_PATH = csv_path


@pytest.fixture(autouse=True)
def _restore_settings():
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
    _reset_csv_cache()


def test_demo_evening_peak_is_dirtier_than_night():
    evening = _demo_grid_carbon_intensity(datetime(2026, 1, 1, 19, 0))
    night = _demo_grid_carbon_intensity(datetime(2026, 1, 1, 3, 0))
    assert evening > night


@pytest.mark.asyncio
async def test_live_mode_without_api_key_is_unavailable_not_fabricated():
    _reset_settings("live", "", "https://api.electricitymap.org/v3", "")
    reading = await get_grid_carbon_intensity(18.52, 73.85, city="Pune")
    assert reading.source == EnergyDataSource.UNAVAILABLE
    assert reading.value is None
    assert "not" in reading.note.lower() or "unavailable" in reading.note.lower()


@pytest.mark.asyncio
async def test_live_mode_success_is_labeled_live():
    _reset_settings("live", "test-token", "https://api.electricitymap.org/v3", "")

    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {
        "carbonIntensity": 612.4,
        "datetime": "2026-08-25T04:15:00.000Z",
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        reading = await get_grid_carbon_intensity(18.52, 73.85, city="Pune")

    assert reading.source == EnergyDataSource.LIVE
    assert reading.value == 612.4
    assert reading.provider == "Electricity Maps"
    assert reading.observed_at == datetime(2026, 8, 25, 4, 15, tzinfo=UTC)


@pytest.mark.asyncio
async def test_live_mode_never_labeled_live_on_provider_failure():
    _reset_settings("live", "test-token", "https://api.electricitymap.org/v3", "")

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("boom"))
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        reading = await get_grid_carbon_intensity(18.52, 73.85, city="Pune")

    assert reading.source == EnergyDataSource.UNAVAILABLE
    assert reading.value is None


@pytest.mark.asyncio
async def test_auto_mode_falls_back_to_csv_when_live_unconfigured():
    _reset_csv_cache()
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    ) as f:
        f.write("city,timestamp,gco2_per_kwh\nPune,2026-08-24T10:00:00+00:00,701.2\n")
        path = f.name

    _reset_settings("auto", "", "https://api.electricitymap.org/v3", path)
    _reset_csv_cache()
    reading = await get_grid_carbon_intensity(18.52, 73.85, city="Pune")

    assert reading.source == EnergyDataSource.CSV
    assert reading.value == 701.2
    assert "not real-time" in reading.note.lower()


@pytest.mark.asyncio
async def test_csv_mode_no_match_is_unavailable_not_fabricated():
    _reset_csv_cache()
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    ) as f:
        f.write("city,timestamp,gco2_per_kwh\nDelhi,2026-08-24T10:00:00+00:00,701.2\n")
        path = f.name

    _reset_settings("csv", "", "", path)
    _reset_csv_cache()
    reading = await get_grid_carbon_intensity(18.52, 73.85, city="Pune")

    assert reading.source == EnergyDataSource.UNAVAILABLE
    assert reading.value is None


@pytest.mark.asyncio
async def test_demo_mode_is_explicitly_labeled_demo():
    _reset_settings("demo", "", "", "")
    reading = await get_grid_carbon_intensity(18.52, 73.85, city="Pune")
    assert reading.source == EnergyDataSource.DEMO
    assert reading.value is not None
    assert "not a real measurement" in reading.note.lower()


@pytest.mark.asyncio
async def test_unconfigured_mode_is_unavailable():
    _reset_settings("unknown_mode", "", "", "")
    reading = await get_grid_carbon_intensity(18.52, 73.85, city="Pune")
    assert reading.source == EnergyDataSource.UNAVAILABLE
    assert reading.value is None
