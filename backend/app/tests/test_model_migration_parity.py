import uuid
from pathlib import Path

import anyio
import pytest
import pytest_asyncio
from sqlalchemy import create_engine, inspect, text

from app.core.config import settings
from app.core.database import Base

# Import every model module so all subclasses are registered on
# Base.metadata before we introspect it.
from app.models import (  # noqa: F401
    analytics,
    civic_issue,
    emission_source,
    enforcement,
    monitoring,
    user,
)

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def _run_alembic_upgrade(database_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "db_migrations"))
    original_url = settings.DATABASE_URL
    settings.DATABASE_URL = database_url  # db_migrations/env.py reads this
    try:
        # Migration 003 is pure TimescaleDB optimization (continuous
        # aggregates, compression/retention policies) -- it needs the
        # real TimescaleDB extension, only available via the project's
        # Docker image, and creates no tables/columns of its own, so it
        # contributes nothing to the column-parity check this test runs.
        # Apply up to 002, stamp past 003, then continue normally so the
        # rest of the schema (004+) still gets built and checked.
        command.upgrade(cfg, "002_phase_features")
        command.stamp(cfg, "003_timescaledb_optimization")
        command.upgrade(cfg, "head")
    finally:
        settings.DATABASE_URL = original_url


@pytest_asyncio.fixture(scope="function")
async def migrated_schema_columns() -> dict[str, set[str]]:
    """Runs the real Alembic migration chain into a throwaway database
    and returns {table_name: {column_name, ...}} as actually created --
    the production source of truth."""
    db_name = f"parity_test_{uuid.uuid4().hex[:8]}"
    admin_sync_url = settings.sync_database_url

    admin_engine = create_engine(admin_sync_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()

    base_url = admin_sync_url.rsplit("/", 1)[0]
    test_db_async_url = (
        base_url.replace("postgresql://", "postgresql+asyncpg://") + f"/{db_name}"
    )
    test_db_sync_url = base_url + f"/{db_name}"

    setup_engine = create_engine(test_db_sync_url)
    with setup_engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        has_timescaledb = conn.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'")
        ).first()
        if not has_timescaledb:
            conn.execute(text("""
                    CREATE OR REPLACE FUNCTION create_hypertable(
                        relation regclass, time_column_name name,
                        if_not_exists boolean DEFAULT false
                    ) RETURNS void AS $$ BEGIN END; $$ LANGUAGE plpgsql;
                    """))
        conn.commit()
    setup_engine.dispose()

    try:
        await anyio.to_thread.run_sync(_run_alembic_upgrade, test_db_async_url)

        inspect_engine = create_engine(test_db_sync_url)
        with inspect_engine.connect() as conn:
            inspector = inspect(conn)
            columns = {
                table: {c["name"] for c in inspector.get_columns(table)}
                for table in inspector.get_table_names()
            }
        inspect_engine.dispose()
        return columns
    finally:
        admin_engine = create_engine(admin_sync_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        admin_engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_every_orm_column_exists_in_migrated_schema(migrated_schema_columns):
    """For every mapped model, every column it declares must exist,
    under its actual (possibly overridden) name, in the table the real
    Alembic migrations produce. This is the check that would have
    caught `EmissionSource.extra_data` -> missing "metadata" column
    before it ever reached production, instead of only surfacing as a
    500 on the live Construction & Dust page."""
    mismatches = []

    for mapper in Base.registry.mappers:
        table = mapper.local_table
        if table is None or table.name not in migrated_schema_columns:
            continue
        migrated_columns = migrated_schema_columns[table.name]
        for column in table.columns:
            if column.name not in migrated_columns:
                mismatches.append(
                    f"{table.name}.{column.name} (model: {mapper.class_.__name__})"
                )

    assert not mismatches, (
        "ORM columns with no matching column in the Alembic-migrated schema "
        "(this is the bug class that broke Construction & Dust Intelligence):\n  "
        + "\n  ".join(sorted(mismatches))
    )
