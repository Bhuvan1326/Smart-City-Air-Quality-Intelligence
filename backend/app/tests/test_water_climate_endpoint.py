from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User, UserRole
from app.models.water_resource import CityWaterResource


@pytest.mark.asyncio
async def test_water_current_requires_auth(client: AsyncClient):
    resp = await client.get(
        "/api/v1/water/current?latitude=18.52&longitude=73.85&city=Pune"
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_water_current_unavailable_when_weather_fails_and_no_municipal_data(
    client: AsyncClient, auth_headers: dict
):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("boom"))
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        resp = await client.get(
            "/api/v1/water/current?latitude=18.52&longitude=73.85&city=NoDataCity",
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["weather_available"] is False
    assert data["municipal_data_available"] is False
    assert data["flood_conducive_risk"] is None
    assert data["drought_risk"] is None


@pytest.mark.asyncio
async def test_water_current_combines_live_weather_and_municipal_data(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    db_session.add(
        CityWaterResource(
            city="WaterTestCity",
            reservoir_level_pct=25.0,
            water_consumption_mld=450.0,
            groundwater_level_m=12.0,
            data_as_of=date(2026, 6, 1),
            source_note="Test municipal water board bulletin",
        )
    )
    await db_session.commit()

    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {
        "current": {
            "time": "2026-08-25T12:00",
            "temperature_2m": 29.0,
            "relative_humidity_2m": 70.0,
            "apparent_temperature": 31.0,
            "precipitation": 10.0,
            "wind_speed_10m": 5.0,
        }
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        resp = await client.get(
            "/api/v1/water/current?latitude=18.52&longitude=73.85&city=WaterTestCity",
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["weather_available"] is True
    assert data["precipitation_mm"] == 10.0
    assert data["flood_conducive_risk"] == "high"
    assert data["municipal_data_available"] is True
    assert data["reservoir_level_pct"] == 25.0
    assert data["drought_risk"] == "high"


@pytest.mark.asyncio
async def test_create_water_resource_requires_admin(
    client: AsyncClient, db_session: AsyncSession
):
    # auth_headers (from the test_admin fixture) is itself an admin, so
    # it can't be used to verify a 403 here — this test needs a
    # genuinely non-admin (CITIZEN) user to confirm RequireAdmin
    # actually rejects them.
    non_admin = User(
        email="non_admin_water_test@example.com",
        hashed_password=hash_password("NonAdmin@123"),
        full_name="Non Admin",
        role=UserRole.CITIZEN,
        city="Pune",
        is_active=True,
    )
    db_session.add(non_admin)
    await db_session.commit()

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "non_admin_water_test@example.com", "password": "NonAdmin@123"},
    )
    token = login_resp.json()["data"]["access_token"]
    non_admin_headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/water/resource",
        json={"city": "AdminTestCity", "reservoir_level_pct": 50.0},
        headers=non_admin_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_water_resource_allows_multiple_readings_per_city(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    """POST always inserts — multiple dated readings per city are allowed."""
    payload = {
        "city": "MultiReadCity",
        "reservoir_level_pct": 60.0,
        "data_as_of": "2026-08-01",
    }
    r1 = await client.post("/api/v1/water/resource", json=payload, headers=auth_headers)
    assert r1.status_code == 201

    payload2 = {
        "city": "MultiReadCity",
        "reservoir_level_pct": 45.0,
        "data_as_of": "2026-09-01",
    }
    r2 = await client.post(
        "/api/v1/water/resource", json=payload2, headers=auth_headers
    )
    assert r2.status_code == 201

    # Two distinct records should now exist for the same city.
    assert r1.json()["data"]["id"] != r2.json()["data"]["id"]


@pytest.mark.asyncio
async def test_get_water_resource_returns_latest_when_multiple_exist(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    """GET /resource returns the most-recent reading by data_as_of."""
    db_session.add(
        CityWaterResource(
            city="LatestCity",
            reservoir_level_pct=30.0,
            data_as_of=date(2026, 7, 1),
        )
    )
    db_session.add(
        CityWaterResource(
            city="LatestCity",
            reservoir_level_pct=55.0,
            data_as_of=date(2026, 9, 1),
        )
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/water/resource?city=LatestCity", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["reservoir_level_pct"] == 55.0


@pytest.mark.asyncio
async def test_water_history_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/water/history?city=Pune")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_water_history_returns_empty_list_for_unknown_city(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get(
        "/api/v1/water/history?city=NoSuchCity99", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_water_history_returns_readings_oldest_first(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    """History endpoint returns all records ordered oldest → newest."""
    db_session.add(
        CityWaterResource(
            city="HistoryCity",
            reservoir_level_pct=70.0,
            data_as_of=date(2026, 6, 1),
        )
    )
    db_session.add(
        CityWaterResource(
            city="HistoryCity",
            reservoir_level_pct=50.0,
            data_as_of=date(2026, 7, 1),
        )
    )
    db_session.add(
        CityWaterResource(
            city="HistoryCity",
            reservoir_level_pct=35.0,
            data_as_of=date(2026, 8, 1),
        )
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/water/history?city=HistoryCity", headers=auth_headers
    )
    assert resp.status_code == 200
    records = resp.json()["data"]
    assert len(records) == 3
    levels = [r["reservoir_level_pct"] for r in records]
    assert levels == [70.0, 50.0, 35.0]
