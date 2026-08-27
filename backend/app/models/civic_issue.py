"""Civic Issue Intelligence — citizen-reported issues (garbage, potholes,
waste burning, etc.), AI-assisted photo classification, GIS ward
assignment, SLA tracking, a status audit trail, resolution proof, AI
before/after verification, citizen confirmation, and duplicate-report
clustering.

See:
- app/services/civic_photo_classifier.py — the initial AI classification
  call (real Claude vision, never fabricated; citizen always confirms or
  overrides).
- app/services/civic_ward_assignment.py — real PostGIS point-in-polygon
  ward assignment where a WardBoundary polygon is on file, falling back
  to an approximate nearest-centroid method, then to "unavailable" — a
  boundary is never fabricated.
- app/services/civic_governance.py — municipality/ward-office/department/
  representative lookups, and the distinction between "responsible civic
  authority" and "elected ward representative".
- app/services/civic_sla.py — the static, documented SLA/department
  mapping.
- app/services/civic_resolution_verification.py — the real Claude-vision
  before/after comparison (LIKELY_RESOLVED / NEEDS_REVIEW /
  INSUFFICIENT_EVIDENCE, never absolute certainty).
- app/services/civic_duplicate_detection.py — geospatial + type + time-
  window clustering of likely-duplicate reports (see CivicIssueCluster).
- app/services/civic_escalation.py — SLA-breach detection and escalation.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID as UUIDType

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
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
    VERIFICATION_PENDING = "verification_pending"
    VERIFIED = "verified"
    REOPENED = "reopened"
    ESCALATED = "escalated"
    OVERDUE = "overdue"
    CLOSED = "closed"


class WardAssignmentMethod(str, Enum):
    # Real PostGIS ST_Contains against an admin-entered
    # app.models.civic_governance.WardBoundary polygon.
    POINT_IN_POLYGON = "point_in_polygon"
    # Falls back to app.gis.operations.GISService.point_in_ward
    # (nearest-ward-centroid distance) when no polygon covers the point.
    NEAREST_WARD_CENTROID_APPROXIMATE = "nearest_ward_centroid_approximate"
    UNAVAILABLE = "unavailable"


class ClassificationSource(str, Enum):
    CITIZEN_REPORTED = "citizen_reported"  # no photo, or AI unavailable
    AI_SUGGESTED_CITIZEN_CONFIRMED = "ai_suggested_citizen_confirmed"
    AI_SUGGESTED_CITIZEN_OVERRIDDEN = "ai_suggested_citizen_overridden"


class AIVerificationResult(str, Enum):
    LIKELY_RESOLVED = "likely_resolved"
    NEEDS_REVIEW = "needs_review"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class CivicIssueCluster(BaseModel):
    """A group of likely-duplicate reports of the same physical issue —
    same issue_type, within a proximity radius and time window of each
    other (see app/services/civic_duplicate_detection.py). Report_count
    is denormalized for cheap listing; the authoritative count is always
    len(issues).
    """

    __tablename__ = "civic_issue_clusters"

    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ward_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    issue_type: Mapped[str] = mapped_column(String(40), nullable=False)
    centroid_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    centroid_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    report_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    issues: Mapped[list["CivicIssue"]] = relationship(
        "CivicIssue", back_populates="cluster"
    )


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

    # --- Resolution proof (see app/api/v1/endpoints/civic.py POST /resolve) ---
    resolution_photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_order_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # --- AI before/after verification — never absolute certainty ---
    ai_verification_result: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    ai_verification_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    ai_verification_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Citizen confirmation ---
    citizen_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    citizen_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    citizen_verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reopen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- Duplicate/recurring clustering ---
    cluster_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("civic_issue_clusters.id"), nullable=True
    )
    is_duplicate_of_cluster: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="True if this report was matched to an existing cluster rather than being the first report of it.",
    )

    reporter: Mapped["User"] = relationship("User", foreign_keys=[reporter_id])
    resolved_by: Mapped["User | None"] = relationship(
        "User", foreign_keys=[resolved_by_id]
    )
    cluster: Mapped["CivicIssueCluster | None"] = relationship(
        "CivicIssueCluster", back_populates="issues"
    )
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
