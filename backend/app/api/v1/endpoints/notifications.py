from typing import Annotated
from uuid import UUID

from app.api.deps import CurrentUser, get_db
from app.models.enforcement import CitizenAlert
from app.schemas.base import APIResponse, BaseSchema
from app.services.notifications.twilio_service import TwilioService
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class RegisterPushTokenRequest(BaseSchema):
    push_token: str


@router.post("/push-token", response_model=APIResponse[None])
async def register_push_token(
    data: RegisterPushTokenRequest,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[None]:
    """Register/update the current user's FCM device token (free push channel)."""
    current_user.push_token = data.push_token
    session.add(current_user)
    await session.commit()
    return APIResponse(message="Push token registered")


@router.get("/ivr/{alert_id}")
async def ivr_twiml_webhook(
    alert_id: UUID, session: Annotated[AsyncSession, Depends(get_db)]
) -> Response:
    """
    Twilio calls this URL when an IVR alert call connects, and expects a
    TwiML XML response describing what to say. Only reachable when
    TWILIO_ENABLED=True and an outbound call was actually placed (see
    TwilioService.trigger_ivr_call / NotificationDispatcher).
    """
    alert = await session.get(CitizenAlert, alert_id)
    message = alert.message_text if alert else "No alert details available."
    language_map = {"en": "en-IN", "hi": "hi-IN", "mr": "mr-IN"}
    language = language_map.get(alert.language if alert else "en", "en-IN")

    twiml = TwilioService.build_ivr_twiml(message, language=language)
    return Response(content=twiml, media_type="application/xml")
