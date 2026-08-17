"""
Firebase Cloud Messaging (FCM) push notification service.

FCM is free on Firebase's Spark plan — no credit card required, no volume
limit that requires payment for typical alerting use. This is the primary
notification channel for the platform for that reason.

Uses the HTTP v1 API via the `firebase-admin` SDK, which handles the OAuth2
service-account signing internally. Setup (all free):
  1. Create a Firebase project at https://console.firebase.google.com
  2. Project Settings → Service Accounts → Generate new private key
  3. Put the downloaded JSON's contents (or a path to the file) in
     FIREBASE_CREDENTIALS_JSON

As with the satellite clients, the live-send path can't be exercised from
this sandbox (no network egress to Google APIs) — verify against a real
project before production use.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import logger


@dataclass
class PushResult:
    success: bool
    message_id: str | None = None
    error: str | None = None


class FirebaseService:
    _app = None  # lazily-initialized firebase_admin App, shared across instances

    def __init__(self) -> None:
        self._messaging = None

    @property
    def is_configured(self) -> bool:
        return bool(settings.FIREBASE_PROJECT_ID and settings.FIREBASE_CREDENTIALS_JSON)

    def _ensure_initialized(self):
        if not self.is_configured:
            return None
        if FirebaseService._app is not None:
            import firebase_admin
            from firebase_admin import messaging

            return messaging

        import firebase_admin
        from firebase_admin import credentials, messaging

        raw = settings.FIREBASE_CREDENTIALS_JSON
        try:
            if raw.strip().startswith("{"):
                cred_info = json.loads(raw)
                cred = credentials.Certificate(cred_info)
            else:
                cred = credentials.Certificate(raw)  # path to file
            FirebaseService._app = firebase_admin.initialize_app(
                cred, {"projectId": settings.FIREBASE_PROJECT_ID}
            )
        except Exception as e:  # noqa: BLE001 -- notification provider optional
            logger.error("firebase.init_failed", error=str(e))
            return None

        return messaging

    async def send_to_token(
        self, token: str, title: str, body: str, data: dict | None = None
    ) -> PushResult:
        messaging = self._ensure_initialized()
        if messaging is None:
            logger.info("firebase.not_configured_skip_send")
            return PushResult(success=False, error="Firebase not configured")

        message = messaging.Message(
            token=token,
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
        )
        try:
            message_id = messaging.send(message)
            return PushResult(success=True, message_id=message_id)
        except Exception as e:  # noqa: BLE001
            logger.error("firebase.send_failed", error=str(e))
            return PushResult(success=False, error=str(e))

    async def send_to_topic(
        self, topic: str, title: str, body: str, data: dict | None = None
    ) -> PushResult:
        """
        Topic sends power role-based and ward/city-based notifications
        (e.g. "ward_W03_hi_aqi", "role_enforcement_officer") without having
        to fan out to individual tokens — clients subscribe to topics on
        their end.
        """
        messaging = self._ensure_initialized()
        if messaging is None:
            logger.info("firebase.not_configured_skip_send")
            return PushResult(success=False, error="Firebase not configured")

        message = messaging.Message(
            topic=topic,
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
        )
        try:
            message_id = messaging.send(message)
            return PushResult(success=True, message_id=message_id)
        except Exception as e:  # noqa: BLE001
            logger.error("firebase.topic_send_failed", topic=topic, error=str(e))
            return PushResult(success=False, error=str(e))
