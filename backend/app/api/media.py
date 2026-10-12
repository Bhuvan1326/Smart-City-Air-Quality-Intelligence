"""Authenticated evidence-media route (replaces the former public StaticFiles
mount). Mounted at settings.MEDIA_URL_PREFIX so URLs already stored in the
database (/media/evidence/...) keep their shape."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.services import media_access
from app.services.auth import AuthService
from app.services.evidence_storage import EvidenceStorage

router = APIRouter(tags=["Media"])


async def _optional_user(request: Request, session: AsyncSession) -> User | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        return await AuthService(session).get_current_user(token)
    except ValueError:
        return None


def _serve(rel_path: str) -> Response:
    found = EvidenceStorage().read_photo(f"{settings.MEDIA_URL_PREFIX}/{rel_path}")
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")
    body, media_type = found
    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


@router.get(settings.MEDIA_URL_PREFIX + "/{rel_path:path}", include_in_schema=False)
async def get_media(
    rel_path: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    exp: Annotated[int | None, Query()] = None,
    sig: Annotated[str | None, Query()] = None,
) -> Response:
    rel = media_access.normalise_rel_path(rel_path)
    if rel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")

    if sig is not None and exp is not None:
        if not media_access.verify(rel, exp, sig):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="Invalid or expired link"
            )
        return _serve(rel)

    user = await _optional_user(request, session)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not await media_access.can_read(session, user, rel):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")
    return _serve(rel)
