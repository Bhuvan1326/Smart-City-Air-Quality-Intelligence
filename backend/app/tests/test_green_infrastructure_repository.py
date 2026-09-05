"""Tests for AQIReadingRepository.get_latest_valid_by_station — the
synthetic-and-invalid-excluding lookup Green Infrastructure Optimization
uses instead of the generic get_latest_by_station (see
app/api/v1/endpoints/green_infrastructure.py).

Uses a minimal fake AsyncSession that records the compiled SQL rather than
a live Postgres connection (same approach as
test_aqi_history_filtering.py), since this sandbox has no live DB. This
verifies the query itself excludes synthetic/invalid rows; the
DB-dependent behavioural check lives in
test_green_infrastructure_endpoint.py.
"""

from uuid import uuid4

import pytest

from app.repositories.aqi import AQIReadingRepository


class _FakeScalarResult:
    def scalar_one_or_none(self):
        return None


class _RecordingSession:
    def __init__(self):
        self.last_statement = None

    async def execute(self, stmt, params=None):
        self.last_statement = stmt
        return _FakeScalarResult()


@pytest.mark.asyncio
async def test_get_latest_valid_by_station_excludes_synthetic_and_invalid():
    session = _RecordingSession()
    repo = AQIReadingRepository(session)

    await repo.get_latest_valid_by_station(uuid4())

    sql = str(session.last_statement)
    assert "quality_flag" in sql
    # Compiled SQLAlchemy NOT IN renders as "NOT IN" against a bound
    # expanding parameter list — assert the exclusion clause is present
    # rather than the literal values (which aren't inlined into the SQL
    # text at compile time).
    assert "NOT IN" in sql.upper()


@pytest.mark.asyncio
async def test_get_latest_valid_by_station_orders_by_timestamp_desc_limit_one():
    session = _RecordingSession()
    repo = AQIReadingRepository(session)

    await repo.get_latest_valid_by_station(uuid4())

    sql = str(session.last_statement)
    assert "ORDER BY" in sql.upper()
    assert "DESC" in sql.upper()
    assert "LIMIT" in sql.upper()
