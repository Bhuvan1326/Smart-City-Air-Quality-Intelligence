import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_enforcement_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/enforcement")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_enforcement_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/enforcement?city=EmptyCity", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["items"] == []


@pytest.mark.asyncio
async def test_create_enforcement_action(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/enforcement",
        json={
            "city": "Pune",
            "ward_id": "W07",
            "action_type": "inspection",
            "title": "Test inspection — construction dust",
            "description": "High AQI detected near construction site",
            "priority_score": 75.0,
            "latitude": 18.4968,
            "longitude": 73.8126,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["title"] == "Test inspection — construction dust"
    assert body["data"]["status"] == "pending"
    return body["data"]["id"]


@pytest.mark.asyncio
async def test_update_enforcement_status(client: AsyncClient, auth_headers: dict):
    # Create first
    create_resp = await client.post(
        "/api/v1/enforcement",
        json={
            "city": "Pune",
            "action_type": "notice",
            "title": "Update test action",
            "priority_score": 50.0,
        },
        headers=auth_headers,
    )
    action_id = create_resp.json()["data"]["id"]

    # Update
    resp = await client.patch(
        f"/api/v1/enforcement/{action_id}",
        json={
            "status": "in_progress",
            "notes": "Inspector dispatched to site",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "in_progress"
    assert data["notes"] == "Inspector dispatched to site"


@pytest.mark.asyncio
async def test_get_enforcement_action(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/enforcement",
        json={
            "city": "Pune",
            "action_type": "warning",
            "title": "Get test action",
            "priority_score": 40.0,
        },
        headers=auth_headers,
    )
    action_id = create_resp.json()["data"]["id"]

    resp = await client.get(f"/api/v1/enforcement/{action_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == action_id


@pytest.mark.asyncio
async def test_enforcement_not_found(client: AsyncClient, auth_headers: dict):
    import uuid

    resp = await client.get(f"/api/v1/enforcement/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_citizen_cannot_create_enforcement(client: AsyncClient):
    # Register as citizen
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "citizen_enf@test.in",
            "password": "Password@123",
            "full_name": "Citizen Test",
            "role": "citizen",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "citizen_enf@test.in",
            "password": "Password@123",
        },
    )
    token = login.json()["data"]["access_token"]

    resp = await client.post(
        "/api/v1/enforcement",
        json={
            "city": "Pune",
            "action_type": "inspection",
            "title": "Citizen attempt",
            "priority_score": 50.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
