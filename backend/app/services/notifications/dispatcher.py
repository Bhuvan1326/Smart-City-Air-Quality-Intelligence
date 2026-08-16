"""
NotificationDispatcher — turns a CitizenAlert (a ward-broadcast alert record,
see app.models.enforcement.CitizenAlert) into actual delivered notifications,
and updates its delivery_status/delivery_count/sent_at fields.

Recipients are every User in the alert's ward (falling back to city-wide
users if no ward is set on the account). Channel priority is:

  1. push  → Firebase (free) if the user has a push_token
  2. email → SMTP (free) if the user has an email and push isn't available
  3. sms/ivr → Twilio (paid, opt-in — see TwilioService) only when
     TWILIO_ENABLED and the alert's channel explicitly requests it

This keeps the whole notification path fully functional on zero API keys
(alerts are computed and logged, delivery_status becomes "skipped_no_config"
rather than silently pretending to succeed) and upgrades automatically the
moment free Firebase/SMTP credentials are supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.enforcement import AlertChannel, CitizenAlert
from app.models.user import User
from app.services.notifications.email_service import EmailService
from app.services.notifications.firebase_service import FirebaseService
from app.services.notifications.twilio_service import TwilioService


@dataclass
class DispatchOutcome:
    alert_id: str
    recipients_considered: int
    delivered: int
    failed: int
    skipped_no_config: int
    channel_used: str


class NotificationDispatcher:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.firebase = FirebaseService()
        self.email = EmailService()
        self.twilio = TwilioService()

    async def dispatch_alert(self, alert: CitizenAlert) -> DispatchOutcome:
        recipients = await self._recipients_for(alert)
        delivered = failed = skipped = 0

        for user in recipients:
            ok = await self._deliver_to_user(alert, user)
            if ok is True:
                delivered += 1
            elif ok is False:
                failed += 1
            else:
                skipped += 1

        alert.delivery_count = delivered
        alert.sent_at = alert.sent_at or datetime.now(UTC)
        if delivered > 0:
            alert.delivery_status = (
                "delivered" if failed == 0 else "partially_delivered"
            )
        elif skipped > 0 and failed == 0:
            alert.delivery_status = "skipped_no_config"
        else:
            alert.delivery_status = "failed"

        outcome = DispatchOutcome(
            alert_id=str(alert.id),
            recipients_considered=len(recipients),
            delivered=delivered,
            failed=failed,
            skipped_no_config=skipped,
            channel_used=alert.channel,
        )
        logger.info("notification.dispatch_complete", **outcome.__dict__)
        return outcome

    async def _recipients_for(self, alert: CitizenAlert) -> list[User]:
        query = select(User).where(
            User.is_active == True,  # noqa: E712
            User.ward_id == alert.ward_id,
        )
        result = await self.session.execute(query)
        users = list(result.scalars().all())
        if not users:
            # No one explicitly registered to this ward — fall back to city.
            city_query = select(User).where(
                User.is_active == True,  # noqa: E712
                User.city == alert.city,
            )
            users = list((await self.session.execute(city_query)).scalars().all())
        return users

    async def _deliver_to_user(self, alert: CitizenAlert, user: User) -> bool | None:
        """Returns True (delivered), False (attempted and failed), or None (skipped, unconfigured)."""
        if alert.channel == AlertChannel.PUSH and user.push_token:
            result = await self.firebase.send_to_token(
                user.push_token,
                alert.message_title,
                alert.message_text,
                data={
                    "ward_id": alert.ward_id,
                    "risk_level": alert.risk_level,
                    "aqi": alert.aqi_value,
                },
            )
            if not self.firebase.is_configured:
                return None
            return result.success

        if alert.channel == AlertChannel.EMAIL or (
            alert.channel == AlertChannel.PUSH and not user.push_token
        ):
            if not user.email:
                return None
            result = await self.email.send(
                user.email, alert.message_title, alert.message_text
            )
            if not self.email.is_configured:
                return None
            return result.success

        if alert.channel == AlertChannel.SMS:
            if not user.phone:
                return None
            if not self.twilio.is_configured:
                return None
            result = await self.twilio.send_sms(user.phone, alert.message_text)
            return result.success

        if alert.channel == AlertChannel.IVR:
            if not user.phone or not self.twilio.is_configured:
                return None
            # Requires a public callback URL serving TwiML for this alert;
            # the notifications endpoint exposes one at /notifications/ivr/{alert_id}.
            from app.core.config import settings

            twiml_url = f"{settings.TWILIO_STATUS_CALLBACK_URL or ''}/api/v1/notifications/ivr/{alert.id}"
            result = await self.twilio.trigger_ivr_call(user.phone, twiml_url)
            return result.success

        # DISPLAY channel = public signage, not a per-user push; nothing to dispatch here.
        return None
