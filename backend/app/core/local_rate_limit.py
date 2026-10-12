"""Bounded per-process rate-limit fallback for when Redis is unavailable.

The distributed limiter (`RateLimitMiddleware` + `get_redis`) is the real
control. This module exists so that a Redis outage degrades to a *bounded*
in-process limiter instead of silently allowing unlimited traffic (the
previous fail-open behavior — S9) or taking the whole platform down (a
naive fail-closed).

Deliberate limitations, documented in docs/week-3/security-validation.md:
  * Per-process state — limits are NOT shared across workers/containers,
    so effective global limits scale with the worker count. Acceptable as
    a degraded safeguard; it is never the primary control.
  * Only the current minute bucket is retained — memory is O(distinct
    keys per minute), never O(total requests). Hour-level limits simply
    do not exist in the fallback.
"""

from __future__ import annotations

import threading
import time


class LocalRateLimiter:
    """Current-minute sliding-window counter, thread-safe, bounded."""

    def __init__(self) -> None:
        self._window_minute: int = -1
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, *, now: int | None = None) -> int:
        """Increment and return the key's count for the current minute
        bucket. `now` is injectable for deterministic tests."""
        minute = (now if now is not None else int(time.time())) // 60
        with self._lock:
            if minute != self._window_minute:
                # Window rolled: all previous counts are stale — clearing
                # keeps memory bounded to current-minute cardinality.
                self._counts.clear()
                self._window_minute = minute
            self._counts[key] = self._counts.get(key, 0) + 1
            return self._counts[key]

    def value(self, key: str) -> int:
        with self._lock:
            return self._counts.get(key, 0)

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()
            self._window_minute = -1


# Shared fallback instance — one per process, deliberately.
local_rate_limiter = LocalRateLimiter()
