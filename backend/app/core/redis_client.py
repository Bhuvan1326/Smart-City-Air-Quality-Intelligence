import asyncio
import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

_redis_client: aioredis.Redis | None = None
_redis_client_loop: asyncio.AbstractEventLoop | None = None


async def get_redis() -> aioredis.Redis:
    """Return a process-wide Redis client, transparently recreating it if
    the running event loop has changed since it was created.

    aioredis's connection pool binds its sockets/transports to whichever
    event loop was running at connection time. A single global client is
    safe under a real ASGI server (one event loop for the life of the
    process), but breaks the moment something runs the client under a
    *different* loop than the one it was created on — the old loop's
    transports are no longer valid and every call raises "Event loop is
    closed". That happens in this codebase's own test suite (pytest-asyncio
    with function-scoped event loops per test) and would equally happen for
    any other multi-loop host (e.g. a forked worker). Rather than papering
    over this with test-only mocks, detect the loop change here and
    reconnect, so the same client works correctly regardless of caller.
    """
    global _redis_client, _redis_client_loop
    current_loop = asyncio.get_running_loop()
    if _redis_client is None or _redis_client_loop is not current_loop:
        if _redis_client is not None:
            try:
                await _redis_client.aclose()
            except Exception:  # noqa: BLE001 -- best-effort cleanup of the stale client
                pass
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
        _redis_client_loop = current_loop
    return _redis_client


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
