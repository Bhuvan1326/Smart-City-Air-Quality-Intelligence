from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import settings
from app.core.logging import logger
from jose import JWTError, jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    subject: str | Any, expires_delta: timedelta | None = None
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": str(subject),
        "exp": expire,
        "type": "access",
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    subject: str | Any,
    family_id: str | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, str, str]:
    """
    Create a refresh token.

    Returns (token, jti, family_id). `family_id` links every token issued from
    a single original login so that reuse of any token in the family (e.g. a
    stolen refresh token replayed after rotation) can be detected and the
    entire family revoked — this is the standard refresh-token-rotation
    defence against token theft.
    """
    jti = str(uuid.uuid4())
    family_id = family_id or str(uuid.uuid4())
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    payload = {
        "sub": str(subject),
        "exp": expire,
        "type": "refresh",
        "jti": jti,
        "fam": family_id,
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, jti, family_id


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}") from e


# ─── Refresh token rotation / revocation (Redis-backed) ──────────────────────
#
# Every refresh token's jti is tracked in Redis until it expires. On each
# refresh, the presented jti is checked and immediately rotated (single-use);
# a new token is minted in the same family. If a jti is presented that is no
# longer the active one for its family — i.e. it was already rotated out, or
# the family was revoked — this is treated as token reuse/theft and the
# *entire family* is revoked, forcing re-authentication.

_ACTIVE_PREFIX = "refresh:active"  # refresh:active:{family_id} -> current jti
_REVOKED_PREFIX = "refresh:revoked_family"  # refresh:revoked_family:{family_id} -> "1"


async def register_refresh_token(family_id: str, jti: str, ttl_seconds: int) -> None:
    from app.core.redis_client import get_redis

    redis = await get_redis()
    await redis.set(f"{_ACTIVE_PREFIX}:{family_id}", jti, ex=ttl_seconds)


async def is_family_revoked(family_id: str) -> bool:
    from app.core.redis_client import get_redis

    redis = await get_redis()
    return bool(await redis.get(f"{_REVOKED_PREFIX}:{family_id}"))


async def revoke_family(family_id: str, ttl_seconds: int | None = None) -> None:
    """Revoke every refresh token ever issued in this family (theft response / logout)."""
    from app.core.redis_client import get_redis

    redis = await get_redis()
    ttl = ttl_seconds or settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await redis.set(f"{_REVOKED_PREFIX}:{family_id}", "1", ex=ttl)
    await redis.delete(f"{_ACTIVE_PREFIX}:{family_id}")


async def validate_and_rotate(family_id: str, presented_jti: str) -> bool:
    """
    Returns True if `presented_jti` is the current active token for the
    family (safe to rotate). Returns False — and revokes the whole family —
    if the jti doesn't match the active one (reuse of an already-rotated or
    revoked token).
    """
    from app.core.redis_client import get_redis

    redis = await get_redis()
    active_jti = await redis.get(f"{_ACTIVE_PREFIX}:{family_id}")

    if active_jti is None:
        # No active token on record (expired naturally, or Redis was
        # flushed) — fail closed rather than silently trusting the token.
        return False

    if active_jti != presented_jti:
        logger.warning("refresh_token.reuse_detected", family_id=family_id)
        await revoke_family(family_id)
        return False

    return True
