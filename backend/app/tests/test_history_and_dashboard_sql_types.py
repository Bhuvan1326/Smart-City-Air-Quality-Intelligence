"""Regression tests for two real-Postgres SQL-typing bugs found during
Docker runtime verification of the Live AQI feature:

1. GET /api/v1/aqi/history — `time_bucket(:interval, ...)` bound the
   `:interval` parameter as an untyped string ("1 hour"), which asyncpg
   sends to Postgres without a type OID. Postgres's `time_bucket`
   overload resolution needs a real `interval`, so it raised
   `asyncpg.exceptions.DataError: invalid input for query argument $1:
   '1 hour' ('str' object has no attribute 'days')`. Fix: cast the bound
   parameter explicitly with `:interval::interval`.

2. GET /api/v1/dashboard/overview — `get_city_average_aqi_around` built
   `(:hours_ago + :half_window) * INTERVAL '1 hour'` with two untyped
   numeric parameters. Postgres couldn't resolve `unknown + unknown` and
   raised `asyncpg.exceptions.AmbiguousFunctionError: operator is not
   unique: unknown + unknown`. Fix: cast both parameters explicitly with
   `::double precision`.

These are both real-Postgres SQL-typing issues that don't surface with
mocked sessions (`make_db_session()` in test_aqi_history_filtering.py),
so these tests use the `db_session`/`client` fixtures and are
auto-marked `integration` by conftest.py's `pytest_collection_modifyitems`
— they only run with `TEST_DATABASE_URL`/`DATABASE_URL` pointing at a
real Postgres (e.g. `pytest -vv`, not `pytest -m "not integration"`).
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import AQIReading, MonitoringStation, QualityFlag
from app.repositories.aqi import AQIReadingRepository

pytestmark = pytest.mark.asyncio


async def _make_station(
    db_session: AsyncSession, *, city: str = "Pune"
) -> MonitoringStation:
    from geoalchemy2.elements import WKTElement

    station = MonitoringStation(
        name="Test Regression Station",
        station_code=f"TEST_REGRESSION_{datetime.now(UTC).timestamp()}",
        city=city,
        country="India",
        operator="Test",
        latitude=18.52,
        longitude=73.85,
        geometry=WKTElement("POINT(73.85 18.52)", srid=4326),
        station_type="test",
    )
    db_session.add(station)
    await db_session.commit()
    await db_session.refresh(station)
    return station


async def _add_reading(
    db_session: AsyncSession, station: MonitoringStation, *, aqi: int, hours_ago: float
) -> None:
    reading = AQIReading(
        station_id=station.id,
        aqi=aqi,
        pm25=aqi * 0.5,
        timestamp=datetime.now(UTC) - timedelta(hours=hours_ago),
        latitude=station.latitude,
        longitude=station.longitude,
        quality_flag=QualityFlag.GOOD,
    )
    db_session.add(reading)
    await db_session.commit()


class TestHistoryIntervalCastRealPostgres:
    """get_history must not raise asyncpg.exceptions.DataError for any
    of the intervals the API actually accepts."""

    @pytest.mark.parametrize("interval", ["15m", "1h", "6h", "24h"])
    async def test_station_scoped_history_accepts_every_supported_interval(
        self, db_session: AsyncSession, interval: str
    ):
        station = await _make_station(db_session)
        await _add_reading(db_session, station, aqi=80, hours_ago=1)

        repo = AQIReadingRepository(db_session)
        # Must not raise — this is the exact code path that previously
        # raised asyncpg.exceptions.DataError.
        rows = await repo.get_history(
            station.id,
            datetime.now(UTC) - timedelta(hours=48),
            datetime.now(UTC),
            interval=interval,
        )
        assert isinstance(rows, list)

    @pytest.mark.parametrize("interval", ["15m", "1h", "6h", "24h"])
    async def test_city_scoped_history_accepts_every_supported_interval(
        self, db_session: AsyncSession, interval: str
    ):
        station = await _make_station(db_session)
        await _add_reading(db_session, station, aqi=80, hours_ago=1)

        repo = AQIReadingRepository(db_session)
        rows = await repo.get_history(
            None,
            datetime.now(UTC) - timedelta(hours=48),
            datetime.now(UTC),
            interval=interval,
            city="Pune",
        )
        assert isinstance(rows, list)

    async def test_history_endpoint_1h_does_not_500(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.get(
            "/api/v1/aqi/history?city=Pune&interval=1h", headers=auth_headers
        )
        assert resp.status_code != 500
        assert resp.status_code == 200

    async def test_history_endpoint_15m_does_not_500(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.get(
            "/api/v1/aqi/history?city=Pune&interval=15m", headers=auth_headers
        )
        assert resp.status_code != 500
        assert resp.status_code == 200

    async def test_history_endpoint_rejects_invalid_interval_safely(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Invalid intervals must be rejected by FastAPI's query-param
        validation (422) before ever reaching the database — never a raw
        500 from a malformed SQL string."""
        resp = await client.get(
            "/api/v1/aqi/history?city=Pune&interval=DROP TABLE aqi_readings;--",
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_history_endpoint_rejects_unsupported_but_wellformed_interval(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.get(
            "/api/v1/aqi/history?city=Pune&interval=3h", headers=auth_headers
        )
        assert resp.status_code == 422


class TestDashboardOverviewArithmeticRealPostgres:
    """get_city_average_aqi_around must not raise
    asyncpg.exceptions.AmbiguousFunctionError."""

    async def test_get_city_average_aqi_around_does_not_raise(
        self, db_session: AsyncSession
    ):
        station = await _make_station(db_session)
        await _add_reading(db_session, station, aqi=90, hours_ago=24)

        repo = AQIReadingRepository(db_session)
        # Exact call the dashboard overview endpoint makes: hours_ago=24,
        # default window_hours=1.0 -> half_window=0.5, previously
        # triggered "operator is not unique: unknown + unknown".
        result = await repo.get_city_average_aqi_around(station.city, hours_ago=24)
        assert result is None or isinstance(result, float)

    async def test_dashboard_overview_endpoint_does_not_500(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        station = await _make_station(db_session)
        await _add_reading(db_session, station, aqi=95, hours_ago=24)

        resp = await client.get(
            "/api/v1/dashboard/overview?city=Pune", headers=auth_headers
        )
        assert resp.status_code != 500
        assert resp.status_code == 200
