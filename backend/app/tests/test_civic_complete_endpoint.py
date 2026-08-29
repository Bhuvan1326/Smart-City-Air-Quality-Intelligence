"""Endpoint tests for the completed Civic Issue Intelligence workflow:
resolution proof, AI verification (mocked), citizen confirmation,
escalation, duplicate clustering, and governance CRUD. DB-backed
(auto-marked integration via db_session/client fixtures).
"""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from app.core.security import hash_password
from app.models.civic_issue import CivicIssue, CivicIssueStatus
from app.models.user import User, UserRole
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


def _tiny_photo_data_url() -> str:
    import base64

    payload = base64.b64encode(b"\xff\xd8\xff\xe0fake-jpeg-bytes").decode()
    return f"data:image/jpeg;base64,{payload}"


async def _create_second_user(db_session: AsyncSession, email: str) -> User:
    user = User(
        email=email,
        hashed_password=hash_password("Other@123"),
        full_name="Other Citizen",
        role=UserRole.CITIZEN,
        city="Pune",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _login(client: AsyncClient, email: str, password: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _submit_and_progress_to_in_progress(
    client: AsyncClient, auth_headers: dict, issue_type: str = "pothole"
) -> str:
    create_resp = await client.post(
        "/api/v1/civic/issues",
        json={
            "city": "ResolutionFlowCity",
            "latitude": 18.5204,
            "longitude": 73.8567,
            "issue_type": issue_type,
        },
        headers=auth_headers,
    )
    issue_id = create_resp.json()["data"]["id"]
    for to_status in ("assigned", "acknowledged", "in_progress"):
        await client.patch(
            f"/api/v1/civic/issues/{issue_id}/status",
            json={"to_status": to_status},
            headers=auth_headers,
        )
    return issue_id


@pytest.mark.asyncio
async def test_generic_patch_cannot_set_resolved_directly(
    client: AsyncClient, auth_headers: dict
):
    issue_id = await _submit_and_progress_to_in_progress(client, auth_headers)
    resp = await client.patch(
        f"/api/v1/civic/issues/{issue_id}/status",
        json={"to_status": "resolved"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_resolve_requires_after_photo_and_notes(
    client: AsyncClient, auth_headers: dict
):
    issue_id = await _submit_and_progress_to_in_progress(client, auth_headers)

    with patch(
        "app.services.civic_resolution_verification.verify_resolution",
        AsyncMock(return_value=None),
    ):
        resp = await client.post(
            f"/api/v1/civic/issues/{issue_id}/resolve",
            json={
                "after_photo_data_url": _tiny_photo_data_url(),
                "resolution_notes": "Filled the pothole with asphalt.",
            },
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "verification_pending"
    assert data["resolution_photo_url"]
    assert data["resolved_at"]


@pytest.mark.asyncio
async def test_full_resolution_and_citizen_confirmation_loop(
    client: AsyncClient, auth_headers: dict
):
    issue_id = await _submit_and_progress_to_in_progress(client, auth_headers)

    with patch(
        "app.services.civic_resolution_verification.verify_resolution",
        AsyncMock(return_value=None),
    ):
        await client.post(
            f"/api/v1/civic/issues/{issue_id}/resolve",
            json={
                "after_photo_data_url": _tiny_photo_data_url(),
                "resolution_notes": "Fixed.",
            },
            headers=auth_headers,
        )

    verify_resp = await client.post(
        f"/api/v1/civic/issues/{issue_id}/citizen-verify",
        json={"confirmed": True},
        headers=auth_headers,
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["data"]["status"] == "verified"

    close_resp = await client.patch(
        f"/api/v1/civic/issues/{issue_id}/status",
        json={"to_status": "closed"},
        headers=auth_headers,
    )
    assert close_resp.status_code == 200
    assert close_resp.json()["data"]["status"] == "closed"


@pytest.mark.asyncio
async def test_citizen_reopen_when_not_actually_fixed(
    client: AsyncClient, auth_headers: dict
):
    issue_id = await _submit_and_progress_to_in_progress(client, auth_headers)

    with patch(
        "app.services.civic_resolution_verification.verify_resolution",
        AsyncMock(return_value=None),
    ):
        await client.post(
            f"/api/v1/civic/issues/{issue_id}/resolve",
            json={
                "after_photo_data_url": _tiny_photo_data_url(),
                "resolution_notes": "Fixed.",
            },
            headers=auth_headers,
        )

    resp = await client.post(
        f"/api/v1/civic/issues/{issue_id}/citizen-verify",
        json={"confirmed": False, "note": "Still broken."},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "reopened"
    assert data["reopen_count"] == 1


@pytest.mark.asyncio
async def test_only_reporter_can_citizen_verify(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    issue_id = await _submit_and_progress_to_in_progress(client, auth_headers)
    with patch(
        "app.services.civic_resolution_verification.verify_resolution",
        AsyncMock(return_value=None),
    ):
        await client.post(
            f"/api/v1/civic/issues/{issue_id}/resolve",
            json={
                "after_photo_data_url": _tiny_photo_data_url(),
                "resolution_notes": "Fixed.",
            },
            headers=auth_headers,
        )

    await _create_second_user(db_session, "other_citizen@example.com")
    other_headers = await _login(client, "other_citizen@example.com", "Other@123")

    resp = await client.post(
        f"/api/v1/civic/issues/{issue_id}/citizen-verify",
        json={"confirmed": True},
        headers=other_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_duplicate_report_within_radius_and_window_is_clustered(
    client: AsyncClient, auth_headers: dict
):
    first = await client.post(
        "/api/v1/civic/issues",
        json={
            "city": "ClusterTestCity",
            "latitude": 18.5204,
            "longitude": 73.8567,
            "issue_type": "garbage",
        },
        headers=auth_headers,
    )
    second = await client.post(
        "/api/v1/civic/issues",
        json={
            "city": "ClusterTestCity",
            "latitude": 18.52041,  # ~1m away
            "longitude": 73.85671,
            "issue_type": "garbage",
        },
        headers=auth_headers,
    )
    first_data = first.json()["data"]
    second_data = second.json()["data"]

    assert first_data["is_duplicate_of_cluster"] is False
    assert second_data["is_duplicate_of_cluster"] is True
    assert second_data["cluster_id"] == first_data["cluster_id"]
    assert second_data["duplicate_report_count"] == 2


@pytest.mark.asyncio
async def test_escalation_run_marks_overdue_issue(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_admin
):
    issue = CivicIssue(
        reporter_id=test_admin.id,
        city="EscalationTestCity",
        ward_id="W01",
        ward_assignment_method="unavailable",
        latitude=18.5,
        longitude=73.8,
        issue_type="drainage",
        classification_source="citizen_reported",
        severity="moderate",
        status=CivicIssueStatus.IN_PROGRESS.value,
        sla_hours=48.0,
        sla_deadline=datetime.now(UTC) - timedelta(hours=2),
        is_overdue=False,
    )
    db_session.add(issue)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/civic/escalation/run?city=EscalationTestCity", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["newly_overdue"] == 1
    assert data["newly_escalated"] == 1


@pytest.mark.asyncio
async def test_municipality_and_ward_office_and_representative_crud(
    client: AsyncClient, auth_headers: dict
):
    muni_resp = await client.post(
        "/api/v1/civic/municipalities",
        json={"city": "GovTestCity", "name": "GovTestCity Municipal Corporation"},
        headers=auth_headers,
    )
    assert muni_resp.status_code == 201

    office_resp = await client.post(
        "/api/v1/civic/ward-offices",
        json={
            "city": "GovTestCity",
            "ward_id": "W01",
            "office_name": "Ward 1 Office",
            "contact_phone": "020-1234567",
        },
        headers=auth_headers,
    )
    assert office_resp.status_code == 201

    rep_resp = await client.post(
        "/api/v1/civic/representatives",
        json={
            "city": "GovTestCity",
            "ward_id": "W01",
            "name": "Test Representative",
            "role": "Corporator",
            "source": "Test election commission record",
        },
        headers=auth_headers,
    )
    assert rep_resp.status_code == 201

    # A new issue in that ward should now show governance context.
    issue_resp = await client.post(
        "/api/v1/civic/issues",
        json={
            "city": "GovTestCity",
            "latitude": 18.5204,
            "longitude": 73.8567,
            "issue_type": "pothole",
        },
        headers=auth_headers,
    )
    data = issue_resp.json()["data"]
    # ward_id assignment is UNAVAILABLE for a fresh city with no boundaries/stations,
    # so governance context won't resolve to this ward — but the endpoint itself
    # must not error, and the response shape must include the fields.
    assert "responsible_authority" in data
    assert "elected_representative" in data


@pytest.mark.asyncio
async def test_ward_boundary_creation_and_polygon_assignment(
    client: AsyncClient, auth_headers: dict
):
    boundary_resp = await client.post(
        "/api/v1/civic/ward-boundaries",
        json={
            "city": "PolygonTestCity",
            "ward_id": "PW01",
            "ring": [
                [73.80, 18.50],
                [73.90, 18.50],
                [73.90, 18.60],
                [73.80, 18.60],
                [73.80, 18.50],
            ],
            "source": "Test approximate rectangle for unit testing",
            "effective_from": date(2020, 1, 1).isoformat(),
        },
        headers=auth_headers,
    )
    assert boundary_resp.status_code == 201

    issue_resp = await client.post(
        "/api/v1/civic/issues",
        json={
            "city": "PolygonTestCity",
            "latitude": 18.55,  # inside the rectangle
            "longitude": 73.85,
            "issue_type": "pothole",
        },
        headers=auth_headers,
    )
    data = issue_resp.json()["data"]
    assert data["ward_id"] == "PW01"
    assert data["ward_assignment_method"] == "point_in_polygon"
