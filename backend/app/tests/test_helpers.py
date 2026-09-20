from unittest.mock import AsyncMock, MagicMock


def make_nested_transaction_cm():
    """Mimic `AsyncSession.begin_nested()`'s return value: not itself a
    coroutine (call is sync), but usable as `async with ...:` — matches
    real SQLAlchemy so callers exercising SAVEPOINT-based per-item
    isolation (see aqi_ingestion._discover_india_locations_async) don't
    need real Postgres to run against."""
    cm = AsyncMock()
    cm.__aenter__.return_value = None
    cm.__aexit__.return_value = False
    return cm


def make_db_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    session.begin_nested = MagicMock(side_effect=lambda: make_nested_transaction_cm())
    return session


def make_session_cm(session):
    cm = AsyncMock()
    cm.__aenter__.return_value = session
    cm.__aexit__.return_value = False
    return cm
