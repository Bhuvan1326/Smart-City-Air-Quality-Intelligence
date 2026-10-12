from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.core.config import settings
from app.schemas.base import APIResponse, BaseSchema
from app.services import media_access

router = APIRouter(prefix="/media", tags=["Media"])


class SignedUrlRequest(BaseSchema):
    path: str  # the stored URL path, e.g. /media/evidence/<id>/<file>.jpg


class SignedUrlResponse(BaseSchema):
    url: str
    expires_at: datetime


@router.post("/signed-url", response_model=APIResponse[SignedUrlResponse])
async def create_signed_url(
    data: SignedUrlRequest,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[SignedUrlResponse]:
    """Mint a short-lived link for evidence the caller may already read."""
    prefix = settings.MEDIA_URL_PREFIX + "/"
    rel = (
        media_access.normalise_rel_path(data.path[len(prefix) :])
        if data.path.startswith(prefix)
        else None
    )
    if rel is None or not await media_access.can_read(session, current_user, rel):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")
    exp, sig = media_access.sign(rel)
    return APIResponse(
        data=SignedUrlResponse(
            url=f"{prefix}{rel}?exp={exp}&sig={sig}",
            expires_at=datetime.fromtimestamp(exp, tz=UTC),
        )
    )
