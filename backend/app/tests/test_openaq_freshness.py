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
async def test_429_is_not_retried_and_enters_cooldown(monkeypatch):
    calls = {"n": 0}

    async def no_slot_wait():
        return None

    async def no_cooldown(resp):
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            429,
            headers={
                "retry-after": "60",
                "x-ratelimit-reset": "60",
                "x-ratelimit-limit": "60",
                "x-ratelimit-remaining": "0",
            },
        )

    monkeypatch.setattr(openaq, "_acquire_rate_slot", no_slot_wait)
    monkeypatch.setattr(openaq, "_set_provider_cooldown", no_cooldown)
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        reading = await openaq.fetch_location_latest(client, LOCATION)

    assert reading is None
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_rate_limit_headers_are_honored_without_waiting_until_zero(monkeypatch):
    server_now = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    obs_time = server_now - timedelta(minutes=5)
    cooldown_calls = []

    async def no_slot_wait():
        return None

    async def record_cooldown(resp):
        cooldown_calls.append(resp.headers.get("x-ratelimit-reset"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_latest_payload(obs_time),
            headers={
                "date": format_datetime(server_now, usegmt=True),
                "x-ratelimit-limit": "60",
                "x-ratelimit-remaining": "3",
                "x-ratelimit-reset": "10",
            },
        )

    monkeypatch.setattr(openaq, "_acquire_rate_slot", no_slot_wait)
    monkeypatch.setattr(openaq, "_set_provider_cooldown", record_cooldown)
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        reading = await openaq.fetch_location_latest(client, LOCATION)

    assert reading is not None
    assert cooldown_calls == ["10"]
