import asyncio
import json
import threading
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import logger

_thread_local = threading.local()


def _log_redis_event(event: str, **kwargs: Any) -> None:

    logger.info(
        event,
        thread_id=threading.get_ident(),
        thread_name=threading.current_thread().name,
        **kwargs,
    )


async def get_redis() -> aioredis.Redis:
    current_loop = asyncio.get_running_loop()
    client: aioredis.Redis | None = getattr(_thread_local, "client", None)
    client_loop = getattr(_thread_local, "client_loop", None)
    if client is not None and client_loop is not current_loop:
        await _discard_thread_local_client()
        client = None
    if client is None:
        client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
        _thread_local.client = client
        _thread_local.client_loop = current_loop
        _log_redis_event("redis_client.created", loop_id=id(current_loop))
    return client


async def _discard_thread_local_client() -> None:
    client: aioredis.Redis | None = getattr(_thread_local, "client", None)
    if client is not None:
        try:
            await client.aclose()
        except Exception:
            pass
        _log_redis_event(
            "redis_client.discarded",
            loop_id=id(getattr(_thread_local, "client_loop", None)),
        )
        _thread_local.client = None
        _thread_local.client_loop = None


async def reset_redis_client() -> None:
    """Closes and discards the calling thread's Redis client so the next
    get_redis() call on this thread creates a fresh one, and flushes the DB
    so cached values never leak from one caller/test into the next. Test
    suites run single-threaded, so this remains equivalent to the previous
    module-global behavior for that use case.
    """
    client: aioredis.Redis | None = getattr(_thread_local, "client", None)
    if client is not None:
        try:
            await client.flushdb()
        except Exception:
            pass
    await _discard_thread_local_client()


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
