"""Civic Issue Intelligence — citizen-reported issues (garbage, potholes,
waste burning, etc.), AI-assisted photo classification, GIS ward
assignment, SLA tracking, and a status audit trail.

SCOPE OF THIS PHASE (deliberately not a placeholder for the rest): this
model supports submission through to authority status tracking. It does
NOT yet support resolution-proof photos, AI before/after verification,
citizen confirm-resolved loops, duplicate/recurring-issue clustering, or
elected-representative mapping — those are separate, larger phases and
are not represented here to avoid claiming functionality that doesn't
exist yet.

See:
- app/services/civic_photo_classifier.py — the AI classification call
  (real Claude vision, never a fabricated result; citizen always confirms
  or overrides the suggestion).
- app/services/civic_ward_assignment.py — GIS ward lookup with an honest
  distinction between real point-in-polygon assignment (where boundary
  polygons exist) and an approximate nearest-station fallback.
- app/services/civic_sla.py — the static, documented SLA/department
  mapping (not a per-municipality admin panel yet).
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID as UUIDType

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class CivicIssueType(str, Enum):
    GARBAGE = "garbage"
    POTHOLE = "pothole"
    WASTE_BURNING = "waste_burning"
    CONSTRUCTION_DEBRIS = "construction_debris"
    WATER_LEAKAGE = "water_leakage"
    FLOODING = "flooding"
    FALLEN_TREE = "fallen_tree"
    STREETLIGHT = "streetlight"
    DRAINAGE = "drainage"
    DAMAGED_INFRASTRUCTURE = "damaged_infrastructure"
    OTHER = "other"


class CivicIssueSeverity(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class CivicIssueStatus(str, Enum):
    SUBMITTED = "submitted"
    TRIAGED = "triaged"
    ASSIGNED = "assigned"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    OVERDUE = "overdue"
    CLOSED = "closed"
    # VERIFICATION_PENDING, VERIFIED, and REOPENED are intentionally not
    # included yet — that loop (resolution proof -> AI verification ->
    # citizen confirmation) is not implemented in this phase.


class WardAssignmentMethod(str, Enum):
    # Reuses app.gis.operations.GISService.point_in_ward, which is
    # nearest-ward-centroid distance, not true polygon containment (no
    # PostGIS point-in-polygon query is actually implemented anywhere in
    # this codebase yet) — labeled accordingly rather than claiming a
    # precision this platform doesn't have.
    NEAREST_WARD_CENTROID_APPROXIMATE = "nearest_ward_centroid_approximate"
    UNAVAILABLE = "unavailable"


class ClassificationSource(str, Enum):
    CITIZEN_REPORTED = "citizen_reported"  # no photo, or AI unavailable
    AI_SUGGESTED_CITIZEN_CONFIRMED = "ai_suggested_citizen_confirmed"
    AI_SUGGESTED_CITIZEN_OVERRIDDEN = "ai_suggested_citizen_overridden"


class CivicIssue(BaseModel):
    __tablename__ = "civic_issues"

    reporter_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ward_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    ward_assignment_method: Mapped[str] = mapped_column(
        String(30), nullable=False, default=WardAssignmentMethod.UNAVAILABLE
    )

    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geometry: Mapped[Geometry | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )

    issue_type: Mapped[str] = mapped_column(String(40), nullable=False)
    classification_source: Mapped[str] = mapped_column(
        String(40), nullable=False, default=ClassificationSource.CITIZEN_REPORTED
    )
    ai_suggested_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_suggested_severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ai_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CivicIssueSeverity.MODERATE
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=CivicIssueStatus.SUBMITTED, index=True
    )
    assigned_department: Mapped[str | None] = mapped_column(String(150), nullable=True)
    sla_hours: Mapped[float] = mapped_column(Float, nullable=False)
    sla_deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_overdue: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    reporter: Mapped["User"] = relationship("User", foreign_keys=[reporter_id])
    status_events: Mapped[list["CivicIssueStatusEvent"]] = relationship(
        "CivicIssueStatusEvent",
        back_populates="issue",
        order_by="CivicIssueStatusEvent.created_at",
    )


class CivicIssueStatusEvent(BaseModel):
    __tablename__ = "civic_issue_status_events"

    issue_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("civic_issues.id"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_by_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    issue: Mapped["CivicIssue"] = relationship(
        "CivicIssue", back_populates="status_events"
    )
    changed_by: Mapped["User | None"] = relationship(
        "User", foreign_keys=[changed_by_id]
    )
