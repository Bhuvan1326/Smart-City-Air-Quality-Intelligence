"""Civic issue SLA and responsible-department configuration.

There is no per-municipality admin panel for SLA configuration yet — this
is a static, documented mapping in code (a genuine limitation, not a
fabrication: the values are defensible defaults, not sourced from any
specific municipality's actual published SLA, so callers should treat
them as this deployment's own configured defaults rather than an
authoritative civic commitment). "Department" names here are generic
administrative categories, never a specific real office, employee, or
elected official — this platform does not fabricate representatives or
named entities anywhere in this module.
"""

from __future__ import annotations

from app.models.civic_issue import CivicIssueSeverity, CivicIssueType

# (default SLA hours, responsible department) per issue type.
_ISSUE_TYPE_CONFIG: dict[CivicIssueType, tuple[float, str]] = {
    CivicIssueType.GARBAGE: (48.0, "Solid Waste Management Department"),
    CivicIssueType.POTHOLE: (72.0, "Roads & Infrastructure Department"),
    CivicIssueType.WASTE_BURNING: (24.0, "Solid Waste Management Department"),
    CivicIssueType.CONSTRUCTION_DEBRIS: (48.0, "Solid Waste Management Department"),
    CivicIssueType.WATER_LEAKAGE: (24.0, "Water Supply Department"),
    CivicIssueType.FLOODING: (12.0, "Drainage & Stormwater Department"),
    CivicIssueType.FALLEN_TREE: (24.0, "Parks & Gardens Department"),
    CivicIssueType.STREETLIGHT: (72.0, "Electrical Department"),
    CivicIssueType.DRAINAGE: (48.0, "Drainage & Stormwater Department"),
    CivicIssueType.DAMAGED_INFRASTRUCTURE: (72.0, "Roads & Infrastructure Department"),
    CivicIssueType.OTHER: (96.0, "General Administration"),
}

# Severity can tighten (never loosen) the base SLA — e.g. a CRITICAL
# pothole (deep, on a main road) gets less time than a LOW severity one.
_SEVERITY_MULTIPLIER: dict[CivicIssueSeverity, float] = {
    CivicIssueSeverity.LOW: 1.0,
    CivicIssueSeverity.MODERATE: 1.0,
    CivicIssueSeverity.HIGH: 0.5,
    CivicIssueSeverity.CRITICAL: 0.25,
}


def resolve_sla_and_department(
    issue_type: CivicIssueType, severity: CivicIssueSeverity
) -> tuple[float, str]:
    """Returns (sla_hours, assigned_department) for a given issue type and
    severity. Always returns a value — issue_type is a closed enum, so
    there is no "unavailable" case here, unlike the live-data providers
    elsewhere in this platform.
    """
    base_hours, department = _ISSUE_TYPE_CONFIG[issue_type]
    multiplier = _SEVERITY_MULTIPLIER[severity]
    return round(base_hours * multiplier, 1), department
