import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import User


async def _create_notification(
    db_session: AsyncSession, user: User, title: str = "Air Quality Alert"
) -> Notification:
    notification = Notification(
        user_id=user.id,
        title=title,
        body="AQI level is High in your area.",
        notification_type="citizen_alert",
    )
    db_session.add(notification)
    await db_session.commit()
    await db_session.refresh(notification)
    return notification


@pytest.mark.asyncio
async def test_list_notifications_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/notifications")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_notifications_empty_state(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/notifications", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_notifications_returns_only_current_users_notifications(
    client: AsyncClient,
    auth_headers: dict,
    officer_auth_headers: dict,
    test_admin: User,
    test_officer: User,
    db_session: AsyncSession,
):
    await _create_notification(db_session, test_admin, title="Admin's alert")
    await _create_notification(db_session, test_officer, title="Officer's alert")

    admin_resp = await client.get("/api/v1/notifications", headers=auth_headers)
    admin_items = admin_resp.json()["data"]["items"]
    assert len(admin_items) == 1
    assert admin_items[0]["title"] == "Admin's alert"

    officer_resp = await client.get(
        "/api/v1/notifications", headers=officer_auth_headers
    )
    officer_items = officer_resp.json()["data"]["items"]
    assert len(officer_items) == 1
    assert officer_items[0]["title"] == "Officer's alert"


@pytest.mark.asyncio
async def test_unread_count_reflects_only_unread(
    client: AsyncClient, auth_headers: dict, test_admin: User, db_session: AsyncSession
):
    n1 = await _create_notification(db_session, test_admin, title="First")
    await _create_notification(db_session, test_admin, title="Second")

    resp = await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
    assert resp.json()["data"]["unread_count"] == 2

    await client.post(f"/api/v1/notifications/{n1.id}/read", headers=auth_headers)

    resp = await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
    assert resp.json()["data"]["unread_count"] == 1


@pytest.mark.asyncio
async def test_mark_notification_read_updates_state(
    client: AsyncClient, auth_headers: dict, test_admin: User, db_session: AsyncSession
):
    notification = await _create_notification(db_session, test_admin)

    resp = await client.post(
        f"/api/v1/notifications/{notification.id}/read", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_read"] is True
    assert data["read_at"] is not None


@pytest.mark.asyncio
async def test_mark_all_read_clears_unread_count(
    client: AsyncClient, auth_headers: dict, test_admin: User, db_session: AsyncSession
):
    await _create_notification(db_session, test_admin, title="First")
    await _create_notification(db_session, test_admin, title="Second")

    resp = await client.post("/api/v1/notifications/read-all", headers=auth_headers)
    assert resp.status_code == 200

    count_resp = await client.get(
        "/api/v1/notifications/unread-count", headers=auth_headers
    )
    assert count_resp.json()["data"]["unread_count"] == 0


@pytest.mark.asyncio
async def test_dismiss_notification_removes_it_from_list(
    client: AsyncClient, auth_headers: dict, test_admin: User, db_session: AsyncSession
):
    notification = await _create_notification(db_session, test_admin)

    resp = await client.delete(
        f"/api/v1/notifications/{notification.id}", headers=auth_headers
    )
    assert resp.status_code == 200

    list_resp = await client.get("/api/v1/notifications", headers=auth_headers)
    assert list_resp.json()["data"]["items"] == []


@pytest.mark.asyncio
async def test_user_cannot_mark_another_users_notification_read(
    client: AsyncClient,
    officer_auth_headers: dict,
    test_admin: User,
    db_session: AsyncSession,
):
    notification = await _create_notification(db_session, test_admin)

    resp = await client.post(
        f"/api/v1/notifications/{notification.id}/read",
        headers=officer_auth_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_user_cannot_dismiss_another_users_notification(
    client: AsyncClient,
    officer_auth_headers: dict,
    test_admin: User,
    db_session: AsyncSession,
):
    notification = await _create_notification(db_session, test_admin)

    resp = await client.delete(
        f"/api/v1/notifications/{notification.id}",
        headers=officer_auth_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_mark_read_returns_404_for_unknown_notification(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/v1/notifications/00000000-0000-0000-0000-000000000000/read",
        headers=auth_headers,
    )
    assert resp.status_code == 404
