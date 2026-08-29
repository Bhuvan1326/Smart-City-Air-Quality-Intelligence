from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.tests.test_helpers import make_db_session, make_session_cm
from app.workers.tasks import notifications


@pytest.fixture
def patched_engine():
    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_create_engine,
        patch("sqlalchemy.ext.asyncio.async_sessionmaker") as mock_sessionmaker,
    ):
        fake_engine = AsyncMock()
        mock_create_engine.return_value = fake_engine
        yield mock_create_engine, mock_sessionmaker, fake_engine


@pytest.mark.asyncio
async def test_dispatch_async_noop_when_notifications_disabled():
    with patch("app.workers.tasks.notifications.settings.NOTIFICATIONS_ENABLED", False):
        await notifications._dispatch_async()


@pytest.mark.asyncio
async def test_dispatch_async_returns_early_when_no_pending(patched_engine):
    _, mock_sessionmaker, fake_engine = patched_engine
    session = make_db_session()

    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=scalars_result)
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    with patch("app.workers.tasks.notifications.settings.NOTIFICATIONS_ENABLED", True):
        await notifications._dispatch_async()

    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_async_processes_pending_alerts(patched_engine):
    _, mock_sessionmaker, fake_engine = patched_engine
    session = make_db_session()
    session.commit = AsyncMock()

    alert1 = MagicMock()
    alert2 = MagicMock()
    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = [alert1, alert2]
    session.execute = AsyncMock(return_value=scalars_result)
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    outcome = MagicMock(delivered=1, failed=0, skipped_no_config=0)
    mock_dispatcher = MagicMock()
    mock_dispatcher.dispatch_alert = AsyncMock(return_value=outcome)

    with (
        patch("app.workers.tasks.notifications.settings.NOTIFICATIONS_ENABLED", True),
        patch(
            "app.services.notifications.dispatcher.NotificationDispatcher",
            return_value=mock_dispatcher,
        ),
    ):
        await notifications._dispatch_async()

    assert mock_dispatcher.dispatch_alert.await_count == 2
    session.commit.assert_awaited_once()
    fake_engine.dispose.assert_awaited_once()


def test_dispatch_pending_alerts_task_invokes_async(patched_engine):
    with (
        patch(
            "app.workers.tasks.notifications._dispatch_async", new=AsyncMock()
        ) as mocked,
        patch("app.workers.tasks.notifications.asyncio.run") as mock_run,
    ):
        mock_run.side_effect = lambda coro: coro.close()
        notifications.dispatch_pending_alerts.run()
        mocked.assert_called_once()
        mock_run.assert_called_once()
