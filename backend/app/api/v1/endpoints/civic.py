"""Civic Issue Intelligence endpoint.

Covers: submission (real AI photo classification, citizen always
confirms/overrides) -> duplicate/cluster detection -> real PostGIS
ward assignment where a boundary is on file -> municipality/ward-office/
department/representative context -> SLA -> officer status updates ->
resolution proof -> AI before/after verification -> citizen confirmation
(with reopen) -> automatic SLA escalation (also manually triggerable).

See app/models/civic_issue.py and the individual services under
app/services/civic_* for the honesty rules behind each piece.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, RequireAdmin, RequireOfficer, get_db
from app.core.sanitization import UnsafeInputError
from app.models.civic_governance import (
    Municipality,
    WardBoundary,
    WardOffice,
    WardRepresentative,
)
from app.models.civic_issue import (
    CivicIssue,
    CivicIssueCluster,
    CivicIssueSeverity,
    CivicIssueStatus,
    CivicIssueStatusEvent,
    CivicIssueType,
    ClassificationSource,
)
from app.models.user import UserRole
from app.schemas.base import APIResponse
from app.schemas.civic import (
    CivicIssueCitizenVerifyRequest,
    CivicIssueCreate,
    CivicIssueListItem,
    CivicIssueResolveRequest,
    CivicIssueResponse,
    CivicIssueStatusUpdate,
    ElectedWardRepresentative,
    EscalationRunResponse,
    MunicipalityCreate,
    MunicipalityResponse,
    ResponsibleCivicAuthority,
    WardBoundaryCreate,
    WardBoundaryResponse,
    WardOfficeCreate,
    WardOfficeResponse,
    WardRepresentativeCreate,
    WardRepresentativeResponse,
)
from app.services.civic_duplicate_detection import find_matching_cluster
from app.services.civic_escalation import check_and_escalate_overdue_issues
from app.services.civic_governance import (
    get_municipality,
    get_ward_office,
    get_ward_representative,
)
from app.services.civic_photo_classifier import classify_photo
from app.services.civic_resolution_verification import verify_resolution
from app.services.civic_sla import resolve_sla_and_department
from app.services.civic_ward_assignment import assign_ward
from app.services.evidence_storage import EvidenceStorage

router = APIRouter(prefix="/civic", tags=["Civic Issue Intelligence"])

_EXT_TO_MEDIA_TYPE = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}

# Statuses that must be reached through a dedicated endpoint (resolve /
# citizen-verify), never through the generic status-update endpoint —
# "authority cannot simply click Resolved" without evidence.
_RESTRICTED_STATUSES = {
    CivicIssueStatus.RESOLVED,
    CivicIssueStatus.VERIFICATION_PENDING,
    CivicIssueStatus.VERIFIED,
    CivicIssueStatus.REOPENED,
}

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
        CivicIssueStatus.ESCALATED
    },  # RESOLVED via /resolve only
    CivicIssueStatus.VERIFIED: {CivicIssueStatus.CLOSED},
    CivicIssueStatus.ESCALATED: {
        CivicIssueStatus.ACKNOWLEDGED,
        CivicIssueStatus.IN_PROGRESS,
    },
    CivicIssueStatus.REOPENED: {
        CivicIssueStatus.ACKNOWLEDGED,
        CivicIssueStatus.IN_PROGRESS,
    },
}


def _decode_photo_for_classification(data_url: str) -> tuple[str, str]:
    from app.services.evidence_storage import _decode_data_url

    raw, ext = _decode_data_url(data_url)
    import base64

    return base64.b64encode(raw).decode("ascii"), _EXT_TO_MEDIA_TYPE[ext]


async def _build_governance_context(
    session: AsyncSession, *, city: str, ward_id: str | None, department: str | None
) -> tuple[ResponsibleCivicAuthority, ElectedWardRepresentative | None]:
    municipality = await get_municipality(session, city)
    ward_office = await get_ward_office(session, city, ward_id) if ward_id else None
    representative = (
        await get_ward_representative(session, city, ward_id) if ward_id else None
    )

    authority = ResponsibleCivicAuthority(
        department=department,
        municipality_name=municipality.name if municipality else None,
        ward_office_name=ward_office.office_name if ward_office else None,
        ward_office_contact_phone=ward_office.contact_phone if ward_office else None,
    )
    representative_out = (
        ElectedWardRepresentative(
            name=representative.name,
            role=representative.role,
            photo_url=representative.photo_url,
            official_profile_url=representative.official_profile_url,
            official_contact=representative.official_contact,
            term_start=representative.term_start,
            term_end=representative.term_end,
            source=representative.source,
        )
        if representative
        else None
    )
    return authority, representative_out


async def _to_response(session: AsyncSession, issue: CivicIssue) -> CivicIssueResponse:
    authority, representative = await _build_governance_context(
        session,
        city=issue.city,
        ward_id=issue.ward_id,
        department=issue.assigned_department,
    )
    duplicate_report_count = None
    if issue.cluster_id is not None:
        cluster_result = await session.execute(
            select(CivicIssueCluster.report_count).where(
                CivicIssueCluster.id == issue.cluster_id
            )
        )
        row = cluster_result.first()
        duplicate_report_count = row[0] if row else None

    return CivicIssueResponse(
        **{
            k: getattr(issue, k)
            for k in (
                "id",
                "reporter_id",
                "city",
                "ward_id",
                "ward_assignment_method",
                "latitude",
                "longitude",
                "issue_type",
                "classification_source",
                "ai_suggested_type",
                "ai_confidence",
                "ai_suggested_severity",
                "ai_reasoning",
                "severity",
                "description",
                "photo_url",
                "status",
                "assigned_department",
                "sla_hours",
                "sla_deadline",
                "is_overdue",
                "created_at",
                "updated_at",
                "resolution_photo_url",
                "resolution_notes",
                "work_order_reference",
                "resolved_at",
                "resolved_by_id",
                "ai_verification_result",
                "ai_verification_confidence",
                "ai_verification_reasoning",
                "citizen_verified",
                "citizen_verified_at",
                "citizen_verification_note",
                "reopen_count",
                "cluster_id",
                "is_duplicate_of_cluster",
            )
        },
        status_events=list(issue.status_events),
        duplicate_report_count=duplicate_report_count,
        responsible_authority=authority,
        elected_representative=representative,
    )


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
                "use_ai_suggestion=true to accept the AI's suggestion."
            ),
        )

    ward_result = await assign_ward(
        session, city=data.city, latitude=data.latitude, longitude=data.longitude
    )
    sla_hours, department = resolve_sla_and_department(final_type, final_severity)

    now = datetime.now(UTC)
    duplicate_match = await find_matching_cluster(
        session,
        city=data.city,
        issue_type=final_type.value,
        latitude=data.latitude,
        longitude=data.longitude,
        now=now,
    )
    if duplicate_match is not None:
        cluster = duplicate_match.cluster
        cluster.report_count += 1
        cluster.last_reported_at = now
        is_duplicate = True
    else:
        cluster = CivicIssueCluster(
            city=data.city,
            ward_id=ward_result.ward_id,
            issue_type=final_type.value,
            centroid_latitude=data.latitude,
            centroid_longitude=data.longitude,
            report_count=1,
            first_reported_at=now,
            last_reported_at=now,
        )
        session.add(cluster)
        await session.flush()
        is_duplicate = False

    from geoalchemy2.elements import WKTElement

    geometry = WKTElement(f"POINT({data.longitude} {data.latitude})", srid=4326)

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
        cluster_id=cluster.id,
        is_duplicate_of_cluster=is_duplicate,
    )
    session.add(issue)
    await session.flush()

    if data.photo_data_url:
        issue.photo_url = EvidenceStorage().save_photo(
            str(issue.id), data.photo_data_url
        )

    session.add(
        CivicIssueStatusEvent(
            issue_id=issue.id,
            from_status=None,
            to_status=CivicIssueStatus.SUBMITTED.value,
            changed_by_id=current_user.id,
            note="Issue submitted"
            + (
                " (matched to an existing cluster of similar reports)"
                if is_duplicate
                else ""
            ),
        )
    )
    await session.flush()
    await session.refresh(issue, attribute_names=["status_events"])

    return APIResponse(
        data=await _to_response(session, issue), message="Civic issue submitted"
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
    # Deliberately the same 404 for "doesn't exist" and "exists but isn't
    # yours" — a citizen shouldn't be able to distinguish the two by
    # probing IDs. Officers/admins/inspectors need to see any issue in
    # order to process it; a citizen may only see their own report.
    officer_roles = {
        UserRole.CITY_ADMINISTRATOR,
        UserRole.POLLUTION_CONTROL_OFFICER,
        UserRole.FIELD_INSPECTOR,
    }
    if issue is None or (
        current_user.role not in officer_roles and issue.reporter_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Civic issue not found"
        )
    return APIResponse(data=await _to_response(session, issue))


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

    if to_status in _RESTRICTED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"'{to_status.value}' cannot be set directly. Use POST "
                "/civic/issues/{id}/resolve or /citizen-verify instead."
            ),
        )

    allowed = _ALLOWED_TRANSITIONS.get(current_status, set())
    if to_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot transition from '{current_status.value}' to '{to_status.value}'. "
                f"Allowed: {sorted(s.value for s in allowed) or 'none'}."
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
        data=await _to_response(session, issue), message="Status updated"
    )


@router.post(
    "/issues/{issue_id}/resolve",
    response_model=APIResponse[CivicIssueResponse],
    dependencies=[RequireOfficer],
)
async def resolve_civic_issue(
    issue_id: UUID,
    data: CivicIssueResolveRequest,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[CivicIssueResponse]:
    """Authority resolution requires an after-photo and notes — never a
    bare status flip. Runs real AI before/after verification if
    configured; the result is advisory only (never absolute certainty)
    and does not block the transition to citizen verification.
    """
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

    current_status = CivicIssueStatus(issue.status)
    if current_status not in (CivicIssueStatus.IN_PROGRESS, CivicIssueStatus.ESCALATED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot resolve an issue in status '{current_status.value}'.",
        )

    try:
        after_photo_url = EvidenceStorage().save_photo(
            f"{issue.id}-resolution", data.after_photo_data_url
        )
    except UnsafeInputError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from e

    now = datetime.now(UTC)
    issue.resolution_photo_url = after_photo_url
    issue.resolution_notes = data.resolution_notes
    issue.work_order_reference = data.work_order_reference
    issue.resolved_at = now
    issue.resolved_by_id = current_user.id

    verification = await verify_resolution(
        before_photo_url=issue.photo_url, after_photo_data_url=data.after_photo_data_url
    )
    if verification is not None:
        issue.ai_verification_result = verification.result.value
        issue.ai_verification_confidence = verification.confidence
        issue.ai_verification_reasoning = verification.reasoning
    else:
        issue.ai_verification_result = None
        issue.ai_verification_confidence = None
        issue.ai_verification_reasoning = (
            "AI verification unavailable (no before photo on file, or the "
            "verification provider is not configured)."
        )

    issue.status = CivicIssueStatus.VERIFICATION_PENDING.value
    session.add(
        CivicIssueStatusEvent(
            issue_id=issue.id,
            from_status=current_status.value,
            to_status=CivicIssueStatus.VERIFICATION_PENDING.value,
            changed_by_id=current_user.id,
            note=(
                f"Resolution submitted. AI verification: "
                f"{issue.ai_verification_result or 'unavailable'}."
            ),
        )
    )
    await session.flush()
    await session.refresh(issue, attribute_names=["status_events"])
    return APIResponse(
        data=await _to_response(session, issue),
        message="Resolution submitted — pending citizen confirmation",
    )


@router.post(
    "/issues/{issue_id}/citizen-verify",
    response_model=APIResponse[CivicIssueResponse],
)
async def citizen_verify_civic_issue(
    issue_id: UUID,
    data: CivicIssueCitizenVerifyRequest,
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

    if issue.reporter_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the citizen who reported this issue can confirm its resolution.",
        )

    current_status = CivicIssueStatus(issue.status)
    if current_status != CivicIssueStatus.VERIFICATION_PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Issue is not awaiting citizen verification (status: '{current_status.value}').",
        )

    now = datetime.now(UTC)
    issue.citizen_verified = data.confirmed
    issue.citizen_verified_at = now
    issue.citizen_verification_note = data.note

    if data.confirmed:
        issue.status = CivicIssueStatus.VERIFIED.value
        note = "Citizen confirmed the issue was resolved."
    else:
        issue.status = CivicIssueStatus.REOPENED.value
        issue.reopen_count += 1
        note = "Citizen reported the issue was NOT actually resolved — reopened."

    session.add(
        CivicIssueStatusEvent(
            issue_id=issue.id,
            from_status=current_status.value,
            to_status=issue.status,
            changed_by_id=current_user.id,
            note=note,
        )
    )
    await session.flush()
    await session.refresh(issue, attribute_names=["status_events"])
    return APIResponse(
        data=await _to_response(session, issue), message="Verification recorded"
    )


@router.post(
    "/escalation/run",
    response_model=APIResponse[EscalationRunResponse],
    dependencies=[RequireAdmin],
)
async def run_escalation_check(
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str | None = Query(default=None),
) -> APIResponse[EscalationRunResponse]:
    """Manually trigger the same SLA-breach check the Celery beat
    schedule runs every 15 minutes — useful when Celery/Redis isn't
    running (see app/workers/tasks/civic_escalation.py).
    """
    result = await check_and_escalate_overdue_issues(session, city=city)
    return APIResponse(
        data=EscalationRunResponse(
            checked=result.checked,
            newly_overdue=result.newly_overdue,
            newly_escalated=result.newly_escalated,
        )
    )


# ─── Civic governance CRUD (admin-entered, no defaults) ─────────────────────


@router.get("/municipalities", response_model=APIResponse[list[MunicipalityResponse]])
async def list_municipalities(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str | None = Query(default=None),
) -> APIResponse[list[MunicipalityResponse]]:
    stmt = select(Municipality).where(Municipality.is_deleted.is_(False))
    if city:
        stmt = stmt.where(Municipality.city == city)
    result = await session.execute(stmt)
    return APIResponse(
        data=[MunicipalityResponse.model_validate(m) for m in result.scalars().all()]
    )


@router.post(
    "/municipalities",
    response_model=APIResponse[MunicipalityResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[RequireAdmin],
)
async def create_municipality(
    data: MunicipalityCreate, session: Annotated[AsyncSession, Depends(get_db)]
) -> APIResponse[MunicipalityResponse]:
    record = Municipality(**data.model_dump())
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return APIResponse(data=MunicipalityResponse.model_validate(record))


@router.get("/ward-offices", response_model=APIResponse[list[WardOfficeResponse]])
async def list_ward_offices(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[list[WardOfficeResponse]]:
    result = await session.execute(
        select(WardOffice).where(
            WardOffice.city == city, WardOffice.is_deleted.is_(False)
        )
    )
    return APIResponse(
        data=[WardOfficeResponse.model_validate(w) for w in result.scalars().all()]
    )


@router.post(
    "/ward-offices",
    response_model=APIResponse[WardOfficeResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[RequireAdmin],
)
async def create_ward_office(
    data: WardOfficeCreate, session: Annotated[AsyncSession, Depends(get_db)]
) -> APIResponse[WardOfficeResponse]:
    record = WardOffice(**data.model_dump())
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return APIResponse(data=WardOfficeResponse.model_validate(record))


@router.get(
    "/representatives", response_model=APIResponse[list[WardRepresentativeResponse]]
)
async def list_ward_representatives(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[list[WardRepresentativeResponse]]:
    result = await session.execute(
        select(WardRepresentative).where(
            WardRepresentative.city == city, WardRepresentative.is_deleted.is_(False)
        )
    )
    return APIResponse(
        data=[
            WardRepresentativeResponse.model_validate(r) for r in result.scalars().all()
        ]
    )


@router.post(
    "/representatives",
    response_model=APIResponse[WardRepresentativeResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[RequireAdmin],
)
async def create_ward_representative(
    data: WardRepresentativeCreate, session: Annotated[AsyncSession, Depends(get_db)]
) -> APIResponse[WardRepresentativeResponse]:
    record = WardRepresentative(**data.model_dump())
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return APIResponse(data=WardRepresentativeResponse.model_validate(record))


@router.post(
    "/ward-boundaries",
    response_model=APIResponse[WardBoundaryResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[RequireAdmin],
)
async def create_ward_boundary(
    data: WardBoundaryCreate, session: Annotated[AsyncSession, Depends(get_db)]
) -> APIResponse[WardBoundaryResponse]:
    from geoalchemy2.elements import WKTElement

    ring_wkt = ", ".join(f"{lon} {lat}" for lon, lat in data.ring)
    geometry = WKTElement(f"POLYGON(({ring_wkt}))", srid=4326)

    record = WardBoundary(
        city=data.city,
        ward_id=data.ward_id,
        geometry=geometry,
        source=data.source,
        effective_from=data.effective_from,
        effective_to=data.effective_to,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return APIResponse(data=WardBoundaryResponse.model_validate(record))
