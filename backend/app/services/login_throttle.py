"""Login abuse protection (S9): per-email failed-attempt throttle.

Redis counter when available (`login_fail:{email}`, TTL =
LOGIN_WINDOW_SECONDS); a bounded in-process fallback when it is not —
mirroring the rate-limiter degradation policy: a store outage must never
silently make authentication unlimited.

Checked BEFORE password verification in AuthService.login so the 429-style
response fires for any email once its failure budget is spent — whether or
not the account exists — and cannot be used to enumerate valid accounts.

Trade-off (documented, standard for email-keyed lockout): an attacker who
knows a victim's address can keep it locked by continuously failing
logins. Bounded by the window length; see security-validation.md.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable

from app.core.config import settings

_KEY_PREFIX = "login_fail:"


def _now() -> int:
    return int(time.time())


class _LocalThrottle:
    """Bounded per-process fallback: per-email list of failure timestamps
    inside the sliding window. Memory is O(failed logins in window)."""

    def __init__(self, clock: Callable[[], int] = _now) -> None:
        self._clock = clock
        self._failures: dict[str, list[int]] = defaultdict(list)

    def is_locked(self, email: str) -> bool:
        window_start = self._clock() - settings.LOGIN_WINDOW_SECONDS
        fails = [t for t in self._failures.get(email, []) if t >= window_start]
        self._failures[email] = fails
        return len(fails) >= settings.LOGIN_MAX_ATTEMPTS

    def record_failure(self, email: str) -> int:
        window_start = self._clock() - settings.LOGIN_WINDOW_SECONDS
        fails = [t for t in self._failures.get(email, []) if t >= window_start]
        fails.append(self._clock())
        self._failures[email] = fails
        return len(fails)

    def clear(self, email: str) -> None:
        self._failures.pop(email, None)

    def reset(self) -> None:
        self._failures.clear()


_local = _LocalThrottle()


def reset_local_throttle() -> None:
    _local.reset()


async def _redis():
    from app.core.redis_client import get_redis

    return await get_redis()


async def is_locked(email: str) -> bool:
    try:
        count = await (await _redis()).get(f"{_KEY_PREFIX}{email}")
        if count is not None and int(count) >= settings.LOGIN_MAX_ATTEMPTS:
            return True
        return False
    except Exception:
        return _local.is_locked(email)


async def record_failure(email: str) -> int:
    try:
        redis = await _redis()
        key = f"{_KEY_PREFIX}{email}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, settings.LOGIN_WINDOW_SECONDS)
        return int(count)
    except Exception:
        return _local.record_failure(email)


async def clear_failures(email: str) -> None:
    try:
        redis = await _redis()
        await redis.delete(f"{_KEY_PREFIX}{email}")
    except Exception:
        _local.clear(email)


async def failure_count(email: str) -> int:
    try:
        count = await (await _redis()).get(f"{_KEY_PREFIX}{email}")
        return int(count) if count else 0
    except Exception:
        return len(_local._failures.get(email, []))
