from datetime import datetime
from uuid import UUID

from app.schemas.base import BaseSchema


class NotificationResponse(BaseSchema):
    id: UUID
    title: str
    body: str
    notification_type: str
    related_alert_id: UUID | None
    is_read: bool
    read_at: datetime | None
    created_at: datetime


class NotificationUnreadCountResponse(BaseSchema):
    unread_count: int
