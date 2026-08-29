"""Unit tests for app.services.weather_provider. No DB dependency."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.weather_provider import get_current_weather


@pytest.mark.asyncio
async def test_live_weather_success_parses_all_fields():
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {
        "current": {
            "time": "2026-08-25T04:15",
            "temperature_2m": 34.2,
            "relative_humidity_2m": 41.0,
            "apparent_temperature": 37.8,
            "precipitation": 0.0,
            "wind_speed_10m": 12.4,
        }
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        weather = await get_current_weather(18.52, 73.85)

    assert weather is not None
    assert weather.temperature_c == 34.2
    assert weather.apparent_temperature_c == 37.8
    assert weather.relative_humidity_pct == 41.0
    assert weather.wind_speed_kmh == 12.4
    assert weather.provider == "Open-Meteo"
    assert weather.observed_at == datetime(2026, 8, 25, 4, 15, tzinfo=UTC)


@pytest.mark.asyncio
async def test_weather_provider_failure_returns_none_never_fabricates():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("network down"))
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        weather = await get_current_weather(18.52, 73.85)

    assert weather is None


@pytest.mark.asyncio
async def test_weather_provider_non_200_returns_none():
    mock_response = MagicMock(status_code=500)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        weather = await get_current_weather(18.52, 73.85)

    assert weather is None


@pytest.mark.asyncio
async def test_weather_provider_missing_temperature_field_returns_none():
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {"current": {"time": "2026-08-25T04:15"}}
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        weather = await get_current_weather(18.52, 73.85)

    assert weather is None
