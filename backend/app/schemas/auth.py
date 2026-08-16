from uuid import UUID

from pydantic import EmailStr, Field

from app.models.user import UserRole
from app.schemas.base import BaseSchema


class LoginRequest(BaseSchema):
    email: EmailStr
    password: str = Field(min_length=8)


class RegisterRequest(BaseSchema):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2, max_length=255)
    role: UserRole = UserRole.CITIZEN
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
