from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from app.api.deps import CurrentUser, RequireOfficer, get_db
from app.core.logging import logger
from app.core.sanitization import UnsafeInputError
from app.models.enforcement import ActionStatus, EnforcementAction
from app.models.user import User, UserRole
from app.schemas.base import APIResponse, PaginatedResponse
from app.schemas.enforcement import (
    EnforcementActionCreate,
    EnforcementActionResponse,
    EnforcementActionUpdate,
    EvidenceSubmissionRequest,
    EvidenceSubmissionResponse,
)
from app.services.evidence_storage import EvidenceStorage
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/enforcement", tags=["Enforcement"])


@router.get(
    "", response_model=APIResponse[PaginatedResponse[EnforcementActionResponse]]
)
async def list_enforcement_actions(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str | None = Query(None),
    status_filter: ActionStatus | None = Query(None, alias="status"),
    ward_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> APIResponse[PaginatedResponse[EnforcementActionResponse]]:
    query = select(EnforcementAction).where(EnforcementAction.is_deleted.is_(False))

    # Field inspectors only see their own actions
    if current_user.role == UserRole.FIELD_INSPECTOR:
        query = query.where(EnforcementAction.officer_id == current_user.id)
    elif city:
        query = query.where(EnforcementAction.city == city)

    if status_filter:
        query = query.where(EnforcementAction.status == status_filter)
    if ward_id:
        query = query.where(EnforcementAction.ward_id == ward_id)

    query = query.order_by(
        desc(EnforcementAction.priority_score), desc(EnforcementAction.created_at)
    )

    from sqlalchemy import func
    from sqlalchemy import select as sel

    count_q = sel(func.count()).select_from(query.subquery())
    total = await session.scalar(count_q) or 0

    result = await session.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )
    actions = list(result.scalars().all())

    items = [EnforcementActionResponse.model_validate(a) for a in actions]
    return APIResponse(data=PaginatedResponse.create(items, total, page, page_size))


@router.post(
    "",
    response_model=APIResponse[EnforcementActionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_enforcement_action(
    data: EnforcementActionCreate,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[EnforcementActionResponse]:
    if current_user.role == UserRole.CITIZEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    from geoalchemy2.elements import WKTElement

    geometry = None
    if data.latitude and data.longitude:
        geometry = WKTElement(f"POINT({data.longitude} {data.latitude})", srid=4326)

    action = EnforcementAction(
        officer_id=current_user.id,
        source_id=data.source_id,
        ward_id=data.ward_id,
        city=data.city,
        action_type=data.action_type,
        title=data.title,
        description=data.description,
        latitude=data.latitude,
        longitude=data.longitude,
        geometry=geometry,
        priority_score=data.priority_score,
    )
    session.add(action)
    await session.flush()
    await session.refresh(action)
    return APIResponse(
        data=EnforcementActionResponse.model_validate(action), message="Action created"
    )


@router.patch("/{action_id}", response_model=APIResponse[EnforcementActionResponse])
async def update_enforcement_action(
    action_id: UUID,
    data: EnforcementActionUpdate,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[EnforcementActionResponse]:
    result = await session.execute(
        select(EnforcementAction).where(
            EnforcementAction.id == action_id,
            EnforcementAction.is_deleted.is_(False),
        )
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Action not found"
        )

    if (
        current_user.role == UserRole.FIELD_INSPECTOR
        and action.officer_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify other officer's actions",
        )

    if data.status:
        action.status = data.status
        if data.status == ActionStatus.COMPLETED:
            action.resolved_at = datetime.now(timezone.utc)
    if data.notes is not None:
        action.notes = data.notes
    if data.outcome_score is not None:
        action.outcome_score = data.outcome_score
    if data.evidence_urls is not None:
        action.evidence_urls = data.evidence_urls

    session.add(action)
    await session.flush()
    await session.refresh(action)
    return APIResponse(data=EnforcementActionResponse.model_validate(action))


@router.get("/{action_id}", response_model=APIResponse[EnforcementActionResponse])
async def get_enforcement_action(
    action_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[EnforcementActionResponse]:
    result = await session.execute(
        select(EnforcementAction).where(
            EnforcementAction.id == action_id,
            EnforcementAction.is_deleted.is_(False),
        )
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Action not found"
        )
    return APIResponse(data=EnforcementActionResponse.model_validate(action))


@router.post(
    "/{action_id}/evidence", response_model=APIResponse[EvidenceSubmissionResponse]
)
async def submit_inspection_evidence(
    action_id: UUID,
    data: EvidenceSubmissionRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireOfficer,
) -> APIResponse[EvidenceSubmissionResponse]:
    """
    Completes an inspection with notes/status/photos. Built for the offline
    PWA inspection flow (see frontend lib/offline/sync-manager.ts): the form
    can be filled out with no connectivity, queued in IndexedDB, and this
    endpoint gets called once connectivity returns — possibly more than
    once if a response is lost mid-flight and the client retries. `client_id`
    is an idempotency key generated on-device when the officer completes the
    form; a second submission with the same client_id updates the existing
    evidence record rather than duplicating the photos.
    """
    result = await session.execute(
        select(EnforcementAction).where(
            EnforcementAction.id == action_id,
            EnforcementAction.is_deleted.is_(False),
        )
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Action not found"
        )

    existing_metadata = action.evidence_metadata or {}
    was_duplicate = existing_metadata.get("client_id") == data.client_id
    storage = EvidenceStorage()

    if was_duplicate:
        # Same submission replayed (retry after a lost response) — return
        # the already-saved result instead of saving the photos again.
        logger.info(
            "evidence.duplicate_submission_ignored",
            action_id=str(action_id),
            client_id=data.client_id,
        )
        return APIResponse(
            data=EvidenceSubmissionResponse(
                action_id=action.id,
                client_id=data.client_id,
                status=action.status,
                evidence_urls=action.evidence_urls or [],
                photos_saved=0,
                was_duplicate=True,
            )
        )

    saved_urls: list[str] = []
    for photo_data_url in data.photos:
        try:
            url = storage.save_photo(str(action_id), photo_data_url)
            saved_urls.append(url)
        except UnsafeInputError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
            ) from e

    action.status = data.status
    action.notes = data.notes
    if data.outcome_score is not None:
        action.outcome_score = data.outcome_score
    action.evidence_urls = list(action.evidence_urls or []) + saved_urls
    action.evidence_metadata = {
        "client_id": data.client_id,
        "captured_at": data.captured_at.isoformat(),
        "latitude": data.latitude,
        "longitude": data.longitude,
        "submitted_offline": True,
    }
    if data.status == ActionStatus.COMPLETED:
        action.resolved_at = datetime.now(timezone.utc)

    session.add(action)
    await session.commit()
    await session.refresh(action)

    logger.info(
        "evidence.submitted",
        action_id=str(action_id),
        officer_id=str(current_user.id),
        photos=len(saved_urls),
    )

    return APIResponse(
        data=EvidenceSubmissionResponse(
            action_id=action.id,
            client_id=data.client_id,
            status=action.status,
            evidence_urls=action.evidence_urls,
            photos_saved=len(saved_urls),
            was_duplicate=False,
        )
    )
