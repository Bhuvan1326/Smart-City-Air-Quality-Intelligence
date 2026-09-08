import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.redis_client import reset_redis_client
from app.core.security import hash_password
from app.main import app
from app.models.user import User, UserRole

# TEST_DATABASE_URL is intentionally the *only* environment variable this
# module trusts for the test connection string. It used to also fall back
# to the generic DATABASE_URL, but DATABASE_URL is not a portable value:
# CI's postgres service publishes on 5432 (see .github/workflows/ci.yml),
# while local `docker compose` deliberately publishes the same container
# port on host port 5434 instead (see docker-compose.yml's `db.ports`) so
# it never collides with a native/Windows PostgreSQL install that may
# already be listening on 5432. A developer who exports DATABASE_URL
# locally (e.g. copying the value CI uses, or a leftover from a native
# Postgres setup) would silently redirect this fixture at port 5432,
# where nothing is listening once you've moved to Docker Postgres on
# 5434 — producing exactly a WinError 1225 / ConnectionRefusedError
# *before* any test body runs, since it fails inside `engine.begin()`
# below. Only TEST_DATABASE_URL — a name nothing else in this codebase
# sets or reads — is honored, so the only way to change where tests
# point is to explicitly opt in with that name.
_default_test_host = "db:5432" if os.path.exists("/.dockerenv") else "localhost:5434"
TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    f"postgresql+asyncpg://airuser:airpass@{_default_test_host}/airquality_test",
)

# A handful of tests (e.g. test_aqi_pune_live.py's Celery-entry-point
# test) deliberately build their own engine straight from
# settings.DATABASE_URL, to exercise the exact code path
# app.workers.tasks.aqi_ingestion uses in production, rather than going
# through the db_session/client fixtures. In Docker that variable is
# correctly set per-service (see docker-compose.yml); outside Docker it
# otherwise falls back to Settings' own class default, which — like the
# old TEST_DB_URL fallback this replaces — targets port 5432, not this
# project's local Docker Compose port 5434. Keeping settings.DATABASE_URL
# in sync with TEST_DB_URL for the lifetime of this pytest process (this
# only mutates the in-process Settings singleton; it has no effect on the
# already-running Docker containers) means every DB-backed test targets
# the one real test database, whichever way it gets there.
settings.DATABASE_URL = TEST_DB_URL


async def _ensure_test_database_exists(db_url: str) -> None:
    """Creates the target database (e.g. `airquality_test`) if it doesn't
    exist yet.

    docker-compose.yml's `db` service only seeds POSTGRES_DB (`airquality`,
    for the application) on first container init — it has no knowledge of
    a separate `airquality_test` database, so on a Docker volume that
    predates this fixture (or was only ever used for `airquality`),
    `airquality_test` genuinely does not exist yet. Rather than requiring
    a manual `CREATE DATABASE` step on every fresh machine/volume, connect
    to the server's always-present `postgres` maintenance database and
    create it here, idempotently. This talks to the same Docker Postgres
    instance TEST_DB_URL already points at — it does not open any new
    host/port, so it doesn't change *where* tests connect, only ensures
    the specific database is there once they do.
    """
    target = make_url(db_url)
    db_name = target.database
    try:
        conn = await asyncpg.connect(
            host=target.host,
            port=target.port,
            user=target.username,
            password=target.password,
            database="postgres",
        )
    except (OSError, ConnectionRefusedError) as exc:
        raise ConnectionError(
            f"Could not reach PostgreSQL at {target.host}:{target.port} to "
            f"prepare the test database '{db_name}'. Confirm the Docker "
            "Postgres container is running and its port is published to "
            "the host (docker-compose.yml maps db -> 0.0.0.0:5434), and "
            "that no TEST_DATABASE_URL override is pointing somewhere "
            "else."
        ) from exc

    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", db_name
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()

    # A freshly-created database has no extensions. The models rely on
    # PostGIS's `geometry` column type (see e.g. app/models/monitoring.py,
    # app/models/emission_source.py) — the same extension
    # `scripts/init_db.sql` enables for the main `airquality` database,
    # which never runs against a separately-created `airquality_test`.
    # `uuid-ossp` / `pg_trgm` are enabled too for parity with that script.
    # This is idempotent (`IF NOT EXISTS`) so it's safe to run every test.
    conn = await asyncpg.connect(
        host=target.host,
        port=target.port,
        user=target.username,
        password=target.password,
        database=db_name,
    )
    try:
        for extension in ("uuid-ossp", "postgis", "pg_trgm"):
            await conn.execute(f'CREATE EXTENSION IF NOT EXISTS "{extension}"')
    finally:
        await conn.close()


@pytest_asyncio.fixture(autouse=True)
async def _reset_redis_client_per_test():
    """Ensures app.core.redis_client's module-level Redis singleton is
    never reused across two different tests' event loops (see
    reset_redis_client's docstring for why that matters). A no-op for
    tests that never touch Redis, since the singleton is only ever
    created lazily on first use — this fixture does not itself require
    Redis to be available.
    """
    await reset_redis_client()
    yield
    await reset_redis_client()


def make_db_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    return session


def make_session_cm(session):
    cm = AsyncMock()
    cm.__aenter__.return_value = session
    cm.__aexit__.return_value = False
    return cm


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Real Postgres-backed engine for DB-dependent tests only.

    Only created when a test actually requests `db_session` or `client`
    (directly, or transitively via `test_admin`/`admin_token`/
    `auth_headers`, which all depend on one of those). Tests that never
    request any of those fixtures never trigger engine creation, so
    PostgreSQL availability is only required for tests that genuinely
    exercise database behavior — this fixture is intentionally NOT
    autouse.

    Function scope means the full schema is created fresh and dropped
    again for every test that uses it, which already guarantees complete
    isolation between tests without needing a separate table-truncation
    step (a redundant autouse `_clean_tables` fixture previously existed
    here and was removed — it added a second Postgres connection per test
    for no additional isolation guarantee, and being autouse, it also
    silently required Postgres for every pure-logic test in this
    directory, which was the actual bug: unit tests like AQI/health-risk/
    recommendation/route calculations failed merely because Postgres was
    unavailable, despite never touching a database).
    """
    await _ensure_test_database_exists(TEST_DB_URL)

    engine = create_async_engine(TEST_DB_URL, echo=False, pool_pre_ping=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        # Plain Base.metadata.drop_all() issues an unqualified DROP TABLE,
        # which Postgres refuses for aqi_readings: it's a TimescaleDB
        # hypertable with continuous-aggregate views
        # (_timescaledb_internal._partial_view_3 / _direct_view_3) still
        # depending on it. Without CASCADE, that DROP TABLE fails, the
        # schema is left dirty, and every subsequent test in the run then
        # fails at setup (duplicate-key errors from leftover rows) —
        # so drop every table explicitly with CASCADE instead.
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f'DROP TABLE IF EXISTS "{table.name}" CASCADE'))

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:

    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(test_engine) -> AsyncGenerator[AsyncClient, None]:
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    # AuditLogMiddleware doesn't go through Depends(get_db) — it can't,
    # middleware isn't part of FastAPI's dependency-injection graph — so
    # it reads its session factory from app.state instead (see
    # app/core/middleware.py). Without this, the middleware would fall
    # back to the real app.core.database.AsyncSessionLocal, a
    # module-level engine created once at import time and bound to
    # whichever event loop was running then; reusing it from a later
    # test's (different) event loop is exactly what produced the
    # "Future attached to a different loop" / MissingGreenlet failures
    # seen in CI on every mutating (POST/PATCH/PUT/DELETE) request, since
    # only those trigger AuditLogMiddleware's DB write.
    app.state.async_session_factory = session_factory

    # RateLimitMiddleware's 60-requests/minute-per-IP limit is real and
    # Redis-backed (RATE_LIMIT_ENABLED defaults True in production too —
    # this is not weakening the feature). Every test client request goes
    # through ASGITransport, which has no real client IP, so every test
    # in a run shares one IP; a full-suite run easily exceeds 60 requests
    # within a rolling minute, producing 429s on tests that have nothing
    # to do with rate limiting. No test in this suite exercises
    # RateLimitMiddleware's behavior directly, so disabling it here is
    # scoped precisely to that gap rather than hiding a real failure.
    original_rate_limit_enabled = settings.RATE_LIMIT_ENABLED
    settings.RATE_LIMIT_ENABLED = False

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    settings.RATE_LIMIT_ENABLED = original_rate_limit_enabled
    app.dependency_overrides.clear()
    if hasattr(app.state, "async_session_factory"):
        del app.state.async_session_factory


@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession) -> User:
    user = User(
        email="test_admin@pune.gov.in",
        hashed_password=hash_password("Admin@123"),
        full_name="Test Admin",
        role=UserRole.CITY_ADMINISTRATOR,
        city="Pune",
        is_active=True,
    )

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    return user


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient, test_admin: User) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "test_admin@pune.gov.in",
            "password": "Admin@123",
        },
    )

    return resp.json()["data"]["access_token"]


@pytest_asyncio.fixture
async def auth_headers(admin_token: str) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


_DB_FIXTURE_NAMES = {
    "db_session",
    "client",
    "test_admin",
    "admin_token",
    "auth_headers",
}


def pytest_collection_modifyitems(items):
    """Auto-label every test that requests a DB fixture (directly or
    transitively) with @pytest.mark.integration, so `pytest -m "not
    integration"` reliably runs only Postgres-free tests without anyone
    having to hand-annotate every existing test file. A test is left
    unmarked if it uses none of these fixture names — i.e. it's pure
    logic and should never require Postgres to run.
    """
    for item in items:
        fixture_names = getattr(item, "fixturenames", [])
        if _DB_FIXTURE_NAMES.intersection(fixture_names):
            item.add_marker(pytest.mark.integration)
