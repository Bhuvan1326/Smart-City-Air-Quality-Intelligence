from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    is_family_revoked,
    register_refresh_token,
    revoke_family,
    validate_and_rotate,
    verify_password,
)
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)

    async def register(self, data: RegisterRequest) -> UserResponse:
        existing = await self.user_repo.get_by_email(data.email)
        if existing:
            raise ValueError("Email already registered")

        # SECURITY: public self-registration must never grant an elevated
        # role. `data.role` is client-supplied on a fully unauthenticated
        # endpoint — honoring it would let anyone register as
        # city_administrator. Elevated roles (admin, officer, inspector)
        # are assigned out-of-band (e.g. by an existing administrator or
        # direct provisioning), never through public self-registration.
        from app.models.user import UserRole

        user = await self.user_repo.create(
            {
                "email": data.email,
                "hashed_password": hash_password(data.password),
                "full_name": data.full_name,
                "role": UserRole.CITIZEN,
                "city": data.city,
                "phone": data.phone,
                "preferred_language": data.preferred_language,
                "is_active": True,
            }
        )
        return UserResponse.model_validate(user)

    async def login(self, data: LoginRequest) -> TokenResponse:
        user = await self.user_repo.get_by_email(data.email)
        if not user or not verify_password(data.password, user.hashed_password):
            raise ValueError("Invalid credentials")
        if not user.is_active:
            raise ValueError("Account is disabled")

        await self.user_repo.update(user, {"last_login": datetime.now(UTC)})

        from app.core.config import settings

        refresh_token, jti, family_id = create_refresh_token(str(user.id))
        await self._register_refresh(family_id, jti)

        return TokenResponse(
            access_token=create_access_token(str(user.id)),
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def refresh(self, refresh_token: str) -> TokenResponse:
        try:
            payload = decode_token(refresh_token)
        except ValueError as e:
            raise ValueError(f"Invalid refresh token: {e}") from e

        if payload.get("type") != "refresh":
            raise ValueError("Not a refresh token")

        family_id = payload.get("fam")
        jti = payload.get("jti")
        user_id = payload.get("sub")

        if not family_id or not jti:
            raise ValueError("Malformed refresh token")

        if await is_family_revoked(family_id):
            raise ValueError("Refresh token has been revoked — please log in again")

        # Single-use rotation: reject and burn the whole family if this jti
        # was already used (theft/replay detection).
        rotated_ok = await validate_and_rotate(family_id, jti)
        if not rotated_ok:
            raise ValueError(
                "Refresh token reuse detected — session revoked, please log in again"
            )

        user = await self.user_repo.get_by_id(UUID(user_id))
        if not user or not user.is_active:
            await revoke_family(family_id)
            raise ValueError("User not found or inactive")

        from app.core.config import settings

        new_refresh_token, new_jti, _ = create_refresh_token(
            str(user.id), family_id=family_id
        )
        await self._register_refresh(family_id, new_jti)

        return TokenResponse(
            access_token=create_access_token(str(user.id)),
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def logout(self, refresh_token: str | None) -> None:
        """Revoke the refresh token family so it (and any rotated copies) can't be reused."""
        if not refresh_token:
            return
        try:
            payload = decode_token(refresh_token)
        except ValueError:
            return
        family_id = payload.get("fam")
        if family_id:
            await revoke_family(family_id)
            logger.info("auth.logout", family_id=family_id)

    async def _register_refresh(self, family_id: str, jti: str) -> None:
        from app.core.config import settings

        ttl_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
        await register_refresh_token(family_id, jti, ttl_seconds)

    async def get_current_user(self, token: str) -> User:
        try:
            payload = decode_token(token)
        except ValueError as e:
            raise ValueError(f"Invalid access token: {e}") from e

        if payload.get("type") != "access":
            raise ValueError("Not an access token")

        user_id = payload.get("sub")
        user = await self.user_repo.get_by_id(UUID(user_id))
        if not user or not user.is_active:
            raise ValueError("User not found or inactive")
        return user
