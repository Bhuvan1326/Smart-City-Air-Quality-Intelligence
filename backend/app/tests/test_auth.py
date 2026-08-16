import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@test.in",
            "password": "Password@123",
            "full_name": "Test User",
            "role": "citizen",
            "city": "Pune",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["email"] == "newuser@test.in"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {
        "email": "dup@test.in",
        "password": "Password@123",
        "full_name": "Dup User",
    }
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 400
    assert "already registered" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "logintest@test.in",
            "password": "Password@123",
            "full_name": "Login Test",
        },
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "logintest@test.in",
            "password": "Password@123",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrongpass@test.in",
            "password": "Password@123",
            "full_name": "Wrong Pass",
        },
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "wrongpass@test.in",
            "password": "WrongPassword",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["role"] == "city_administrator"


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_token_refresh(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "refresh@test.in",
            "password": "Password@123",
            "full_name": "Refresh Test",
        },
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "refresh@test.in",
            "password": "Password@123",
        },
    )
    refresh_token = login_resp.json()["data"]["refresh_token"]

    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()["data"]


@pytest.mark.asyncio
async def test_invalid_token_rejected(client: AsyncClient):
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer invalid.token.here"}
    )
    assert resp.status_code == 401
