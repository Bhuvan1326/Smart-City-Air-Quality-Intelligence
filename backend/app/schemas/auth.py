from uuid import UUID

from app.models.user import UserRole
from app.schemas.base import BaseSchema
from pydantic import EmailStr, Field


class LoginRequest(BaseSchema):
    email: EmailStr
    password: str = Field(min_length=8)


class RegisterRequest(BaseSchema):
    """Public self-registration. There is no `role` field here on purpose —
    see AuthService.register(): every account created through this endpoint
    is always UserRole.CITIZEN. Elevated roles are provisioned separately,
    never accepted from an unauthenticated request body."""

    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2, max_length=255)
    city: str | None = None
    phone: str | None = None
    preferred_language: str = "en"


class TokenResponse(BaseSchema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseSchema):
    refresh_token: str


class LogoutRequest(BaseSchema):
    refresh_token: str | None = None


class UserResponse(BaseSchema):
    id: UUID
    email: str
    full_name: str
    role: UserRole
    city: str | None
    ward_id: str | None
    is_active: bool
    preferred_language: str


class PasswordResetRequest(BaseSchema):
    email: EmailStr


class PasswordResetConfirm(BaseSchema):
    token: str
    new_password: str = Field(min_length=8)
