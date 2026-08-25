"""Tests for AQIReadingRepository.get_history's city/station/ward filtering.

Real bug being regression-tested: the endpoint accepted and validated
`city`/`ward_id` query params but silently discarded them before calling
the repository, so the "city-wide" branch actually aggregated every
station across every city together.

These tests don't require a live Postgres connection — they use a minimal
fake AsyncSession that records the exact SQL text and bound parameters
`get_history` sends, so we can verify the query is actually scoped
correctly without needing a real database. This complements (not
replaces) real integration testing against Postgres, which would be
needed to verify the query executes correctly and returns the right rows
— that requires a live DB this sandbox doesn't have.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.repositories.aqi import AQIReadingRepository


class _FakeResult:
    def __iter__(self):
        return iter([])


class _RecordingSession:
    """Records the last statement/params passed to execute(), never
    actually touches a database."""

    def __init__(self):
        self.last_statement = None
        self.last_params = None

    async def execute(self, stmt, params=None):
        self.last_statement = stmt
        self.last_params = params or {}
        return _FakeResult()


NOW = datetime.now(UTC)
START = NOW
END = NOW


@pytest.mark.asyncio
async def test_city_filter_joins_stations_and_binds_city():
    session = _RecordingSession()
    repo = AQIReadingRepository(session)
    await repo.get_history(None, START, END, city="Pune")

    sql = str(session.last_statement)
    assert "JOIN monitoring_stations s" in sql
    assert "s.city = :city" in sql
    assert session.last_params["city"] == "Pune"


@pytest.mark.asyncio
async def test_ward_id_adds_extra_clause_only_when_given():
    session = _RecordingSession()
    repo = AQIReadingRepository(session)

    await repo.get_history(None, START, END, city="Pune", ward_id="W06")
    sql_with_ward = str(session.last_statement)
    assert "s.ward_id = :ward_id" in sql_with_ward
    assert session.last_params["ward_id"] == "W06"

    await repo.get_history(None, START, END, city="Pune")
    sql_without_ward = str(session.last_statement)
    assert "s.ward_id = :ward_id" not in sql_without_ward
    assert "ward_id" not in session.last_params


@pytest.mark.asyncio
async def test_station_filter_does_not_join_or_filter_by_city():
    session = _RecordingSession()
    repo = AQIReadingRepository(session)
    station_id = uuid4()
    await repo.get_history(station_id, START, END)

    sql = str(session.last_statement)
    assert "JOIN monitoring_stations" not in sql
    assert "station_id = :station_id" in sql
    assert session.last_params["station_id"] == station_id


@pytest.mark.asyncio
async def test_missing_both_city_and_station_raises_before_any_query():
    session = _RecordingSession()
    repo = AQIReadingRepository(session)
    with pytest.raises(ValueError):
        await repo.get_history(None, START, END)
    # Confirms the function fails fast rather than silently running an
    # unscoped, all-cities query — the exact original bug.
    assert session.last_statement is None


@pytest.mark.asyncio
async def test_interval_is_mapped_to_a_valid_postgres_interval():
    session = _RecordingSession()
    repo = AQIReadingRepository(session)
    await repo.get_history(None, START, END, interval="6h", city="Pune")
    assert session.last_params["interval"] == "6 hours"


@pytest.mark.asyncio
async def test_empty_result_from_fake_session_returns_empty_list():
    session = _RecordingSession()
    repo = AQIReadingRepository(session)
    result = await repo.get_history(None, START, END, city="Pune")
    assert result == []
