"""Week 2 (A3): the drift checker must detect a deliberate ORM/migration mismatch."""

import json
import os
from importlib import import_module

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.weather import WeatherMeasurement
from app.tools import schema_drift as sd


def _db(meta: sa.MetaData):
    engine = sa.create_engine("sqlite://")
    meta.create_all(engine)
    return engine


def _meta(extra_col=False, extra_index=False, extra_table=False):
    m = sa.MetaData()
    t = sa.Table(
        "things",
        m,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(20), nullable=False),
        *([sa.Column("color", sa.String(10))] if extra_col else []),
    )
    if extra_index:
        sa.Index("ix_things_name", t.c.name)
    if extra_table:
        sa.Table("gadgets", m, sa.Column("id", sa.Integer, primary_key=True))
    return m


def test_aligned_schema_has_no_drift():
    engine = _db(_meta())
    with engine.connect() as c:
        assert sd.signatures_for(c, _meta()) == []


def test_deliberate_mismatch_is_detected_with_stable_signatures():
    engine = _db(_meta())  # "migrated" database
    with engine.connect() as c:
        sigs = sd.signatures_for(
            c, _meta(extra_col=True, extra_index=True, extra_table=True)
        )
    assert "add_column things.color" in sigs
    assert "add_index ix_things_name" in sigs
    assert "add_table gadgets" in sigs


def test_ignored_objects_are_not_reported():
    m = sa.MetaData()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as c:
        c.execute(sa.text("CREATE TABLE spatial_ref_sys (srid INTEGER PRIMARY KEY)"))
        c.execute(sa.text("CREATE TABLE t (id INTEGER PRIMARY KEY, ts TEXT)"))
        c.execute(sa.text("CREATE INDEX t_ts_timestamp_idx ON t (ts)"))
    with engine.connect() as c:
        sigs = sd.signatures_for(c, m)
    assert not any("spatial_ref_sys" in s or "timestamp_idx" in s for s in sigs)
    assert "remove_table t" in sigs


def test_baseline_comparison_reports_new_and_stale():
    new, stale = sd.diff_against_baseline(["a", "b", "c"], ["b", "c", "d"])
    assert new == ["a"] and stale == ["d"]
    assert sd.diff_against_baseline(["x"], ["x"]) == ([], [])


@pytest.fixture
def migrated_weather_connection():
    migration = import_module("db_migrations.versions.007_weather_measurements")
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            yield connection
    finally:
        engine.dispose()


def _weather_metadata():
    metadata = sa.MetaData()
    WeatherMeasurement.__table__.to_metadata(metadata)
    return metadata


def test_weather_model_matches_real_migration(migrated_weather_connection):
    assert Base.metadata.tables["weather_measurements"] is WeatherMeasurement.__table__
    assert sd.signatures_for(migrated_weather_connection, _weather_metadata()) == []
    inspector = sa.inspect(migrated_weather_connection)
    columns = {
        col["name"]: col for col in inspector.get_columns("weather_measurements")
    }
    for name in ("created_at", "updated_at"):
        model_column = WeatherMeasurement.__table__.c[name]
        assert columns[name]["nullable"] is True
        assert model_column.nullable is True
        assert model_column.type.timezone is True
        assert columns[name]["default"] == "CURRENT_TIMESTAMP"
        assert (
            str(model_column.server_default.arg.compile(dialect=postgresql.dialect()))
            == "now()"
        )
        assert model_column.default is None
    assert str(WeatherMeasurement.__table__.c.updated_at.onupdate.arg) == "now()"
    assert inspector.get_pk_constraint("weather_measurements")[
        "constrained_columns"
    ] == ["id"]
    assert inspector.get_foreign_keys("weather_measurements") == []
    assert {
        index["name"]: index["column_names"]
        for index in inspector.get_indexes("weather_measurements")
    } == {
        "ix_weather_measurements_city": ["city"],
        "ix_weather_measurements_observed_at": ["observed_at"],
    }
    assert inspector.get_unique_constraints("weather_measurements") == [
        {
            "name": "uq_weather_city_time_source",
            "column_names": ["city", "observed_at", "source"],
        }
    ]


def test_weather_preserves_nullable_rows_and_server_defaults(
    migrated_weather_connection,
):
    from datetime import UTC, datetime

    table = WeatherMeasurement.__table__
    now = datetime.now(UTC)
    values = {
        "city": "Schema test",
        "latitude": 18.5,
        "longitude": 73.8,
        "observed_at": now,
        "fetched_at": now,
    }
    migrated_weather_connection.execute(
        table.insert().values(
            **values, source="legacy", created_at=sa.null(), updated_at=sa.null()
        )
    )
    migrated_weather_connection.execute(table.insert().values(**values, source="new"))
    with Session(bind=migrated_weather_connection) as session:
        legacy = session.scalars(
            sa.select(WeatherMeasurement).where(table.c.source == "legacy")
        ).one()
        assert legacy.created_at is None
        assert legacy.updated_at is None
        fresh = session.scalars(
            sa.select(WeatherMeasurement).where(table.c.source == "new")
        ).one()
        assert fresh.created_at is not None
        assert fresh.updated_at is not None


def test_weather_metadata_omission_explains_stale_baseline(migrated_weather_connection):
    legacy_signatures = sd.signatures_for(migrated_weather_connection, sa.MetaData())
    assert legacy_signatures == [
        "remove_index ix_weather_measurements_city",
        "remove_index ix_weather_measurements_observed_at",
        "remove_table weather_measurements",
    ]
    baseline = json.loads(sd.BASELINE_PATH.read_text())["signatures"]
    assert not set(legacy_signatures).intersection(baseline)
    assert not any("weather_measurements" in entry for entry in baseline)


def test_weather_nullability_regression_is_not_suppressed(migrated_weather_connection):
    metadata = _weather_metadata()
    for name in ("created_at", "updated_at"):
        metadata.tables["weather_measurements"].c[name].nullable = False
    signatures = sd.signatures_for(migrated_weather_connection, metadata)
    assert signatures == [
        "modify_nullable weather_measurements.created_at",
        "modify_nullable weather_measurements.updated_at",
    ]
    baseline = json.loads(sd.BASELINE_PATH.read_text())["signatures"]
    new, _ = sd.diff_against_baseline(signatures, baseline)
    assert new == signatures


@pytest.mark.skipif(
    not os.environ.get("MIGRATED_DATABASE_URL"),
    reason="needs a database with `alembic upgrade head` applied (set MIGRATED_DATABASE_URL)",
)
@pytest.mark.asyncio
async def test_real_migrated_schema_matches_committed_baseline():
    import json

    current = await sd._current_signatures(os.environ["MIGRATED_DATABASE_URL"])
    baseline = json.loads(sd.BASELINE_PATH.read_text())["signatures"]
    new, stale = sd.diff_against_baseline(current, baseline)
    assert not new, f"new migration-vs-ORM drift: {new[:10]}"
    assert not stale, f"stale baseline entries (remove them): {stale[:10]}"
