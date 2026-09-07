import asyncio
import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

_redis_client: aioredis.Redis | None = None
_redis_client_loop: asyncio.AbstractEventLoop | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_client, _redis_client_loop
    current_loop = asyncio.get_running_loop()
    if _redis_client is not None and _redis_client_loop is not current_loop:
        await _discard_redis_client()
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
        _redis_client_loop = current_loop
    return _redis_client


async def _discard_redis_client() -> None:
    global _redis_client, _redis_client_loop
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception:  # noqa: BLE001 -- old client may be bound to a closed loop
            pass
        _redis_client = None
        _redis_client_loop = None


async def reset_redis_client() -> None:
    """Closes and discards the module-level Redis client so the next
    get_redis() call creates a fresh one, and flushes the DB so cached
    values never leak from one caller/test into the next.

    get_redis() itself now recovers from an event-loop mismatch (see
    above) since every Celery task entry point runs its own
    asyncio.run() and therefore its own fresh event loop each time,
    while this module-level client is a process-wide singleton — the
    same mismatch pytest-asyncio's per-test event loop already exercised
    here. This function still exists for test fixtures because the flush
    matters independently: endpoints like GET /aqi/live?scope=all cache
    their response under a fixed key (see app/api/v1/endpoints/aqi.py)
    with a multi-minute TTL, and without flushing between tests a value
    written by one test keeps being served to the next until the TTL
    naturally expires.
    """
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.flushdb()
        except (
            Exception
        ):  # noqa: BLE001 -- best-effort cleanup of a possibly-dead connection
            pass
    await _discard_redis_client()


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
