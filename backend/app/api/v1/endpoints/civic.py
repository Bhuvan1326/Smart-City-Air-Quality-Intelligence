"""Civic Issue Intelligence endpoint.

SCOPE: submission (with optional real AI photo classification, citizen
always able to confirm/override) -> GIS ward assignment (reusing
GISService, see app/services/civic_ward_assignment.py) -> SLA deadline
(app/services/civic_sla.py) -> authority status updates with a full audit
trail. Resolution-proof photos, AI before/after verification, citizen
confirm-resolved loops, and duplicate/recurring-issue detection are NOT
part of this phase — see app/models/civic_issue.py's module docstring.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, RequireOfficer, get_db
from app.core.sanitization import UnsafeInputError
from app.models.civic_issue import (
    CivicIssue,
    CivicIssueSeverity,
    CivicIssueStatus,
    CivicIssueStatusEvent,
    CivicIssueType,
    ClassificationSource,
)
from app.schemas.base import APIResponse
from app.schemas.civic import (
    CivicIssueCreate,
    CivicIssueListItem,
    CivicIssueResponse,
    CivicIssueStatusUpdate,
)
from app.services.civic_photo_classifier import classify_photo
from app.services.civic_sla import resolve_sla_and_department
from app.services.civic_ward_assignment import assign_ward
from app.services.evidence_storage import EvidenceStorage

router = APIRouter(prefix="/civic", tags=["Civic Issue Intelligence"])

_EXT_TO_MEDIA_TYPE = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}

# Only these transitions are allowed via this phase's status-update
# endpoint. OVERDUE is intentionally system-derived (is_overdue flag),
# not an officer-settable status here. VERIFICATION_PENDING/VERIFIED/
# REOPENED don't exist yet — see the module docstring for why.
_ALLOWED_TRANSITIONS: dict[CivicIssueStatus, set[CivicIssueStatus]] = {
    CivicIssueStatus.SUBMITTED: {CivicIssueStatus.TRIAGED, CivicIssueStatus.ASSIGNED},
    CivicIssueStatus.TRIAGED: {CivicIssueStatus.ASSIGNED, CivicIssueStatus.ESCALATED},
    CivicIssueStatus.ASSIGNED: {
        CivicIssueStatus.ACKNOWLEDGED,
        CivicIssueStatus.ESCALATED,
    },
    CivicIssueStatus.ACKNOWLEDGED: {
        CivicIssueStatus.IN_PROGRESS,
        CivicIssueStatus.ESCALATED,
    },
    CivicIssueStatus.IN_PROGRESS: {
        CivicIssueStatus.RESOLVED,
        CivicIssueStatus.ESCALATED,
    },
    CivicIssueStatus.RESOLVED: {CivicIssueStatus.CLOSED},
    CivicIssueStatus.ESCALATED: {
        CivicIssueStatus.ACKNOWLEDGED,
        CivicIssueStatus.IN_PROGRESS,
    },
}


def _decode_photo_for_classification(data_url: str) -> tuple[str, str]:
    """Returns (base64_payload, media_type) after validating the same way
    app.services.evidence_storage does, without writing to disk yet (the
    issue id needed for the storage path doesn't exist until after the
    row is created).
    """
    from app.services.evidence_storage import _decode_data_url

    raw, ext = _decode_data_url(data_url)
    import base64

    media_type = _EXT_TO_MEDIA_TYPE[ext]
    return base64.b64encode(raw).decode("ascii"), media_type


@router.post(
    "/issues",
    response_model=APIResponse[CivicIssueResponse],
    status_code=status.HTTP_201_CREATED,
)
async def submit_civic_issue(
    data: CivicIssueCreate,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[CivicIssueResponse]:
    citizen_type: CivicIssueType | None = None
    if data.issue_type:
        try:
            citizen_type = CivicIssueType(data.issue_type)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown issue_type '{data.issue_type}'",
            ) from e

    citizen_severity: CivicIssueSeverity | None = None
    if data.severity:
        try:
            citizen_severity = CivicIssueSeverity(data.severity)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown severity '{data.severity}'",
            ) from e

    ai_result = None
    if data.photo_data_url:
        try:
            image_base64, media_type = _decode_photo_for_classification(
                data.photo_data_url
            )
        except UnsafeInputError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
            ) from e
        ai_result = await classify_photo(
            image_base64=image_base64, media_type=media_type
        )

    if citizen_type is not None:
        final_type = citizen_type
        if ai_result is None:
            classification_source = ClassificationSource.CITIZEN_REPORTED
        elif ai_result.issue_type == citizen_type:
            classification_source = ClassificationSource.AI_SUGGESTED_CITIZEN_CONFIRMED
        else:
            classification_source = ClassificationSource.AI_SUGGESTED_CITIZEN_OVERRIDDEN
        final_severity = citizen_severity or (
            ai_result.suggested_severity
            if ai_result and ai_result.issue_type == citizen_type
            else CivicIssueSeverity.MODERATE
        )
    elif ai_result is not None and data.use_ai_suggestion:
        final_type = ai_result.issue_type
        classification_source = ClassificationSource.AI_SUGGESTED_CITIZEN_CONFIRMED
        final_severity = citizen_severity or ai_result.suggested_severity
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Provide issue_type yourself, or supply a photo and set "
                "use_ai_suggestion=true to accept the AI's suggestion. "
                "The AI suggestion is never applied without confirmation."
            ),
        )

    ward_result = await assign_ward(
        session, city=data.city, latitude=data.latitude, longitude=data.longitude
    )
    sla_hours, department = resolve_sla_and_department(final_type, final_severity)

    from geoalchemy2.elements import WKTElement

    geometry = WKTElement(f"POINT({data.longitude} {data.latitude})", srid=4326)

    now = datetime.now(UTC)
    issue = CivicIssue(
        reporter_id=current_user.id,
        city=data.city,
        ward_id=ward_result.ward_id,
        ward_assignment_method=ward_result.method.value,
        latitude=data.latitude,
        longitude=data.longitude,
        geometry=geometry,
        issue_type=final_type.value,
        classification_source=classification_source.value,
        ai_suggested_type=ai_result.issue_type.value if ai_result else None,
        ai_confidence=ai_result.confidence if ai_result else None,
        ai_suggested_severity=ai_result.suggested_severity.value if ai_result else None,
        ai_reasoning=ai_result.reasoning if ai_result else None,
        severity=final_severity.value,
        description=data.description,
        status=CivicIssueStatus.SUBMITTED.value,
        assigned_department=department,
        sla_hours=sla_hours,
        sla_deadline=now + timedelta(hours=sla_hours),
        is_overdue=False,
    )
    session.add(issue)
    await session.flush()

    if data.photo_data_url:
        photo_url = EvidenceStorage().save_photo(str(issue.id), data.photo_data_url)
        issue.photo_url = photo_url

    session.add(
        CivicIssueStatusEvent(
            issue_id=issue.id,
            from_status=None,
            to_status=CivicIssueStatus.SUBMITTED.value,
            changed_by_id=current_user.id,
            note="Issue submitted",
        )
    )
    await session.flush()
    await session.refresh(issue, attribute_names=["status_events"])

    return APIResponse(
        data=CivicIssueResponse.model_validate(issue), message="Civic issue submitted"
    )


@router.get("/issues", response_model=APIResponse[list[CivicIssueListItem]])
async def list_civic_issues(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
    ward_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    only_mine: bool = Query(default=False),
) -> APIResponse[list[CivicIssueListItem]]:
    stmt = select(CivicIssue).where(
        CivicIssue.city == city, CivicIssue.is_deleted.is_(False)
    )
    if ward_id:
        stmt = stmt.where(CivicIssue.ward_id == ward_id)
    if status_filter:
        stmt = stmt.where(CivicIssue.status == status_filter)
    if severity:
        stmt = stmt.where(CivicIssue.severity == severity)
    if only_mine:
        stmt = stmt.where(CivicIssue.reporter_id == current_user.id)
    stmt = stmt.order_by(CivicIssue.created_at.desc()).limit(200)

    result = await session.execute(stmt)
    issues = result.scalars().all()
    return APIResponse(data=[CivicIssueListItem.model_validate(i) for i in issues])


@router.get("/issues/{issue_id}", response_model=APIResponse[CivicIssueResponse])
async def get_civic_issue(
    issue_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[CivicIssueResponse]:
    result = await session.execute(
        select(CivicIssue)
        .options(selectinload(CivicIssue.status_events))
        .where(CivicIssue.id == issue_id, CivicIssue.is_deleted.is_(False))
    )
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Civic issue not found"
        )
    return APIResponse(data=CivicIssueResponse.model_validate(issue))


@router.patch(
    "/issues/{issue_id}/status",
    response_model=APIResponse[CivicIssueResponse],
    dependencies=[RequireOfficer],
)
async def update_civic_issue_status(
    issue_id: UUID,
    data: CivicIssueStatusUpdate,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[CivicIssueResponse]:
    result = await session.execute(
        select(CivicIssue)
        .options(selectinload(CivicIssue.status_events))
        .where(CivicIssue.id == issue_id, CivicIssue.is_deleted.is_(False))
    )
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Civic issue not found"
        )

    try:
        current_status = CivicIssueStatus(issue.status)
        to_status = CivicIssueStatus(data.to_status)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from e

    allowed = _ALLOWED_TRANSITIONS.get(current_status, set())
    if to_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot transition from '{current_status.value}' to "
                f"'{to_status.value}'. Allowed: "
                f"{sorted(s.value for s in allowed) or 'none'}."
            ),
        )

    issue.status = to_status.value
    session.add(
        CivicIssueStatusEvent(
            issue_id=issue.id,
            from_status=current_status.value,
            to_status=to_status.value,
            changed_by_id=current_user.id,
            note=data.note,
        )
    )
    await session.flush()
    await session.refresh(issue, attribute_names=["status_events"])

    return APIResponse(
        data=CivicIssueResponse.model_validate(issue), message="Status updated"
    )
