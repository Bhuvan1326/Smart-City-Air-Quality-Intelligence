from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import seeder
from app.tests.test_helpers import make_db_session, make_session_cm


def scalar_result(value):
    result = MagicMock()
    result.scalar.return_value = value
    return result


def fetchall_result(rows):
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


def scalars_all_result(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


@pytest.fixture
def patched_engine():
    with (
        patch("app.core.seeder.create_async_engine") as mock_create_engine,
        patch("app.core.seeder.async_sessionmaker") as mock_sessionmaker,
    ):
        fake_engine = AsyncMock()
        mock_create_engine.return_value = fake_engine
        yield mock_create_engine, mock_sessionmaker, fake_engine


@pytest.mark.asyncio
async def test_seed_all_skips_when_data_exists(patched_engine):
    _, mock_sessionmaker, fake_engine = patched_engine
    session = make_db_session()
    session.scalar = AsyncMock(return_value=5)
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    await seeder.seed_all()

    session.commit.assert_not_called()
    fake_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_seed_all_runs_full_pipeline_when_empty(patched_engine):
    _, mock_sessionmaker, fake_engine = patched_engine
    session = make_db_session()
    session.scalar = AsyncMock(return_value=0)
    session.flush = AsyncMock()
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    with (
        patch("app.core.seeder._seed_users", new=AsyncMock()) as m_users,
        patch("app.core.seeder._seed_stations", new=AsyncMock()) as m_stations,
        patch("app.core.seeder._seed_emission_sources", new=AsyncMock()) as m_emission,
        patch(
            "app.core.seeder._seed_aqi_readings", new=AsyncMock(return_value=["id1"])
        ) as m_aqi,
        patch("app.core.seeder._seed_forecasts", new=AsyncMock()) as m_forecasts,
        patch("app.core.seeder._seed_attributions", new=AsyncMock()) as m_attr,
        patch("app.core.seeder._seed_anomalies", new=AsyncMock()) as m_anom,
        patch("app.core.seeder._seed_enforcement", new=AsyncMock()) as m_enforce,
        patch("app.core.seeder._seed_outcomes", new=AsyncMock()) as m_outcomes,
        patch("app.core.seeder._seed_policy_snapshots", new=AsyncMock()) as m_policy,
        patch("app.core.seeder._seed_alerts", new=AsyncMock()) as m_alerts,
    ):
        await seeder.seed_all()

    m_users.assert_awaited_once()
    m_stations.assert_awaited_once()
    m_emission.assert_awaited_once()
    m_aqi.assert_awaited_once()
    m_forecasts.assert_awaited_once()
    m_attr.assert_awaited_once()
    m_anom.assert_awaited_once_with(session, ["id1"])
    m_enforce.assert_awaited_once()
    m_outcomes.assert_awaited_once()
    m_policy.assert_awaited_once()
    m_alerts.assert_awaited_once()
    session.commit.assert_awaited_once()
    fake_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_seed_users_adds_four_users():
    session = make_db_session()
    session.flush = AsyncMock()

    with patch("app.core.seeder.hash_password", return_value="hashed"):
        await seeder._seed_users(session)

    session.add_all.assert_called_once()
    users = session.add_all.call_args[0][0]
    assert len(users) == 4
    assert {u.role.value for u in users} == {
        "city_administrator",
        "pollution_control_officer",
        "field_inspector",
        "citizen",
    }
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_seed_stations_adds_all_stations_with_correct_city():
    session = make_db_session()
    session.flush = AsyncMock()
    # No pre-existing station codes — every fixture should be inserted.
    session.execute = AsyncMock(return_value=scalars_all_result([]))

    await seeder._seed_stations(session)

    session.add_all.assert_called_once()
    stations = session.add_all.call_args[0][0]
    assert len(stations) == 11
    pune = [s for s in stations if s.city == "Pune"]
    mumbai = [s for s in stations if s.city == "Mumbai"]
    assert len(pune) == 8
    assert len(mumbai) == 3


@pytest.mark.asyncio
async def test_seed_stations_skips_already_existing_codes():
    """Idempotency: if `monitoring_stations` already has some of these
    fixture codes (e.g. a leftover Docker volume from a prior run that
    survived `docker compose down` without `-v`), re-seeding must skip
    exactly those rows rather than raising a duplicate-key error — this
    is the fix for the observed `ix_stations_code` conflict on
    `PUNE_001` that used to abort the whole seed transaction (and, with
    it, silently roll back the just-inserted admin/officer/inspector/
    citizen users, breaking login)."""
    session = make_db_session()
    session.flush = AsyncMock()
    session.execute = AsyncMock(
        return_value=scalars_all_result(["PUNE_001", "PUNE_002"])
    )

    await seeder._seed_stations(session)

    session.add_all.assert_called_once()
    stations = session.add_all.call_args[0][0]
    codes = {s.station_code for s in stations}
    assert "PUNE_001" not in codes
    assert "PUNE_002" not in codes
    assert len(stations) == 9


@pytest.mark.asyncio
async def test_seed_emission_sources_adds_all_sources():
    session = make_db_session()
    session.flush = AsyncMock()

    await seeder._seed_emission_sources(session)

    session.add_all.assert_called_once()
    sources = session.add_all.call_args[0][0]
    assert len(sources) == 8
    assert all(s.city == "Pune" for s in sources)


@pytest.mark.asyncio
async def test_seed_aqi_readings_generates_expected_volume_and_chunks():
    session = make_db_session()
    session.flush = AsyncMock()
    stations = [
        SimpleNamespace(
            id="s1",
            latitude=18.5,
            longitude=73.8,
            ward_id="W01",
            station_code="PUNE_001",
        ),
        SimpleNamespace(
            id="s2",
            latitude=18.6,
            longitude=73.9,
            ward_id="W04",
            station_code="PUNE_004",
        ),
    ]
    session.execute = AsyncMock(return_value=fetchall_result(stations))

    result_ids = await seeder._seed_aqi_readings(session)

    assert result_ids == ["s1", "s2"]
    total_readings = sum(len(call.args[0]) for call in session.add_all.call_args_list)
    assert total_readings == 169 * 2
    assert session.flush.await_count == session.add_all.call_count


@pytest.mark.asyncio
async def test_seed_forecasts_generates_grids_for_all_wards():
    session = make_db_session()
    session.flush = AsyncMock()

    await seeder._seed_forecasts(session)

    total_grids = sum(len(call.args[0]) for call in session.add_all.call_args_list)
    assert total_grids == 8 * 72


@pytest.mark.asyncio
async def test_seed_attributions_generates_expected_records():
    session = make_db_session()
    session.flush = AsyncMock()

    await seeder._seed_attributions(session)

    session.add_all.assert_called_once()
    records = session.add_all.call_args[0][0]
    assert len(records) == 8 * 8
    for r in records:
        assert 0.55 <= r.overall_confidence <= 0.90


@pytest.mark.asyncio
async def test_seed_anomalies_creates_two_events():
    session = make_db_session()
    session.flush = AsyncMock()
    stations = [
        SimpleNamespace(id="s-w07", ward_id="W07"),
        SimpleNamespace(id="s-w04", ward_id="W04"),
        SimpleNamespace(id="s-w01", ward_id="W01"),
    ]
    session.execute = AsyncMock(return_value=scalars_all_result(stations))

    await seeder._seed_anomalies(session, ["s-w07", "s-w04", "s-w01"])

    session.add_all.assert_called_once()
    events = session.add_all.call_args[0][0]
    assert len(events) == 2
    assert {e.ward_id for e in events} == {"W07", "W04"}


@pytest.mark.asyncio
async def test_seed_enforcement_creates_four_actions():
    session = make_db_session()
    session.flush = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            scalar_result("inspector-id"),
            scalar_result("officer-id"),
            fetchall_result([("src1",), ("src2",), ("src3",), ("src4",)]),
        ]
    )

    await seeder._seed_enforcement(session)

    session.add_all.assert_called_once()
    actions = session.add_all.call_args[0][0]
    assert len(actions) == 4


@pytest.mark.asyncio
async def test_seed_outcomes_returns_early_without_completed_action():
    session = make_db_session()
    session.execute = AsyncMock(return_value=scalar_result(None))

    await seeder._seed_outcomes(session)

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_seed_outcomes_creates_outcome_when_action_exists():
    session = make_db_session()
    session.flush = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[scalar_result("action-1"), scalar_result("verifier-1")]
    )

    await seeder._seed_outcomes(session)

    session.add.assert_called_once()
    outcome = session.add.call_args[0][0]
    assert outcome.action_id == "action-1"
    assert outcome.verified_by == "verifier-1"


@pytest.mark.asyncio
async def test_seed_policy_snapshots_creates_three_policies():
    session = make_db_session()
    session.flush = AsyncMock()

    await seeder._seed_policy_snapshots(session)

    session.add_all.assert_called_once()
    policies = session.add_all.call_args[0][0]
    assert len(policies) == 3
    assert {p.city for p in policies} == {"Pune", "Mumbai", "Delhi"}


@pytest.mark.asyncio
async def test_seed_alerts_creates_three_alerts():
    session = make_db_session()
    session.flush = AsyncMock()

    await seeder._seed_alerts(session)

    session.add_all.assert_called_once()
    alerts = session.add_all.call_args[0][0]
    assert len(alerts) == 3
    assert {a.language for a in alerts} == {"mr", "en", "hi"}
