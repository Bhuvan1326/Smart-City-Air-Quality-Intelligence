import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

_redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
    return _redis_client


async def reset_redis_client() -> None:
    """Closes and discards the module-level Redis client so the next
    get_redis() call creates a fresh one bound to the currently running
    event loop.

    redis.asyncio's connection pool is bound to whichever event loop is
    running when its first connection is established. Because
    _redis_client is a process-wide singleton, reusing it across
    different event loops (e.g. pytest-asyncio's default of a fresh loop
    per test function — see pytest.ini's asyncio_default_test_loop_scope)
    raises errors like "Event loop is closed" or "Future attached to a
    different loop". Test fixtures call this between tests; production
    code never needs to, since the app runs on a single long-lived loop.
    """
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except (
            Exception
        ):  # noqa: BLE001 -- best-effort cleanup of a possibly-dead connection
            pass
        _redis_client = None


async def cache_get(key: str) -> Any | None:
    client = await get_redis()
    value = await client.get(key)
    if value is None:
        return None
    return json.loads(value)


async def cache_set(
    key: str, value: Any, ttl: int = settings.CACHE_TTL_SECONDS
) -> None:
    client = await get_redis()
    await client.set(key, json.dumps(value, default=str), ex=ttl)


async def cache_delete(key: str) -> None:
    client = await get_redis()
    await client.delete(key)


async def cache_delete_pattern(pattern: str) -> None:
    client = await get_redis()
    keys = await client.keys(pattern)
    if keys:
        await client.delete(*keys)
