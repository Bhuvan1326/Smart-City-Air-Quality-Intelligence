"""
Free email notification channel via plain SMTP.

Unlike SMS/voice, email delivery is genuinely free at the volumes this
platform needs: providers such as Brevo (300 free emails/day, no card) or
a Gmail account with an App Password both work with this client with zero
cost. This is the free fallback channel for citizen alerts when a push
token isn't available (e.g. the citizen hasn't installed the PWA).
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings
from app.core.logging import logger


@dataclass
class EmailResult:
    success: bool
    error: str | None = None


class EmailService:
    @property
    def is_configured(self) -> bool:
        return bool(
            settings.SMTP_HOST and settings.SMTP_USERNAME and settings.SMTP_PASSWORD
        )

    async def send(
        self, to_address: str, subject: str, body: str, html_body: str | None = None
    ) -> EmailResult:
        if not self.is_configured:
            logger.info("email.not_configured_skip_send")
            return EmailResult(success=False, error="SMTP not configured")

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = settings.SMTP_FROM_ADDRESS
        message["To"] = to_address
        message.attach(MIMEText(body, "plain"))
        if html_body:
            message.attach(MIMEText(html_body, "html"))

        try:
            # smtplib is blocking; run it off the event loop.
            import asyncio

            await asyncio.to_thread(self._send_sync, to_address, message)
            return EmailResult(success=True)
        except Exception as e:  # noqa: BLE001
            logger.error("email.send_failed", error=str(e))
            return EmailResult(success=False, error=str(e))

    def _send_sync(self, to_address: str, message: MIMEMultipart) -> None:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.sendmail(
                settings.SMTP_FROM_ADDRESS, [to_address], message.as_string()
            )
