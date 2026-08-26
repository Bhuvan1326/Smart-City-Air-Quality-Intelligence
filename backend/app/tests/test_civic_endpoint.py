import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_submit_civic_issue_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/civic/issues",
        json={
            "city": "Pune",
            "latitude": 18.52,
            "longitude": 73.85,
            "issue_type": "pothole",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_submit_civic_issue_without_type_or_photo_is_rejected(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/v1/civic/issues",
        json={"city": "Pune", "latitude": 18.52, "longitude": 73.85},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_civic_issue_with_citizen_type_creates_issue(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/v1/civic/issues",
        json={
            "city": "Pune",
            "latitude": 18.5204,
            "longitude": 73.8567,
            "issue_type": "pothole",
            "severity": "high",
            "description": "Large pothole near the market.",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["issue_type"] == "pothole"
    assert data["classification_source"] == "citizen_reported"
    assert data["status"] == "submitted"
    assert data["assigned_department"] == "Roads & Infrastructure Department"
    assert data["sla_deadline"]
    assert len(data["status_events"]) == 1
    assert data["status_events"][0]["to_status"] == "submitted"


@pytest.mark.asyncio
async def test_critical_severity_gives_shorter_sla_than_low(
    client: AsyncClient, auth_headers: dict
):
    low = await client.post(
        "/api/v1/civic/issues",
        json={
            "city": "Pune",
            "latitude": 18.5204,
            "longitude": 73.8567,
            "issue_type": "garbage",
            "severity": "low",
        },
        headers=auth_headers,
    )
    critical = await client.post(
        "/api/v1/civic/issues",
        json={
            "city": "Pune",
            "latitude": 18.5204,
            "longitude": 73.8567,
            "issue_type": "garbage",
            "severity": "critical",
        },
        headers=auth_headers,
    )
    assert low.json()["data"]["sla_hours"] > critical.json()["data"]["sla_hours"]


@pytest.mark.asyncio
async def test_status_transition_enforced(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/civic/issues",
        json={
            "city": "Pune",
            "latitude": 18.5204,
            "longitude": 73.8567,
            "issue_type": "streetlight",
        },
        headers=auth_headers,
    )
    issue_id = create_resp.json()["data"]["id"]

    # Invalid: SUBMITTED -> RESOLVED skips required steps.
    invalid_resp = await client.patch(
        f"/api/v1/civic/issues/{issue_id}/status",
        json={"to_status": "resolved"},
        headers=auth_headers,
    )
    assert invalid_resp.status_code == 400

    # Valid: SUBMITTED -> ASSIGNED.
    valid_resp = await client.patch(
        f"/api/v1/civic/issues/{issue_id}/status",
        json={"to_status": "assigned", "note": "Routed to department."},
        headers=auth_headers,
    )
    assert valid_resp.status_code == 200
    data = valid_resp.json()["data"]
    assert data["status"] == "assigned"
    assert len(data["status_events"]) == 2


@pytest.mark.asyncio
async def test_status_update_requires_officer_role(
    client: AsyncClient, auth_headers: dict
):
    create_resp = await client.post(
        "/api/v1/civic/issues",
        json={
            "city": "Pune",
            "latitude": 18.5204,
            "longitude": 73.8567,
            "issue_type": "drainage",
        },
        headers=auth_headers,
    )
    issue_id = create_resp.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/civic/issues/{issue_id}/status",
        json={"to_status": "triaged"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_civic_issues_filters_by_status(
    client: AsyncClient, auth_headers: dict
):
    await client.post(
        "/api/v1/civic/issues",
        json={
            "city": "Pune",
            "latitude": 18.5204,
            "longitude": 73.8567,
            "issue_type": "fallen_tree",
        },
        headers=auth_headers,
    )

    resp = await client.get(
        "/api/v1/civic/issues?city=Pune&status=submitted", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert all(item["status"] == "submitted" for item in data)
    assert any(item["issue_type"] == "fallen_tree" for item in data)
