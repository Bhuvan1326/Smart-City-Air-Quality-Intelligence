from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


def _make_weather_mock(temp: float = 36.0, rh: float = 30.0, apparent: float = 38.0):
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {
        "current": {
            "time": "2026-08-25T12:00",
            "temperature_2m": temp,
            "relative_humidity_2m": rh,
            "apparent_temperature": apparent,
            "precipitation": 0.0,
            "wind_speed_10m": 5.0,
        }
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_client
    mock_cm.__aexit__.return_value = False
    return mock_cm


def _make_fail_mock():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("boom"))
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_client
    mock_cm.__aexit__.return_value = False
    return mock_cm


# ─── /heat/current ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_heat_current_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/heat/current?latitude=18.52&longitude=73.85")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_heat_current_unavailable_when_weather_fails(
    client: AsyncClient, auth_headers: dict
):
    with patch("httpx.AsyncClient", return_value=_make_fail_mock()):
        resp = await client.get(
            "/api/v1/heat/current?latitude=18.52&longitude=73.85",
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["air_temperature_source_type"] == "unavailable"
    assert data["air_temperature_c"] is None
    assert data["heat_risk"] is None
    assert data["heat_index_c"] is None


@pytest.mark.asyncio
async def test_heat_current_live_includes_humidity_and_heat_index(
    client: AsyncClient, auth_headers: dict
):
    # RH=30 is below 40% so heat index should be None; risk is from air temp only
    with patch(
        "httpx.AsyncClient", return_value=_make_weather_mock(temp=38.5, rh=30.0)
    ):
        resp = await client.get(
            "/api/v1/heat/current?latitude=18.52&longitude=73.85",
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["air_temperature_source_type"] == "live"
    assert data["air_temperature_c"] == 38.5
    assert data["relative_humidity_pct"] == 30.0
    assert data["heat_index_c"] is None  # RH < 40% → not computed
    assert data["heat_index_used_for_risk"] is False
    assert data["heat_risk"] == "high"  # 38.5°C → high band
    assert data["vegetation_data_available"] is False


@pytest.mark.asyncio
async def test_heat_current_heat_index_used_when_high_humidity(
    client: AsyncClient, auth_headers: dict
):
    # RH=70, temp=36 → heat index ~42°C > 36 → risk escalates to severe
    with patch(
        "httpx.AsyncClient", return_value=_make_weather_mock(temp=36.0, rh=70.0)
    ):
        resp = await client.get(
            "/api/v1/heat/current?latitude=18.52&longitude=73.85",
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["heat_index_c"] is not None
    assert data["heat_index_used_for_risk"] is True
    assert data["heat_risk"] == "severe"


# ─── /heat/hourly ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_heat_hourly_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/heat/hourly?latitude=18.52&longitude=73.85")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_heat_hourly_returns_24_points(client: AsyncClient, auth_headers: dict):
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {
        "hourly": {
            "time": [f"2026-09-09T{h:02d}:00" for h in range(24)],
            "temperature_2m": [32.0 + h * 0.2 for h in range(24)],
            "apparent_temperature": [33.0 + h * 0.2 for h in range(24)],
            "relative_humidity_2m": [55.0] * 24,
        }
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_client
    mock_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_cm):
        resp = await client.get(
            "/api/v1/heat/hourly?latitude=18.52&longitude=73.85",
            headers=auth_headers,
        )

    assert resp.status_code == 200
    hours = resp.json()["data"]["hours"]
    assert len(hours) == 24
    for h in hours:
        assert "temperature_c" in h
        assert "heat_risk" in h
        assert h["heat_risk"] in ("low", "moderate", "high", "severe")


@pytest.mark.asyncio
async def test_heat_hourly_returns_empty_on_api_failure(
    client: AsyncClient, auth_headers: dict
):
    with patch("httpx.AsyncClient", return_value=_make_fail_mock()):
        resp = await client.get(
            "/api/v1/heat/hourly?latitude=18.52&longitude=73.85",
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json()["data"]["hours"] == []


# ─── /heat/forecast ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_heat_forecast_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/heat/forecast?latitude=18.52&longitude=73.85")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_heat_forecast_returns_7_days(client: AsyncClient, auth_headers: dict):
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {
        "daily": {
            "time": [f"2026-09-0{d}" for d in range(1, 8)],
            "temperature_2m_max": [36.0 + d for d in range(7)],
            "apparent_temperature_max": [38.0] * 7,
            "relative_humidity_2m_mean": [50.0] * 7,
            "precipitation_sum": [0.0] * 7,
        }
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_client
    mock_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_cm):
        resp = await client.get(
            "/api/v1/heat/forecast?latitude=18.52&longitude=73.85",
            headers=auth_headers,
        )

    assert resp.status_code == 200
    days = resp.json()["data"]["days"]
    assert len(days) == 7
    for d in days:
        assert "max_temperature_c" in d
        assert "heat_risk" in d


@pytest.mark.asyncio
async def test_heat_forecast_returns_empty_on_api_failure(
    client: AsyncClient, auth_headers: dict
):
    with patch("httpx.AsyncClient", return_value=_make_fail_mock()):
        resp = await client.get(
            "/api/v1/heat/forecast?latitude=18.52&longitude=73.85",
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json()["data"]["days"] == []


# ─── /heat/wards ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_heat_wards_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/heat/wards")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_heat_wards_returns_all_8_pune_wards(
    client: AsyncClient, auth_headers: dict
):
    with patch(
        "httpx.AsyncClient", return_value=_make_weather_mock(temp=36.0, rh=30.0)
    ):
        resp = await client.get("/api/v1/heat/wards", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["wards"]) == 8
    ward_ids = {w["ward_id"] for w in data["wards"]}
    assert ward_ids == {f"W0{i}" for i in range(1, 9)}
    for ward in data["wards"]:
        assert ward["temperature_c"] == 36.0
        assert ward["heat_risk"] == "high"
        assert "bbox" in ward
        assert len(ward["bbox"]) == 4


@pytest.mark.asyncio
async def test_heat_wards_unavailable_when_weather_fails(
    client: AsyncClient, auth_headers: dict
):
    with patch("httpx.AsyncClient", return_value=_make_fail_mock()):
        resp = await client.get("/api/v1/heat/wards", headers=auth_headers)

    assert resp.status_code == 200
    wards = resp.json()["data"]["wards"]
    assert len(wards) == 8
    for ward in wards:
        assert ward["temperature_c"] is None
        assert ward["heat_risk"] is None


# ─── /heat/history ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_heat_history_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/heat/history")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_heat_history_returns_empty_with_no_data(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get(
        "/api/v1/heat/history?city=Pune&days=30", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["city"] == "Pune"
    assert isinstance(data["points"], list)
