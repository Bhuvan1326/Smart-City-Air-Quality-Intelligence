import uuid
from datetime import UTC, datetime

from app.core.database import Base
from sqlalchemy import Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class BaseModel(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __abstract__ = True

    # Without this, SQLAlchemy leaves server-generated columns (notably
    # TimestampMixin.updated_at, which uses onupdate=func.now()) marked
    # "expired, pending refresh" after an UPDATE rather than fetching
    # the new value via RETURNING in the same statement. The next
    # attribute access (e.g. `issue.updated_at` when building a Pydantic
    # response) then triggers an implicit synchronous SELECT outside any
    # awaited context, which raises
    # `sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been
    # called; can't call await_only() here` under the async engine.
    # INSERT doesn't have this problem (server_default columns are
    # RETURNING-fetched automatically regardless of this flag on
    # PostgreSQL), which is why this only surfaced on UPDATE-then-read
    # flows like PATCH /civic/issues/{id}/status.
    __mapper_args__ = {"eager_defaults": True}

    def soft_delete(self) -> None:
        self.is_deleted = True
        self.deleted_at = datetime.now(UTC)
