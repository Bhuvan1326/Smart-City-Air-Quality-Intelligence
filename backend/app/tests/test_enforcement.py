import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User, UserRole


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


# ---------------------------------------------------------------------------
# Field-inspector ownership authorization.
#
# GET /{action_id} and POST /{action_id}/evidence previously only required
# the officer role (RequireOfficer) without also verifying that a
# FIELD_INSPECTOR owns the action, unlike the update flow — meaning any
# authenticated field inspector could read or attach evidence to *any*
# other inspector's action just by knowing its UUID. These tests pin down
# the fixed behavior across every endpoint that takes an action_id, and
# confirm admins/officers keep their existing broader access.
# ---------------------------------------------------------------------------


async def _create_user(
    db_session: AsyncSession, email: str, role: UserRole, password: str = "Test@123"
) -> User:
    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=f"Test {role.value}",
        role=role,
        city="Pune",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _login(client: AsyncClient, email: str, password: str = "Test@123") -> dict:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _create_action_as(client: AsyncClient, headers: dict, title: str) -> str:
    resp = await client.post(
        "/api/v1/enforcement",
        json={
            "city": "Pune",
            "action_type": "inspection",
            "title": title,
            "priority_score": 60.0,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


@pytest.mark.asyncio
async def test_field_inspector_can_access_own_action(
    client: AsyncClient, db_session: AsyncSession
):
    await _create_user(
        db_session, "inspector_own_get@test.in", UserRole.FIELD_INSPECTOR
    )
    headers = await _login(client, "inspector_own_get@test.in")
    action_id = await _create_action_as(client, headers, "Inspector's own action")

    resp = await client.get(f"/api/v1/enforcement/{action_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == action_id


@pytest.mark.asyncio
async def test_field_inspector_cannot_access_other_inspectors_action(
    client: AsyncClient, db_session: AsyncSession
):
    await _create_user(db_session, "inspector_a_get@test.in", UserRole.FIELD_INSPECTOR)
    await _create_user(db_session, "inspector_b_get@test.in", UserRole.FIELD_INSPECTOR)
    headers_a = await _login(client, "inspector_a_get@test.in")
    headers_b = await _login(client, "inspector_b_get@test.in")

    action_id = await _create_action_as(client, headers_a, "Inspector A's action")

    resp = await client.get(f"/api/v1/enforcement/{action_id}", headers=headers_b)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_field_inspector_can_submit_evidence_to_own_action(
    client: AsyncClient, db_session: AsyncSession
):
    await _create_user(
        db_session, "inspector_own_evidence@test.in", UserRole.FIELD_INSPECTOR
    )
    headers = await _login(client, "inspector_own_evidence@test.in")
    action_id = await _create_action_as(client, headers, "Own action for evidence")

    resp = await client.post(
        f"/api/v1/enforcement/{action_id}/evidence",
        json={
            "client_id": "client-own-1",
            "status": "in_progress",
            "notes": "Inspected on site",
            "photos": [],
            "captured_at": "2026-01-01T10:00:00Z",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["action_id"] == action_id


@pytest.mark.asyncio
async def test_field_inspector_cannot_submit_evidence_to_other_action(
    client: AsyncClient, db_session: AsyncSession
):
    await _create_user(
        db_session, "inspector_a_evidence@test.in", UserRole.FIELD_INSPECTOR
    )
    await _create_user(
        db_session, "inspector_b_evidence@test.in", UserRole.FIELD_INSPECTOR
    )
    headers_a = await _login(client, "inspector_a_evidence@test.in")
    headers_b = await _login(client, "inspector_b_evidence@test.in")

    action_id = await _create_action_as(client, headers_a, "Inspector A's action")

    resp = await client.post(
        f"/api/v1/enforcement/{action_id}/evidence",
        json={
            "client_id": "client-other-1",
            "status": "in_progress",
            "notes": "Attempted intrusion",
            "photos": [],
            "captured_at": "2026-01-01T10:00:00Z",
        },
        headers=headers_b,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_field_inspector_can_update_own_action(
    client: AsyncClient, db_session: AsyncSession
):
    await _create_user(
        db_session, "inspector_own_update@test.in", UserRole.FIELD_INSPECTOR
    )
    headers = await _login(client, "inspector_own_update@test.in")
    action_id = await _create_action_as(client, headers, "Own action for update")

    resp = await client.patch(
        f"/api/v1/enforcement/{action_id}",
        json={"notes": "Updated by owning inspector"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["notes"] == "Updated by owning inspector"


@pytest.mark.asyncio
async def test_field_inspector_cannot_update_other_inspectors_action(
    client: AsyncClient, db_session: AsyncSession
):
    await _create_user(
        db_session, "inspector_a_update@test.in", UserRole.FIELD_INSPECTOR
    )
    await _create_user(
        db_session, "inspector_b_update@test.in", UserRole.FIELD_INSPECTOR
    )
    headers_a = await _login(client, "inspector_a_update@test.in")
    headers_b = await _login(client, "inspector_b_update@test.in")

    action_id = await _create_action_as(client, headers_a, "Inspector A's action")

    resp = await client.patch(
        f"/api/v1/enforcement/{action_id}",
        json={"notes": "Should not be allowed"},
        headers=headers_b,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_retains_full_access_to_any_inspectors_action(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    await _create_user(
        db_session, "inspector_for_admin@test.in", UserRole.FIELD_INSPECTOR
    )
    inspector_headers = await _login(client, "inspector_for_admin@test.in")
    action_id = await _create_action_as(
        client, inspector_headers, "Inspector action visible to admin"
    )

    get_resp = await client.get(
        f"/api/v1/enforcement/{action_id}", headers=auth_headers
    )
    assert get_resp.status_code == 200

    patch_resp = await client.patch(
        f"/api/v1/enforcement/{action_id}",
        json={"notes": "Admin override"},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["data"]["notes"] == "Admin override"

    evidence_resp = await client.post(
        f"/api/v1/enforcement/{action_id}/evidence",
        json={
            "client_id": "client-admin-1",
            "status": "completed",
            "notes": "Closed out by admin",
            "photos": [],
            "captured_at": "2026-01-01T10:00:00Z",
        },
        headers=auth_headers,
    )
    assert evidence_resp.status_code == 200


@pytest.mark.asyncio
async def test_pollution_control_officer_retains_broader_access(
    client: AsyncClient, db_session: AsyncSession
):
    await _create_user(
        db_session, "inspector_for_officer@test.in", UserRole.FIELD_INSPECTOR
    )
    await _create_user(
        db_session, "officer_for_test@test.in", UserRole.POLLUTION_CONTROL_OFFICER
    )
    inspector_headers = await _login(client, "inspector_for_officer@test.in")
    officer_headers = await _login(client, "officer_for_test@test.in")

    action_id = await _create_action_as(
        client, inspector_headers, "Inspector action visible to officer"
    )

    resp = await client.get(f"/api/v1/enforcement/{action_id}", headers=officer_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_unauthenticated_denied_for_action_detail_and_evidence(
    client: AsyncClient,
):
    import uuid

    random_id = uuid.uuid4()

    get_resp = await client.get(f"/api/v1/enforcement/{random_id}")
    assert get_resp.status_code == 403

    evidence_resp = await client.post(
        f"/api/v1/enforcement/{random_id}/evidence",
        json={
            "client_id": "client-unauth-1",
            "status": "in_progress",
            "photos": [],
            "captured_at": "2026-01-01T10:00:00Z",
        },
    )
    assert evidence_resp.status_code == 403
