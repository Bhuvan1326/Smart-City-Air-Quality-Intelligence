from unittest.mock import AsyncMock

import pytest

from app.models.enforcement import AlertChannel
from app.services.notifications.dispatcher import NotificationDispatcher
from app.services.notifications.email_service import EmailResult
from app.services.notifications.firebase_service import PushResult
from app.services.notifications.twilio_service import SmsResult


class _FakeUser:
    def __init__(self, push_token=None, email=None, phone=None):
        self.push_token = push_token
        self.email = email
        self.phone = phone


class _FakeAlert:
    def __init__(self, channel, ward_id="W01", city="Pune"):
        self.channel = channel
        self.ward_id = ward_id
        self.city = city
        self.message_title = "AQI Alert"
        self.message_text = "Air quality has worsened"
        self.risk_level = "high"
        self.aqi_value = 220
        self.id = "alert-1"
        self.sent_at = None
        self.delivery_count = 0
        self.delivery_status = "pending"


@pytest.fixture
def dispatcher():
    d = NotificationDispatcher(session=AsyncMock())
    d.firebase = AsyncMock()
    d.email = AsyncMock()
    d.twilio = AsyncMock()
    return d


@pytest.mark.asyncio
async def test_push_channel_delivers_via_firebase_when_configured(dispatcher):
    dispatcher.firebase.is_configured = True
    dispatcher.firebase.send_to_token.return_value = PushResult(
        success=True, message_id="msg-1"
    )
    user = _FakeUser(push_token="token-abc")
    alert = _FakeAlert(AlertChannel.PUSH)

    result = await dispatcher._deliver_to_user(alert, user)

    assert result is True
    dispatcher.firebase.send_to_token.assert_called_once()


@pytest.mark.asyncio
async def test_push_channel_skipped_when_firebase_unconfigured(dispatcher):
    dispatcher.firebase.is_configured = False
    user = _FakeUser(push_token="token-abc")
    alert = _FakeAlert(AlertChannel.PUSH)

    result = await dispatcher._deliver_to_user(alert, user)

    assert result is None  # skipped, not failed


@pytest.mark.asyncio
async def test_push_falls_back_to_email_when_user_has_no_push_token(dispatcher):
    dispatcher.email.is_configured = True
    dispatcher.email.send.return_value = EmailResult(success=True)
    user = _FakeUser(push_token=None, email="citizen@example.com")
    alert = _FakeAlert(AlertChannel.PUSH)

    result = await dispatcher._deliver_to_user(alert, user)

    assert result is True
    dispatcher.email.send.assert_called_once()


@pytest.mark.asyncio
async def test_email_channel_skipped_when_user_has_no_email(dispatcher):
    dispatcher.email.is_configured = True
    user = _FakeUser(push_token=None, email=None)
    alert = _FakeAlert(AlertChannel.EMAIL)

    result = await dispatcher._deliver_to_user(alert, user)

    assert result is None
    dispatcher.email.send.assert_not_called()


@pytest.mark.asyncio
async def test_sms_channel_skipped_when_twilio_disabled(dispatcher):
    dispatcher.twilio.is_configured = (
        False  # TWILIO_ENABLED=false, the platform default
    )
    user = _FakeUser(phone="+911234567890")
    alert = _FakeAlert(AlertChannel.SMS)

    result = await dispatcher._deliver_to_user(alert, user)

    assert result is None
    dispatcher.twilio.send_sms.assert_not_called()


@pytest.mark.asyncio
async def test_sms_channel_delivers_when_twilio_enabled_and_configured(dispatcher):
    dispatcher.twilio.is_configured = True
    dispatcher.twilio.send_sms.return_value = SmsResult(
        success=True, message_sid="SM123"
    )
    user = _FakeUser(phone="+911234567890")
    alert = _FakeAlert(AlertChannel.SMS)

    result = await dispatcher._deliver_to_user(alert, user)

    assert result is True


@pytest.mark.asyncio
async def test_display_channel_is_never_dispatched_to_individual_users(dispatcher):
    """DISPLAY is public signage, not a per-citizen push — should always be a no-op here."""
    user = _FakeUser(push_token="tok", email="a@b.com", phone="+91123")
    alert = _FakeAlert(AlertChannel.DISPLAY)

    result = await dispatcher._deliver_to_user(alert, user)

    assert result is None
    dispatcher.firebase.send_to_token.assert_not_called()
    dispatcher.email.send.assert_not_called()
    dispatcher.twilio.send_sms.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_alert_aggregates_outcome_across_recipients(
    dispatcher, monkeypatch
):
    alert = _FakeAlert(AlertChannel.PUSH)
    users = [
        _FakeUser(push_token="t1"),
        _FakeUser(push_token="t2"),
        _FakeUser(push_token=None, email=None),
    ]

    async def fake_recipients_for(_alert):
        return users

    async def fake_deliver(_alert, user):
        return True if user.push_token else None

    monkeypatch.setattr(dispatcher, "_recipients_for", fake_recipients_for)
    monkeypatch.setattr(dispatcher, "_deliver_to_user", fake_deliver)

    outcome = await dispatcher.dispatch_alert(alert)

    assert outcome.recipients_considered == 3
    assert outcome.delivered == 2
    assert outcome.skipped_no_config == 1
    assert outcome.failed == 0
    assert alert.delivery_status == "delivered"
