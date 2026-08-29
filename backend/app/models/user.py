from enum import Enum
from typing import TYPE_CHECKING

from app.models.base import BaseModel
from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.analytics import AuditLog, OfficerRoute
    from app.models.enforcement import EnforcementAction


class UserRole(str, Enum):
    CITY_ADMINISTRATOR = "city_administrator"
    POLLUTION_CONTROL_OFFICER = "pollution_control_officer"
    FIELD_INSPECTOR = "field_inspector"
    CITIZEN = "citizen"


class User(BaseModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        String(50), nullable=False, default=UserRole.CITIZEN
    )
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ward_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    preferred_language: Mapped[str] = mapped_column(
        String(10), default="en", nullable=False
    )
    push_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    enforcement_actions: Mapped[list["EnforcementAction"]] = relationship(
        "EnforcementAction",
        back_populates="officer",
        foreign_keys="EnforcementAction.officer_id",
    )
    routes: Mapped[list["OfficerRoute"]] = relationship(
        "OfficerRoute", back_populates="officer"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="user"
    )
