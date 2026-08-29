from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.tests.test_helpers import make_db_session, make_session_cm
from app.workers.tasks import alerts


def ward_aqi_result(rows):
    result = MagicMock()
    result.__iter__.return_value = iter(rows)
    return result


def scalar_result(value):
    result = MagicMock()
    result.scalar.return_value = value
    return result


@pytest.fixture
def patched_engine():
    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_create_engine,
        patch("sqlalchemy.ext.asyncio.async_sessionmaker") as mock_sessionmaker,
    ):
        fake_engine = AsyncMock()
        mock_create_engine.return_value = fake_engine
        yield mock_create_engine, mock_sessionmaker, fake_engine


def test_get_risk_level_thresholds():
    assert alerts._get_risk_level(50) is None
    assert alerts._get_risk_level(120) == "moderate"
    assert alerts._get_risk_level(180) == "high"
    assert alerts._get_risk_level(250) == "very_high"
    assert alerts._get_risk_level(350) == "severe"


def test_get_vulnerability_groups_defaults_and_special_wards():
    assert alerts._get_vulnerability_groups("W99") == ["elderly", "children"]
    assert "schools" in alerts._get_vulnerability_groups("W01")
    industrial_groups = alerts._get_vulnerability_groups("W03")
    assert "outdoor_workers" in industrial_groups
    assert "industrial_area_residents" in industrial_groups


@pytest.mark.asyncio
async def test_alerts_async_creates_alerts_for_high_risk_ward(patched_engine):
    mock_create_engine, mock_sessionmaker, fake_engine = patched_engine
    session = make_db_session()
    session.execute = AsyncMock(
        side_effect=[
            ward_aqi_result([SimpleNamespace(ward_id="W01", avg_aqi=180)]),
            scalar_result(None),
        ]
    )
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    await alerts._alerts_async()

    assert session.add.call_count == 3
    session.commit.assert_awaited_once()
    fake_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_alerts_async_skips_moderate_and_low_risk(patched_engine):
    _, mock_sessionmaker, _ = patched_engine
    session = make_db_session()
    session.execute = AsyncMock(
        side_effect=[
            ward_aqi_result(
                [
                    SimpleNamespace(ward_id="W01", avg_aqi=50),
                    SimpleNamespace(ward_id="W02", avg_aqi=120),
                ]
            ),
        ]
    )
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    await alerts._alerts_async()

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_alerts_async_skips_ward_with_recent_alert(patched_engine):
    _, mock_sessionmaker, _ = patched_engine
    session = make_db_session()
    session.execute = AsyncMock(
        side_effect=[
            ward_aqi_result([SimpleNamespace(ward_id="W03", avg_aqi=320)]),
            scalar_result("existing-alert-id"),
        ]
    )
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    await alerts._alerts_async()

    session.add.assert_not_called()


def test_generate_ward_alerts_task_invokes_async(patched_engine):
    with (
        patch("app.workers.tasks.alerts._alerts_async", new=AsyncMock()) as mocked,
        patch("app.workers.tasks.alerts.asyncio.run") as mock_run,
    ):
        mock_run.side_effect = lambda coro: coro.close()
        alerts.generate_ward_alerts.run()
        mocked.assert_called_once()
        mock_run.assert_called_once()
