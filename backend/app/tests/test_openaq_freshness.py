"""Coverage for the Live AQI runtime fix: OpenAQ reading freshness must be
judged against the responding server's own HTTP `Date` header, not this
machine's local clock, and transient 429 rate-limiting must be retried
rather than treated as "no data".

See `verify_live_aqi_output.txt`: three independently-resolved Pune
stations (SPPU, Dhankawadi, Hadapsar) all came back with near-identical
staleness (~90,543-90,554s, i.e. ~25.15h) despite being queried moments
apart -- the signature of a constant local clock offset (this stack runs
under WSL2, whose clock is known to drift from the Windows host) rather
than three independently-stale stations. Karve Road / Nigdi separately
came back `unresolved_no_openaq_candidates` after OpenAQ returned 429s
during a concurrent ingestion burst.
"""

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from app.services.aqi_providers import openaq

LOCATION = {
    "id": 999,
    "name": "Test Station",
    "sensors": [{"id": 1, "parameter": {"name": "pm25"}}],
}


def _latest_payload(obs_dt: datetime) -> dict:
    return {
        "results": [
            {
                "sensorsId": 1,
                "value": 42.0,
                "datetime": {"utc": obs_dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"},
            }
        ]
    }


@pytest.mark.asyncio
async def test_fresh_reading_accepted_despite_local_clock_skew(monkeypatch):
    """The core fix: the reading is genuinely 30 minutes old per the
    server's own Date header, but the local system clock is wrecked by
    +24h (simulating WSL2 drift). The old `datetime.now()`-based check
    would have rejected this as ~24.5h stale; the fix must still accept
    it because "now" is anchored to the response's Date header."""
    server_now = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    obs_time = server_now - timedelta(minutes=30)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_latest_payload(obs_time),
            headers={"date": format_datetime(server_now, usegmt=True)},
        )

    # Prove the local-clock approach would have failed this exact case.
    class _SkewedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now.__func__(datetime, tz) + timedelta(hours=24)

    monkeypatch.setattr(openaq, "datetime", _SkewedDatetime)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        reading = await openaq.fetch_location_latest(client, LOCATION)

    assert reading is not None, "fresh reading was incorrectly rejected as stale"
    assert reading.pm25 == 42.0
    assert reading.observed_at == obs_time


@pytest.mark.asyncio
async def test_genuinely_stale_reading_still_rejected():
    """A reading that really is old (per the server's own clock) must
    still be rejected -- staleness protection is not removed."""
    server_now = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    obs_time = server_now - timedelta(hours=30)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_latest_payload(obs_time),
            headers={"date": format_datetime(server_now, usegmt=True)},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        reading = await openaq.fetch_location_latest(client, LOCATION)

    assert reading is None


@pytest.mark.asyncio
async def test_missing_date_header_falls_back_to_local_clock():
    """If a response has no Date header at all, fall back to the local
    clock rather than crashing."""
    now = datetime.now(timezone.utc)
    obs_time = now - timedelta(minutes=5)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_latest_payload(obs_time))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        reading = await openaq.fetch_location_latest(client, LOCATION)

    assert reading is not None


@pytest.mark.asyncio
async def test_retry_recovers_from_transient_429():
    """A 429 followed by a 200 must succeed, matching the OpenAQ
    rate-limiting observed in the verify log when Celery Beat fires the
    India-wide discovery task and the Pune task at the same tick."""
    server_now = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    obs_time = server_now - timedelta(minutes=5)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"retry-after": "0.01"})
        return httpx.Response(
            200,
            json=_latest_payload(obs_time),
            headers={"date": format_datetime(server_now, usegmt=True)},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        reading = await openaq.fetch_location_latest(client, LOCATION)

    assert reading is not None
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_gives_up_gracefully_after_persistent_429():
    """Persistent rate-limiting must eventually give up cleanly (bounded
    retries, no crash, no infinite loop)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "0.01"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        resp = await openaq._get_with_retry(client, "https://example.invalid/locations")

    assert resp is not None
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_transport_error_returns_none_without_raising():
    """A hard transport failure on every attempt must return None rather
    than propagating, so callers can treat it the same as "no data"."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        resp = await openaq._get_with_retry(client, "https://example.invalid/locations")

    assert resp is None
