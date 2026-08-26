import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.user import User, UserRole


@pytest.fixture(scope="session", autouse=True)
def _disable_rate_limiting_for_tests():
    """
    RateLimitMiddleware (app.core.middleware) is a real, Redis-backed,
    per-IP sliding window (60 req/min, 1000 req/hr) that isn't specific
    to any one endpoint. Every test in this suite calls in from the same
    client IP via the ASGI test transport, so without this the *combined*
    request volume of the full test session can trip the production
    per-minute limit purely from test traffic — causing unrelated,
    otherwise-passing tests later in the run to fail with 429s (most
    visible on fast local runs where hundreds of requests land inside the
    same 60-second window). No test in this suite exercises rate-limiting
    behavior itself, so disabling it for the test session removes no
    coverage; RATE_LIMIT_ENABLED still defaults to True for real
    deployments, so production behavior is unaffected.
    """
    original = settings.RATE_LIMIT_ENABLED
    settings.RATE_LIMIT_ENABLED = False
    yield
    settings.RATE_LIMIT_ENABLED = original


TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://airuser:airpass@localhost:5434/airquality_test",
    ),
)


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
    engine = create_async_engine(TEST_DB_URL, echo=False, pool_pre_ping=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

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

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    app.dependency_overrides.clear()


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
    import pytest

    for item in items:
        fixture_names = getattr(item, "fixturenames", [])
        if _DB_FIXTURE_NAMES.intersection(fixture_names):
            item.add_marker(pytest.mark.integration)
