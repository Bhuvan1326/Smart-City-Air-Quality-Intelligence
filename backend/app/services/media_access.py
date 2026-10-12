"""Authorization and short-lived signing for evidence media.

Evidence files live at  <MEDIA_ROOT>/evidence/<owner>/<uuid>.<ext>  where
<owner> is a civic issue id, "<issue id>-resolution", or an enforcement action
id. Rules:
  * staff (administrator / pollution officer / field inspector): any evidence;
  * citizen: only evidence belonging to a civic issue they reported;
  * everyone else / unknown owner: denied (reported as 404, no existence leak).
Signed links (HMAC-SHA256 over path + expiry, key derived from SECRET_KEY)
exist so an <img src> — which cannot send an Authorization header — can load a
file the minting user was already authorized to read, for a few minutes only.
"""

import hashlib
import hmac
import time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.civic_issue import CivicIssue
from app.models.user import User, UserRole

STAFF_ROLES = frozenset(
    {
        UserRole.CITY_ADMINISTRATOR,
        UserRole.POLLUTION_CONTROL_OFFICER,
        UserRole.FIELD_INSPECTOR,
    }
)


def _key() -> bytes:
    return hmac.new(
        settings.SECRET_KEY.encode(), b"evidence-media-signing-v1", hashlib.sha256
    ).digest()


def normalise_rel_path(rel_path: str) -> str | None:
    """'evidence/<owner>/<file>' or None if it is not a plain 3-part path."""
    parts = rel_path.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "evidence":
        return None
    if any(p in ("", ".", "..") or "\\" in p or "\x00" in p for p in parts):
        return None
    return "/".join(parts)


def sign(rel_path: str, ttl_seconds: int | None = None, now: float | None = None):
    ttl = settings.MEDIA_SIGNED_URL_TTL_SECONDS if ttl_seconds is None else ttl_seconds
    exp = int((time.time() if now is None else now) + ttl)
    sig = hmac.new(_key(), f"{rel_path}|{exp}".encode(), hashlib.sha256).hexdigest()
    return exp, sig


def verify(rel_path: str, exp: int, sig: str, now: float | None = None) -> bool:
    if (time.time() if now is None else now) > exp:
        return False
    expected = hmac.new(
        _key(), f"{rel_path}|{exp}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig)


def owner_issue_id(rel_path: str) -> UUID | None:
    owner = rel_path.split("/")[1].removesuffix("-resolution")
    try:
        return UUID(owner)
    except ValueError:
        return None


async def can_read(session: AsyncSession, user: User, rel_path: str) -> bool:
    if user.role in STAFF_ROLES:
        return True
    if user.role != UserRole.CITIZEN:
        return False
    issue_id = owner_issue_id(rel_path)
    if issue_id is None:
        return False
    found = await session.scalar(
        select(CivicIssue.id).where(
            CivicIssue.id == issue_id,
            CivicIssue.reporter_id == user.id,
            CivicIssue.is_deleted.is_(False),
        )
    )
    return found is not None
