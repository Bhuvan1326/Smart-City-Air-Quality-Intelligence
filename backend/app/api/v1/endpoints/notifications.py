from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.models.enforcement import CitizenAlert
from app.models.notification import Notification
from app.schemas.base import APIResponse, BaseSchema, PaginatedResponse
from app.schemas.notification import (
    NotificationResponse,
    NotificationUnreadCountResponse,
)
from app.services.notifications.twilio_service import TwilioService

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


@router.get("", response_model=APIResponse[PaginatedResponse[NotificationResponse]])
async def list_notifications(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> APIResponse[PaginatedResponse[NotificationResponse]]:
    """The current user's own notifications, newest first. Never returns
    another user's notifications — always scoped to current_user.id.
    """
    query = select(Notification).where(
        Notification.user_id == current_user.id,
        Notification.is_deleted.is_(False),
    )
    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query) or 0

    query = query.order_by(desc(Notification.created_at))
    result = await session.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )
    notifications = list(result.scalars().all())
    items = [NotificationResponse.model_validate(n) for n in notifications]
    return APIResponse(data=PaginatedResponse.create(items, total, page, page_size))


@router.get(
    "/unread-count", response_model=APIResponse[NotificationUnreadCountResponse]
)
async def get_unread_notification_count(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[NotificationUnreadCountResponse]:
    count = await session.scalar(
        select(func.count()).where(
            Notification.user_id == current_user.id,
            Notification.is_deleted.is_(False),
            Notification.is_read.is_(False),
        )
    )
    return APIResponse(data=NotificationUnreadCountResponse(unread_count=count or 0))


@router.post(
    "/{notification_id}/read", response_model=APIResponse[NotificationResponse]
)
async def mark_notification_read(
    notification_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[NotificationResponse]:
    notification = await session.get(Notification, notification_id)
    if notification is None or notification.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found"
        )
    if notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(UTC)
        await session.flush()
        await session.refresh(notification)

    return APIResponse(data=NotificationResponse.model_validate(notification))


@router.post("/read-all", response_model=APIResponse[None])
async def mark_all_notifications_read(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[None]:
    await session.execute(
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.is_deleted.is_(False),
            Notification.is_read.is_(False),
        )
        .values(is_read=True, read_at=datetime.now(UTC))
    )
    await session.flush()
    return APIResponse(message="All notifications marked as read")


@router.delete("/{notification_id}", response_model=APIResponse[None])
async def dismiss_notification(
    notification_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[None]:
    notification = await session.get(Notification, notification_id)
    if notification is None or notification.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found"
        )
    if notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    notification.soft_delete()
    await session.flush()
    return APIResponse(message="Notification dismissed")
