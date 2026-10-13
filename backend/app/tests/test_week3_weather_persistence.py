from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.weather import WeatherMeasurement
from app.services.weather_persistence import map_open_meteo_hourly, persist_weather_rows

_FETCHED = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)


def _payload(times, **series) -> dict:
    hourly = {"time": times}
    hourly.update(series)
    return {"hourly": hourly}


def _map(payload, **kwargs) -> list[WeatherMeasurement]:
    defaults = dict(city="Pune", latitude=18.52, longitude=73.86, fetched_at=_FETCHED)
    defaults.update(kwargs)
    return map_open_meteo_hourly(payload, **defaults)


class TestMapOpenMeteoHourly:
    def test_maps_all_fields_with_provider_timestamp(self):
        rows = _map(
            _payload(
                ["2026-01-10T00:00", "2026-01-10T01:00"],
                temperature_2m=[21.5, 22.0],
                relative_humidity_2m=[60, 61],
                wind_speed_10m=[8.2, 9.1],
                wind_direction_10m=[240, 250],
                precipitation=[0.0, 1.2],
                surface_pressure=[1012.0, 1011.5],
                weather_code=[1, 3],
            )
        )
        assert len(rows) == 2
        r = rows[0]
        assert r.observed_at == datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
        assert r.fetched_at == _FETCHED
        assert r.temperature == 21.5
        assert r.humidity == 60.0
        assert r.wind_speed == 8.2
        assert r.wind_direction == 240.0
        assert r.precipitation == 0.0
        assert r.pressure == 1012.0
        assert r.weather_code == 1
        assert r.source == "open_meteo"
        assert r.is_forecast is True
        assert r.city == "Pune"

    def test_new_measurements_are_not_deleted(self):
        rows = _map(_payload(["2026-01-10T00:00"]))
        assert rows[0].is_deleted is False
        assert rows[0].deleted_at is None

    def test_missing_hourly_or_time_returns_empty(self):
        assert _map({}) == []
        assert _map({"hourly": None}) == []
        assert _map({"hourly": {"time": None}}) == []
        assert _map({"hourly": "not-a-dict"}) == []

    def test_unparseable_timestamps_are_skipped_not_fatal(self):
        rows = _map(_payload(["not-a-time", "2026-01-10T01:00"], temperature_2m=[1, 2]))
        assert len(rows) == 1
        assert rows[0].observed_at.hour == 1

    def test_missing_scalar_fields_become_none_never_fabricated(self):
        rows = _map(_payload(["2026-01-10T00:00"], temperature_2m=[20.0]))
        assert rows[0].temperature == 20.0
        assert rows[0].humidity is None
        assert rows[0].pressure is None
        assert rows[0].weather_code is None

    def test_short_series_does_not_index_error(self):
        rows = _map(
            _payload(
                ["2026-01-10T00:00", "2026-01-10T01:00"],
                temperature_2m=[20.0],  # shorter than time
            )
        )
        assert len(rows) == 2
        assert rows[1].temperature is None

    def test_duplicate_timestamps_dedupe_to_last(self):
        rows = _map(
            _payload(
                ["2026-01-10T00:00", "2026-01-10T00:00"],
                temperature_2m=[10.0, 20.0],
            )
        )
        assert len(rows) == 1
        assert rows[0].temperature == 20.0

    def test_naive_times_are_utc_and_aware_times_convert(self):
        rows = _map(_payload(["2026-01-10T05:30"]))
        assert rows[0].observed_at == datetime(2026, 1, 10, 5, 30, tzinfo=UTC)
        rows = _map(_payload(["2026-01-10T05:30+05:30"]))
        assert rows[0].observed_at == datetime(2026, 1, 10, 0, 0, tzinfo=UTC)

    def test_non_numeric_scalar_becomes_none(self):
        rows = _map(_payload(["2026-01-10T00:00"], temperature_2m=["hot"]))
        assert rows[0].temperature is None


class TestWeatherUpsertPayload:
    @pytest.mark.parametrize("is_deleted", [None, False, True])
    async def test_normalizes_defaults_and_preserves_explicit_deletion(
        self, is_deleted
    ):
        row = WeatherMeasurement(
            city="Pune",
            latitude=18.52,
            longitude=73.86,
            observed_at=_FETCHED,
            fetched_at=_FETCHED,
            source="open_meteo",
            is_forecast=True,
            is_deleted=is_deleted,
            deleted_at=_FETCHED,
        )
        session = AsyncMock()
        assert await persist_weather_rows(session, [row]) == 1
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()
        statement = session.execute.call_args.args[0]
        compiled = statement.compile(dialect=postgresql.dialect())
        assert compiled.params["is_deleted_m0"] is (is_deleted is True)
        assert compiled.params["deleted_at_m0"] == (_FETCHED if is_deleted else None)
        assert "created_at_m0" not in compiled.params
        assert "updated_at_m0" not in compiled.params
        assert "ON CONFLICT ON CONSTRAINT uq_weather_city_time_source" in str(compiled)

    async def test_mixed_batch_has_non_null_flags(self):
        rows = _map(_payload(["2026-01-10T00:00", "2026-01-10T01:00"]))
        rows[0].is_deleted = None
        rows[1].is_deleted = True
        rows[1].deleted_at = _FETCHED
        session = AsyncMock()
        assert await persist_weather_rows(session, rows) == 2
        compiled = session.execute.call_args.args[0].compile(
            dialect=postgresql.dialect()
        )
        assert compiled.params["is_deleted_m0"] is False
        assert compiled.params["deleted_at_m0"] is None
        assert compiled.params["is_deleted_m1"] is True
        assert compiled.params["deleted_at_m1"] == _FETCHED


@pytest.mark.integration
class TestPersistWeatherRows:
    async def test_upsert_is_idempotent_and_refreshes(self, db_session):
        rows = _map(
            _payload(
                ["2026-01-10T00:00", "2026-01-10T01:00"],
                temperature_2m=[20.0, 21.0],
                relative_humidity_2m=[60.0, 61.0],
            )
        )
        assert await persist_weather_rows(db_session, rows) == 2
        flags = (
            await db_session.execute(
                select(WeatherMeasurement.is_deleted, WeatherMeasurement.deleted_at)
            )
        ).all()
        assert flags == [(False, None), (False, None)]
        # Re-ingest the same hours with revised forecast values — must
        # update, not duplicate (uq_weather_city_time_source).
        revised = _map(
            _payload(
                ["2026-01-10T00:00", "2026-01-10T01:00"],
                temperature_2m=[99.0, 98.0],
                relative_humidity_2m=[70.0, 71.0],
            )
        )
        assert await persist_weather_rows(db_session, revised) == 2

        from sqlalchemy import func

        count = await db_session.scalar(
            select(func.count())
            .select_from(WeatherMeasurement)
            .where(
                WeatherMeasurement.city == "Pune",
                WeatherMeasurement.source == "open_meteo",
            )
        )
        assert count == 2
        saved = await db_session.scalar(
            select(WeatherMeasurement.temperature).where(
                WeatherMeasurement.city == "Pune",
                WeatherMeasurement.observed_at == datetime(2026, 1, 10, tzinfo=UTC),
            )
        )
        assert saved == 99.0
        humidity = await db_session.scalar(
            select(WeatherMeasurement.humidity).where(
                WeatherMeasurement.observed_at == datetime(2026, 1, 10, tzinfo=UTC)
            )
        )
        assert humidity == 70.0

    @pytest.mark.parametrize("initially_deleted", [False, True])
    async def test_explicit_deletion_survives_reingestion(
        self, db_session, initially_deleted
    ):
        rows = _map(_payload(["2026-01-10T00:00"], temperature_2m=[20.0]))
        rows[0].is_deleted = initially_deleted
        rows[0].deleted_at = _FETCHED if initially_deleted else None
        assert await persist_weather_rows(db_session, rows) == 1
        if not initially_deleted:
            rows[0].is_deleted = True
            rows[0].deleted_at = _FETCHED
            assert await persist_weather_rows(db_session, rows) == 1
        stored = (
            await db_session.execute(
                select(WeatherMeasurement.is_deleted, WeatherMeasurement.deleted_at)
            )
        ).one()
        assert stored == (True, _FETCHED)
        revised = _map(_payload(["2026-01-10T00:00"], temperature_2m=[99.0]))
        assert await persist_weather_rows(db_session, revised) == 1
        stored = (
            await db_session.execute(
                select(
                    WeatherMeasurement.temperature,
                    WeatherMeasurement.is_deleted,
                    WeatherMeasurement.deleted_at,
                )
            )
        ).one()
        assert stored == (99.0, True, _FETCHED)

    async def test_unset_defaults_on_directly_constructed_row(self, db_session):
        row = WeatherMeasurement(
            city="Pune",
            latitude=18.52,
            longitude=73.86,
            observed_at=_FETCHED,
            fetched_at=_FETCHED,
            source="open_meteo",
            is_forecast=True,
        )
        assert row.is_deleted is None
        assert await persist_weather_rows(db_session, [row]) == 1
        stored = (
            await db_session.execute(
                select(WeatherMeasurement.is_deleted, WeatherMeasurement.deleted_at)
            )
        ).one()
        assert stored == (False, None)
