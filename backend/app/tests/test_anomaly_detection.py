from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tests.test_helpers import make_db_session, make_session_cm
from app.workers.tasks import anomaly_detection


def rows_result(rows):
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


def scalar_result(value):
    result = MagicMock()
    result.scalar.return_value = value
    return result


@pytest.fixture
def patched_engine():
    with patch(
        "sqlalchemy.ext.asyncio.create_async_engine"
    ) as mock_create_engine, patch(
        "sqlalchemy.ext.asyncio.async_sessionmaker"
    ) as mock_sessionmaker:
        fake_engine = AsyncMock()
        mock_create_engine.return_value = fake_engine
        yield mock_create_engine, mock_sessionmaker, fake_engine


def spike_row(
    station_id="station-1",
    aqi=250,
    ward_id="W03",
    z_score=3.0,
    avg_aqi=100.0,
):
    return SimpleNamespace(
        station_id=station_id,
        aqi=aqi,
        timestamp=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
        ward_id=ward_id,
        city="Pune",
        latitude=18.5,
        longitude=73.8,
        name="Test Station",
        avg_aqi=avg_aqi,
        std_aqi=10.0,
        z_score=z_score,
    )


@pytest.mark.asyncio
async def test_detect_async_creates_event_peak_hour_vehicular(patched_engine):
    _, mock_sessionmaker, fake_engine = patched_engine
    session = make_db_session()
    session.execute = AsyncMock(
        side_effect=[
            rows_result([spike_row(ward_id="W01")]),
            scalar_result(None),
        ]
    )
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    with patch("app.workers.tasks.anomaly_detection.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
        await anomaly_detection._detect_async()

    session.add.assert_called_once()
    added_event = session.add.call_args[0][0]
    assert added_event.cause_category == "vehicular"
    session.commit.assert_awaited_once()
    fake_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_detect_async_industrial_off_peak(patched_engine):
    _, mock_sessionmaker, _ = patched_engine
    session = make_db_session()
    session.execute = AsyncMock(
        side_effect=[
            rows_result([spike_row(ward_id="W04")]),
            scalar_result(None),
        ]
    )
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    with patch("app.workers.tasks.anomaly_detection.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)
        await anomaly_detection._detect_async()

    added_event = session.add.call_args[0][0]
    assert added_event.cause_category == "industrial"


@pytest.mark.asyncio
async def test_detect_async_unknown_cause_off_peak_non_industrial_ward(patched_engine):
    _, mock_sessionmaker, _ = patched_engine
    session = make_db_session()
    session.execute = AsyncMock(
        side_effect=[
            rows_result([spike_row(ward_id="W07")]),
            scalar_result(None),
        ]
    )
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    with patch("app.workers.tasks.anomaly_detection.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)
        await anomaly_detection._detect_async()

    added_event = session.add.call_args[0][0]
    assert added_event.cause_category == "unknown"


@pytest.mark.asyncio
async def test_detect_async_skips_when_already_logged(patched_engine):
    _, mock_sessionmaker, _ = patched_engine
    session = make_db_session()
    session.execute = AsyncMock(
        side_effect=[
            rows_result([spike_row()]),
            scalar_result("already-there"),
        ]
    )
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    await anomaly_detection._detect_async()

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_detect_async_no_spikes(patched_engine):
    _, mock_sessionmaker, _ = patched_engine
    session = make_db_session()
    session.execute = AsyncMock(side_effect=[rows_result([])])
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    await anomaly_detection._detect_async()

    session.add.assert_not_called()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_detect_async_confidence_capped_and_null_z(patched_engine):
    _, mock_sessionmaker, _ = patched_engine
    session = make_db_session()
    session.execute = AsyncMock(
        side_effect=[
            rows_result([spike_row(z_score=None)]),
            scalar_result(None),
        ]
    )
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    await anomaly_detection._detect_async()

    added_event = session.add.call_args[0][0]
    assert 0 <= added_event.confidence_score <= 0.95


def station_row(station_id="s1", maintenance_score=0.9):
    return SimpleNamespace(
        id=station_id,
        name="Station One",
        city="Pune",
        ward_id="W01",
        maintenance_score=maintenance_score,
    )


@pytest.mark.asyncio
async def test_maintenance_async_assesses_all_stations(patched_engine):
    _, mock_sessionmaker, fake_engine = patched_engine
    session = make_db_session()

    stations_result = MagicMock()
    stations_result.fetchall.return_value = [station_row()]

    network_result = MagicMock()
    network_result.__iter__.return_value = iter(
        [SimpleNamespace(avg_aqi=90.0), SimpleNamespace(avg_aqi=None)]
    )

    recent_result = MagicMock()
    recent_result.__iter__.return_value = iter(
        [SimpleNamespace(timestamp=datetime.now(UTC), aqi=95)]
    )

    baseline_result = MagicMock()
    baseline_result.__iter__.return_value = iter([])

    session.execute = AsyncMock(
        side_effect=[
            stations_result,
            network_result,
            recent_result,
            baseline_result,
            MagicMock(),
        ]
    )
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    await anomaly_detection._maintenance_async()

    session.add.assert_called_once()
    session.commit.assert_awaited_once()
    fake_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_maintenance_async_no_active_stations(patched_engine):
    _, mock_sessionmaker, _ = patched_engine
    session = make_db_session()

    stations_result = MagicMock()
    stations_result.fetchall.return_value = []

    network_result = MagicMock()
    network_result.__iter__.return_value = iter([])

    session.execute = AsyncMock(side_effect=[stations_result, network_result])
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    await anomaly_detection._maintenance_async()

    session.add.assert_not_called()
    session.commit.assert_awaited_once()


def test_detect_anomalies_task_invokes_async(patched_engine):
    with patch(
        "app.workers.tasks.anomaly_detection._detect_async", new=AsyncMock()
    ) as mocked, patch(
        "app.workers.tasks.anomaly_detection.asyncio.run"
    ) as mock_run:
        mock_run.side_effect = lambda coro: coro.close()
        anomaly_detection.detect_anomalies.run()
        mocked.assert_called_once()
        mock_run.assert_called_once()


def test_predict_sensor_maintenance_task_invokes_async(patched_engine):
    with patch(
        "app.workers.tasks.anomaly_detection._maintenance_async", new=AsyncMock()
    ) as mocked, patch(
        "app.workers.tasks.anomaly_detection.asyncio.run"
    ) as mock_run:
        mock_run.side_effect = lambda coro: coro.close()
        anomaly_detection.predict_sensor_maintenance.run()
        mocked.assert_called_once()
        mock_run.assert_called_once()