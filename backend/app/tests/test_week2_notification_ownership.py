"""Week 2 (B4): notifications are strictly per-user."""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.security import hash_password
from app.models.notification import Notification
from app.models.user import User, UserRole

pytestmark = pytest.mark.integration
PW = "Passw0rd!123"


async def _user(db, client, email, role=UserRole.CITIZEN):
    db.add(
        User(
            email=email,
            hashed_password=hash_password(PW),
            full_name="T " + email,
            role=role,
            city="Pune",
            is_active=True,
        )
    )
    await db.commit()
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    u = (await db.execute(select(User).where(User.email == email))).scalar_one()
    return u, {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest_asyncio.fixture
async def two_users(db_session, client):
    a, ha = await _user(db_session, client, "na@t.in")
    b, hb = await _user(
        db_session, client, "nb@t.in", UserRole.POLLUTION_CONTROL_OFFICER
    )
    na = Notification(
        user_id=a.id, title="A1", body="private-a", notification_type="alert"
    )
    nb = Notification(
        user_id=b.id, title="B1", body="private-b", notification_type="alert"
    )
    db_session.add_all([na, nb])
    await db_session.commit()
    return {"a": ha, "b": hb, "na": str(na.id), "nb": str(nb.id)}


@pytest.mark.asyncio
async def test_list_and_count_are_scoped_to_caller(client, two_users):
    r = await client.get("/api/v1/notifications", headers=two_users["a"])
    bodies = [n["body"] for n in r.json()["data"]["items"]]
    assert bodies == ["private-a"]
    c = await client.get("/api/v1/notifications/unread-count", headers=two_users["b"])
    assert c.json()["data"]["unread_count"] == 1


@pytest.mark.asyncio
async def test_cannot_read_or_dismiss_another_users_notification(client, two_users):
    other_id = two_users["nb"]
    r = await client.post(
        f"/api/v1/notifications/{other_id}/read", headers=two_users["a"]
    )
    assert r.status_code in (403, 404)
    d = await client.delete(f"/api/v1/notifications/{other_id}", headers=two_users["a"])
    assert d.status_code in (403, 404)
    # The victim's notification is untouched.
    still = await client.get("/api/v1/notifications", headers=two_users["b"])
    item = still.json()["data"]["items"][0]
    assert item["is_read"] is False


@pytest.mark.asyncio
async def test_read_all_only_affects_the_caller(client, two_users):
    assert (
        await client.post("/api/v1/notifications/read-all", headers=two_users["a"])
    ).status_code == 200
    mine = await client.get(
        "/api/v1/notifications/unread-count", headers=two_users["a"]
    )
    theirs = await client.get(
        "/api/v1/notifications/unread-count", headers=two_users["b"]
    )
    assert mine.json()["data"]["unread_count"] == 0
    assert theirs.json()["data"]["unread_count"] == 1


@pytest.mark.asyncio
async def test_owner_can_read_and_dismiss(client, two_users):
    nid = two_users["na"]
    r = await client.post(f"/api/v1/notifications/{nid}/read", headers=two_users["a"])
    assert r.status_code == 200 and r.json()["data"]["is_read"] is True
    assert (
        await client.delete(f"/api/v1/notifications/{nid}", headers=two_users["a"])
    ).status_code == 200
    gone = await client.get("/api/v1/notifications", headers=two_users["a"])
    assert gone.json()["data"]["items"] == []


@pytest.mark.asyncio
async def test_unauthenticated_access_is_rejected(client, two_users):
    for method, path in (
        ("get", "/api/v1/notifications"),
        ("get", "/api/v1/notifications/unread-count"),
        ("post", "/api/v1/notifications/read-all"),
        ("post", f"/api/v1/notifications/{two_users['na']}/read"),
        ("delete", f"/api/v1/notifications/{two_users['na']}"),
    ):
        r = await getattr(client, method)(path)
        assert r.status_code in (401, 403), path
