"""Week 1 RBAC / ownership regression tests (integration: real test DB).

Covers: unauthenticated, wrong-role and cross-user access on civic reports and
role-gated routers. Users are created only in the isolated test database.
"""

import pytest
import pytest_asyncio

from app.core.security import hash_password
from app.models.user import User, UserRole

pytestmark = pytest.mark.integration

PW = "Passw0rd!123"


async def _mk(db_session, client, email, role, city="Pune"):
    db_session.add(
        User(
            email=email,
            hashed_password=hash_password(PW),
            full_name="Test " + role.value,
            role=role,
            city=city,
            is_active=True,
        )
    )
    await db_session.commit()
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest_asyncio.fixture
async def actors(db_session, client):
    return {
        "citizen_a": await _mk(db_session, client, "a@t.in", UserRole.CITIZEN),
        "citizen_b": await _mk(db_session, client, "b@t.in", UserRole.CITIZEN),
        "inspector": await _mk(db_session, client, "i@t.in", UserRole.FIELD_INSPECTOR),
        "officer": await _mk(
            db_session, client, "o@t.in", UserRole.POLLUTION_CONTROL_OFFICER
        ),
        "admin": await _mk(db_session, client, "ad@t.in", UserRole.CITY_ADMINISTRATOR),
    }


async def _report(client, headers, issue_type="pothole"):
    r = await client.post(
        "/api/v1/civic/issues",
        json={
            "city": "Pune",
            "latitude": 18.52,
            "longitude": 73.85,
            "issue_type": issue_type,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


@pytest.mark.asyncio
async def test_citizen_list_never_includes_other_citizens_reports(client, actors):
    a_id = await _report(client, actors["citizen_a"])
    b_id = await _report(client, actors["citizen_b"], "garbage")

    # No only_mine parameter at all — the previously exploitable case.
    r = await client.get("/api/v1/civic/issues?city=Pune", headers=actors["citizen_a"])
    ids = {i["id"] for i in r.json()["data"]}
    assert ids == {a_id}

    # Explicitly asking for only_mine=false must not widen the result.
    r = await client.get(
        "/api/v1/civic/issues?city=Pune&only_mine=false", headers=actors["citizen_b"]
    )
    assert {i["id"] for i in r.json()["data"]} == {b_id}


@pytest.mark.asyncio
async def test_staff_still_see_full_queue(client, actors):
    a_id = await _report(client, actors["citizen_a"])
    b_id = await _report(client, actors["citizen_b"], "garbage")
    for role in ("officer", "admin", "inspector"):
        r = await client.get("/api/v1/civic/issues?city=Pune", headers=actors[role])
        assert {a_id, b_id} <= {i["id"] for i in r.json()["data"]}, role


@pytest.mark.asyncio
async def test_citizen_cannot_read_or_act_on_another_citizens_report(client, actors):
    a_id = await _report(client, actors["citizen_a"])
    other = actors["citizen_b"]

    assert (
        await client.get(f"/api/v1/civic/issues/{a_id}", headers=other)
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/civic/issues/{a_id}/citizen-verify",
            json={"confirmed": True},
            headers=other,
        )
    ).status_code == 403
    # Owner can still read it.
    assert (
        await client.get(f"/api/v1/civic/issues/{a_id}", headers=actors["citizen_a"])
    ).status_code == 200


@pytest.mark.asyncio
async def test_citizen_cannot_change_status_or_resolve(client, actors):
    a_id = await _report(client, actors["citizen_a"])
    h = actors["citizen_a"]
    s = await client.patch(
        f"/api/v1/civic/issues/{a_id}/status", json={"to_status": "triaged"}, headers=h
    )
    assert s.status_code == 403
    r = await client.post(
        f"/api/v1/civic/issues/{a_id}/resolve",
        json={"after_photo_data_url": "x", "resolution_notes": "x"},
        headers=h,
    )
    assert r.status_code == 403  # role gate runs before body validation


@pytest.mark.asyncio
async def test_officer_can_still_triage(client, actors):
    a_id = await _report(client, actors["citizen_a"])
    r = await client.patch(
        f"/api/v1/civic/issues/{a_id}/status",
        json={"to_status": "triaged"},
        headers=actors["officer"],
    )
    assert r.status_code == 200


# Analyst-only routers (admin + pollution officer): inspector/citizen -> 403.
ANALYST_GET = ["/api/v1/reports", "/api/v1/analytics", "/api/v1/agents/status"]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ANALYST_GET)
async def test_analyst_routes_role_matrix(client, actors, path):
    assert (await client.get(path)).status_code in (401, 403)  # unauthenticated
    for denied in ("citizen_a", "inspector"):
        r = await client.get(path, headers=actors[denied])
        assert r.status_code == 403, (path, denied, r.status_code)
    for allowed in ("officer", "admin"):
        r = await client.get(path, headers=actors[allowed])
        assert r.status_code != 403, (path, allowed)


@pytest.mark.asyncio
async def test_admin_only_writes(client, actors):
    body = {"city": "Pune", "name": "PMC"}
    assert (
        await client.post("/api/v1/civic/municipalities", json=body)
    ).status_code in (401, 403)
    for denied in ("citizen_a", "inspector", "officer"):
        r = await client.post(
            "/api/v1/civic/municipalities", json=body, headers=actors[denied]
        )
        assert r.status_code == 403, denied
    ok = await client.post(
        "/api/v1/civic/municipalities", json=body, headers=actors["admin"]
    )
    assert ok.status_code == 201


@pytest.mark.asyncio
async def test_citizen_cannot_use_staff_write_routes(client, actors):
    h = actors["citizen_a"]
    assert (await client.get("/api/v1/enforcement", headers=h)).status_code == 403
    assert (
        await client.post(
            "/api/v1/alerts",
            json={
                "ward_id": "W01",
                "city": "Pune",
                "language": "en",
                "channel": "push",
                "risk_level": "unhealthy",
                "aqi_value": 200,
            },
            headers=h,
        )
    ).status_code in (403, 422)


@pytest.mark.asyncio
async def test_register_cannot_escalate_role(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "esc@t.in",
            "password": PW,
            "full_name": "Eve Escalate",
            "role": "city_administrator",
        },
    )
    assert r.status_code == 201
    assert r.json()["data"]["role"] == "citizen"


@pytest.mark.asyncio
async def test_drone_planning_is_staff_only(client, actors):
    plan = {
        "hotspot_id": "H-1",
        "city": "Pune",
        "ward_id": "W01",
        "min_latitude": 18.50,
        "min_longitude": 73.84,
        "max_latitude": 18.51,
        "max_longitude": 73.85,
    }
    assert (await client.post("/api/v1/drone/plan", json=plan)).status_code in (
        401,
        403,
    )
    assert (await client.get("/api/v1/drone/plans")).status_code in (401, 403)
    h = actors["citizen_a"]
    assert (
        await client.post("/api/v1/drone/plan", json=plan, headers=h)
    ).status_code == 403
    assert (await client.get("/api/v1/drone/plans", headers=h)).status_code == 403
    ok = await client.get("/api/v1/drone/plans", headers=actors["inspector"])
    assert ok.status_code == 200
