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


@pytest.mark.asyncio
async def test_heat_wards_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/heat/wards")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_heat_wards_returns_empty_for_non_pune_city(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get("/api/v1/heat/wards?city=Mumbai", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["city"] == "Mumbai"
    assert body["data"]["wards"] == []
    assert "only covers Pune" in body["message"]


@pytest.mark.asyncio
async def test_heat_wards_returns_all_wards_with_provenance(
    client: AsyncClient, auth_headers: dict
):
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {
        "current": {
            "time": "2026-08-25T12:00",
            "temperature_2m": 36.0,
            "relative_humidity_2m": 40.0,
            "apparent_temperature": 38.0,
            "precipitation": 0.0,
            "wind_speed_10m": 5.0,
        }
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with (
        patch("httpx.AsyncClient", return_value=mock_client_cm),
        patch(
            "app.services.satellite.sentinel_hub.SentinelHubClient.is_configured",
            new_callable=lambda: property(lambda self: False),
        ),
    ):
        resp = await client.get("/api/v1/heat/wards?city=Pune", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["city"] == "Pune"
    assert len(data["wards"]) == 8
    ward_ids = {w["ward_id"] for w in data["wards"]}
    assert ward_ids == {f"W0{i}" for i in range(1, 9)}
    for ward in data["wards"]:
        assert ward["air_temperature_source_type"] == "live"
        assert ward["air_temperature_c"] == 36.0
        assert ward["heat_risk"] == "high"
        assert ward["vegetation_data_available"] is False


@pytest.mark.asyncio
async def test_heat_wards_unavailable_when_weather_fails(
    client: AsyncClient, auth_headers: dict
):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("boom"))
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        resp = await client.get("/api/v1/heat/wards?city=Pune", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["wards"]) == 8
    for ward in data["wards"]:
        assert ward["air_temperature_source_type"] == "unavailable"
        assert ward["heat_risk"] is None
