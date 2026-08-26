from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.core.sanitization import sanitize_text
from app.schemas.base import BaseSchema


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


class CivicIssueStatusEventResponse(BaseSchema):
    id: UUID
    from_status: str | None
    to_status: str
    changed_by_id: UUID | None
    note: str | None
    created_at: datetime


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


class CivicIssueListItem(BaseSchema):
    """Lighter-weight shape for list views (no status_events)."""

    id: UUID
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
