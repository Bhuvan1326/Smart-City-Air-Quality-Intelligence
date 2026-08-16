"""
Twilio SMS + IVR (voice) service.

Honesty check, since it matters for anyone deploying this on a zero-budget
basis: there is no telecom provider — Twilio included — that sends real SMS
or places real voice calls for free on an ongoing basis. Twilio's "free
trial" is a one-time, finite credit for testing (and still requires
verifying each destination number while on trial); production sending
requires a funded account. Nothing about that is specific to Twilio — SMS
termination costs money industry-wide.

Because of that, this integration is fully implemented (real Twilio SDK
calls, real TwiML for IVR) but is gated behind `settings.TWILIO_ENABLED`,
which defaults to False. With it left off, the platform runs and demos
with zero API keys and zero risk of an unexpected bill; an operator flips
it on deliberately once they have a funded Twilio account.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import logger


@dataclass
class SmsResult:
    success: bool
    message_sid: str | None = None
    error: str | None = None


@dataclass
class CallResult:
    success: bool
    call_sid: str | None = None
    error: str | None = None


class TwilioService:
    def __init__(self) -> None:
        self._client = None

    @property
    def is_configured(self) -> bool:
        return bool(
            settings.TWILIO_ENABLED
            and settings.TWILIO_ACCOUNT_SID
            and settings.TWILIO_AUTH_TOKEN
        )

    def _get_client(self):
        if self._client is not None:
            return self._client
        from twilio.rest import Client

        self._client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        return self._client

    async def send_sms(self, to_number: str, body: str) -> SmsResult:
        if not self.is_configured:
            logger.info(
                "twilio.disabled_skip_sms",
                reason="TWILIO_ENABLED is False or unconfigured",
            )
            return SmsResult(
                success=False, error="Twilio SMS is disabled (see TWILIO_ENABLED)"
            )

        import asyncio

        def _send():
            client = self._get_client()
            kwargs = {"to": to_number, "body": body}
            if settings.TWILIO_MESSAGING_SERVICE_SID:
                kwargs["messaging_service_sid"] = settings.TWILIO_MESSAGING_SERVICE_SID
            else:
                kwargs["from_"] = settings.TWILIO_FROM_NUMBER
            if settings.TWILIO_STATUS_CALLBACK_URL:
                kwargs["status_callback"] = settings.TWILIO_STATUS_CALLBACK_URL
            return client.messages.create(**kwargs)

        try:
            message = await asyncio.to_thread(_send)
            return SmsResult(success=True, message_sid=message.sid)
        except Exception as e:  # noqa: BLE001
            logger.error("twilio.sms_failed", error=str(e))
            return SmsResult(success=False, error=str(e))

    async def trigger_ivr_call(self, to_number: str, twiml_url: str) -> CallResult:
        """
        Places an outbound call that plays whatever TwiML `twiml_url` (a
        webhook on this backend, see app/api/v1/endpoints/notifications.py)
        returns — used for emergency AQI alerts and inspection reminders
        where a phone call is more likely to be noticed than SMS.
        """
        if not self.is_configured:
            logger.info(
                "twilio.disabled_skip_call",
                reason="TWILIO_ENABLED is False or unconfigured",
            )
            return CallResult(
                success=False, error="Twilio IVR is disabled (see TWILIO_ENABLED)"
            )

        import asyncio

        def _call():
            client = self._get_client()
            return client.calls.create(
                to=to_number,
                from_=settings.TWILIO_VOICE_CALLER_ID or settings.TWILIO_FROM_NUMBER,
                url=twiml_url,
                status_callback=settings.TWILIO_STATUS_CALLBACK_URL or None,
            )

        try:
            call = await asyncio.to_thread(_call)
            return CallResult(success=True, call_sid=call.sid)
        except Exception as e:  # noqa: BLE001
            logger.error("twilio.call_failed", error=str(e))
            return CallResult(success=False, error=str(e))

    @staticmethod
    def build_ivr_twiml(message: str, language: str = "en-IN") -> str:
        """
        Builds the TwiML response for an IVR alert call. `language` uses
        Twilio's supported <Say> voice locales — "en-IN", "hi-IN", and
        "mr-IN" (Marathi) cover the platform's supported alert languages.
        """
        from twilio.twiml.voice_response import VoiceResponse

        response = VoiceResponse()
        response.say(message, language=language)
        response.pause(length=1)
        response.say(
            message, language=language
        )  # repeat once for clarity on a phone line
        return str(response)
