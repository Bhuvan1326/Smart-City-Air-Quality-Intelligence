from datetime import date, datetime
from uuid import UUID

from app.core.sanitization import sanitize_text
from app.schemas.base import BaseSchema
from pydantic import Field, field_validator


class CivicIssueCreate(BaseSchema):
    city: str = Field(..., min_length=1, max_length=100)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    description: str | None = Field(default=None, max_length=2000)
    # Citizen's own choice of issue type. If a photo is also supplied and
    # AI classification succeeds, the citizen's choice still wins unless
    # they explicitly pass use_ai_suggestion=true — the AI never overrides
    # the citizen silently.
    issue_type: str | None = Field(default=None)
    severity: str | None = Field(default=None)
    # data:image/jpeg;base64,... — same accepted format as the existing
    # enforcement evidence-photo flow (see app/services/evidence_storage.py).
    photo_data_url: str | None = Field(default=None)
    use_ai_suggestion: bool = Field(default=False)

    @field_validator("city")
    @classmethod
    def sanitize_city(cls, v: str) -> str:
        return sanitize_text(v.strip())

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v: str | None) -> str | None:
        return sanitize_text(v) if v else v


class CivicIssueStatusUpdate(BaseSchema):
    to_status: str = Field(...)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("note")
    @classmethod
    def sanitize_note(cls, v: str | None) -> str | None:
        return sanitize_text(v) if v else v


class CivicIssueResolveRequest(BaseSchema):
    after_photo_data_url: str = Field(...)
    resolution_notes: str = Field(..., min_length=1, max_length=2000)
    work_order_reference: str | None = Field(default=None, max_length=200)

    @field_validator("resolution_notes")
    @classmethod
    def sanitize_notes(cls, v: str) -> str:
        return sanitize_text(v)


class CivicIssueCitizenVerifyRequest(BaseSchema):
    confirmed: bool = Field(...)
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("note")
    @classmethod
    def sanitize_note(cls, v: str | None) -> str | None:
        return sanitize_text(v) if v else v


class CivicIssueStatusEventResponse(BaseSchema):
    id: UUID
    from_status: str | None
    to_status: str
    changed_by_id: UUID | None
    note: str | None
    created_at: datetime


class ResponsibleCivicAuthority(BaseSchema):
    """The operational body responsible for acting on this issue —
    NEVER the elected representative. Populated from
    app.services.civic_governance + app.services.civic_sla; any field is
    null if no admin-entered record exists (never fabricated).
    """

    department: str | None
    municipality_name: str | None
    ward_office_name: str | None
    ward_office_contact_phone: str | None


class ElectedWardRepresentative(BaseSchema):
    """Accountability/contact context ONLY — this person does not
    personally perform municipal operations. Null if no admin-entered
    record exists for this ward.
    """

    name: str
    role: str
    photo_url: str | None
    official_profile_url: str | None
    official_contact: str | None
    term_start: date | None
    term_end: date | None
    source: str


class CivicIssueResponse(BaseSchema):
    id: UUID
    reporter_id: UUID
    city: str
    ward_id: str | None
    ward_assignment_method: str
    latitude: float
    longitude: float
    issue_type: str
    classification_source: str
    ai_suggested_type: str | None
    ai_confidence: float | None
    ai_suggested_severity: str | None
    ai_reasoning: str | None
    severity: str
    description: str | None
    photo_url: str | None
    status: str
    assigned_department: str | None
    sla_hours: float
    sla_deadline: datetime
    is_overdue: bool
    created_at: datetime
    updated_at: datetime
    status_events: list[CivicIssueStatusEventResponse] = Field(default_factory=list)

    resolution_photo_url: str | None = None
    resolution_notes: str | None = None
    work_order_reference: str | None = None
    resolved_at: datetime | None = None
    resolved_by_id: UUID | None = None
    ai_verification_result: str | None = None
    ai_verification_confidence: float | None = None
    ai_verification_reasoning: str | None = None
    citizen_verified: bool | None = None
    citizen_verified_at: datetime | None = None
    citizen_verification_note: str | None = None
    reopen_count: int = 0
    cluster_id: UUID | None = None
    is_duplicate_of_cluster: bool = False
    duplicate_report_count: int | None = None

    responsible_authority: ResponsibleCivicAuthority | None = None
    elected_representative: ElectedWardRepresentative | None = None


class CivicIssueListItem(BaseSchema):
    """Lighter-weight shape for list views (no status_events)."""

    id: UUID
    reporter_id: UUID
    city: str
    ward_id: str | None
    issue_type: str
    severity: str
    status: str
    assigned_department: str | None
    sla_deadline: datetime
    is_overdue: bool
    photo_url: str | None
    created_at: datetime
    is_duplicate_of_cluster: bool = False
    reopen_count: int = 0


class CivicIssueClusterResponse(BaseSchema):
    id: UUID
    city: str
    ward_id: str | None
    issue_type: str
    centroid_latitude: float
    centroid_longitude: float
    report_count: int
    first_reported_at: datetime
    last_reported_at: datetime


# ─── Civic governance CRUD (admin-entered, no defaults) ─────────────────────


class MunicipalityCreate(BaseSchema):
    city: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    official_website: str | None = Field(default=None, max_length=500)
    source_note: str | None = Field(default=None, max_length=2000)


class MunicipalityUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    official_website: str | None = Field(default=None, max_length=500)
    source_note: str | None = Field(default=None, max_length=2000)


class MunicipalityResponse(BaseSchema):
    id: UUID
    city: str
    name: str
    official_website: str | None
    source_note: str | None
    verified_at: datetime | None


class WardOfficeCreate(BaseSchema):
    city: str = Field(..., min_length=1, max_length=100)
    ward_id: str = Field(..., min_length=1, max_length=50)
    office_name: str = Field(..., min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=2000)
    contact_phone: str | None = Field(default=None, max_length=50)
    contact_email: str | None = Field(default=None, max_length=200)
    source_note: str | None = Field(default=None, max_length=2000)


class WardOfficeResponse(BaseSchema):
    id: UUID
    city: str
    ward_id: str
    office_name: str
    address: str | None
    contact_phone: str | None
    contact_email: str | None
    source_note: str | None
    verified_at: datetime | None


class WardRepresentativeCreate(BaseSchema):
    city: str = Field(..., min_length=1, max_length=100)
    ward_id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    role: str = Field(..., min_length=1, max_length=200)
    photo_url: str | None = Field(default=None, max_length=500)
    official_profile_url: str | None = Field(default=None, max_length=500)
    official_contact: str | None = Field(default=None, max_length=300)
    term_start: date | None = Field(default=None)
    term_end: date | None = Field(default=None)
    source: str = Field(..., min_length=1, max_length=2000)


class WardRepresentativeResponse(BaseSchema):
    id: UUID
    city: str
    ward_id: str
    name: str
    role: str
    photo_url: str | None
    official_profile_url: str | None
    official_contact: str | None
    term_start: date | None
    term_end: date | None
    source: str
    verified_at: datetime | None


class WardBoundaryCreate(BaseSchema):
    city: str = Field(..., min_length=1, max_length=100)
    ward_id: str = Field(..., min_length=1, max_length=50)
    # Ring of [longitude, latitude] pairs, first and last equal (closed
    # ring) — same convention as GeoJSON Polygon coordinates.
    ring: list[list[float]] = Field(..., min_length=4)
    source: str = Field(..., min_length=1, max_length=2000)
    effective_from: date = Field(...)
    effective_to: date | None = Field(default=None)

    @field_validator("ring")
    @classmethod
    def validate_ring(cls, v: list[list[float]]) -> list[list[float]]:
        for point in v:
            if len(point) != 2:
                raise ValueError("Each ring point must be [longitude, latitude]")
        if v[0] != v[-1]:
            raise ValueError("Ring must be closed (first point == last point)")
        return v


class WardBoundaryResponse(BaseSchema):
    id: UUID
    city: str
    ward_id: str
    source: str
    effective_from: date
    effective_to: date | None
    verified_at: datetime | None


class EscalationRunResponse(BaseSchema):
    checked: int
    newly_overdue: int
    newly_escalated: int
