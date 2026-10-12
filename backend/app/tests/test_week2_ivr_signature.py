"""Week 2 (B2): the IVR webhook must reject unsigned/invalidly signed requests."""

import uuid

import pytest

from app.core.config import settings
from app.services.notifications.twilio_signature import (
    compute_signature,
    ivr_callback_url,
)

BASE = "https://alerts.example.test"
TOKEN = "test-only-twilio-token-0123456789"  # fixture value, not a secret


@pytest.fixture(autouse=True)
def twilio_cfg(monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.setattr(settings, "TWILIO_STATUS_CALLBACK_URL", BASE)


def _path(alert_id):
    return f"/api/v1/notifications/ivr/{alert_id}"


def test_url_helper_matches_dispatcher_format():
    aid = uuid.uuid4()
    assert ivr_callback_url(aid) == f"{BASE}/api/v1/notifications/ivr/{aid}"


def test_matches_official_twilio_sdk_algorithm():
    RequestValidator = pytest.importorskip("twilio.request_validator").RequestValidator
    url = f"{BASE}/api/v1/notifications/ivr/{uuid.uuid4()}"
    params = {"CallSid": "CA123", "From": "+911234567890", "To": "+910987654321"}
    assert compute_signature(TOKEN, url, params) == RequestValidator(
        TOKEN
    ).compute_signature(url, params)
    assert compute_signature(TOKEN, url, {}) == RequestValidator(
        TOKEN
    ).compute_signature(url, {})


@pytest.mark.asyncio
async def test_unsigned_get_is_403(client):
    r = await client.get(_path(uuid.uuid4()))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_invalid_signature_is_403(client):
    r = await client.get(
        _path(uuid.uuid4()), headers={"X-Twilio-Signature": "bm90LWEtcmVhbC1zaWc="}
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_signature_for_a_different_alert_is_403(client):
    a, b = uuid.uuid4(), uuid.uuid4()
    sig_for_a = compute_signature(TOKEN, ivr_callback_url(a), {})
    r = await client.get(_path(b), headers={"X-Twilio-Signature": sig_for_a})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_valid_signed_get_reaches_handler(client):
    aid = uuid.uuid4()
    sig = compute_signature(TOKEN, ivr_callback_url(aid), {})
    r = await client.get(_path(aid), headers={"X-Twilio-Signature": sig})
    assert r.status_code == 200
    assert "xml" in r.headers["content-type"]


@pytest.mark.asyncio
async def test_valid_signed_post_with_params_reaches_handler(client):
    aid = uuid.uuid4()
    params = {"CallSid": "CA1", "CallStatus": "in-progress"}
    sig = compute_signature(TOKEN, ivr_callback_url(aid), params)
    r = await client.post(_path(aid), data=params, headers={"X-Twilio-Signature": sig})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_tampered_post_param_is_403(client):
    aid = uuid.uuid4()
    sig = compute_signature(TOKEN, ivr_callback_url(aid), {"CallSid": "CA1"})
    r = await client.post(
        _path(aid), data={"CallSid": "CA-evil"}, headers={"X-Twilio-Signature": sig}
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_fails_closed_when_token_or_base_url_unset(client, monkeypatch):
    aid = uuid.uuid4()
    sig = compute_signature(TOKEN, ivr_callback_url(aid), {})
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "")
    assert (
        await client.get(_path(aid), headers={"X-Twilio-Signature": sig})
    ).status_code == 403
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.setattr(settings, "TWILIO_STATUS_CALLBACK_URL", "")
    assert (
        await client.get(_path(aid), headers={"X-Twilio-Signature": sig})
    ).status_code == 403
