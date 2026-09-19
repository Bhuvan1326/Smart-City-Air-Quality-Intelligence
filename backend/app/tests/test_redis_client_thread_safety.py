import asyncio
import threading

import pytest

from app.core.redis_client import get_redis, reset_redis_client

pytestmark = pytest.mark.asyncio


async def test_get_redis_returns_a_working_client():
    client = await get_redis()
    await client.set("test_redis_client_thread_safety:smoke", "1", ex=5)
    assert await client.get("test_redis_client_thread_safety:smoke") == "1"
    await reset_redis_client()


def test_get_redis_is_isolated_per_thread():

    clients: dict[str, object] = {}
    errors: list[BaseException] = []
    start_barrier = threading.Barrier(2)

    def worker(name: str) -> None:
        async def run() -> None:
            start_barrier.wait(timeout=5)
            client = await get_redis()
            await client.set(f"test_redis_client_thread_safety:{name}", "1", ex=5)
            clients[name] = client
            await reset_redis_client()

        try:
            asyncio.run(run())
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(f"thread-{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"worker thread(s) raised: {errors}"
    assert len(clients) == 2
    assert clients["thread-0"] is not clients["thread-1"]
