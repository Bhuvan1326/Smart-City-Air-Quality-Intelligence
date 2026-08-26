from app.models.civic_issue import CivicIssueSeverity, CivicIssueType
from app.services.civic_sla import resolve_sla_and_department


def test_every_issue_type_has_a_department_and_sla():
    for issue_type in CivicIssueType:
        hours, department = resolve_sla_and_department(
            issue_type, CivicIssueSeverity.MODERATE
        )
        assert hours > 0
        assert department


def test_critical_severity_tightens_sla_relative_to_moderate():
    moderate_hours, _ = resolve_sla_and_department(
        CivicIssueType.POTHOLE, CivicIssueSeverity.MODERATE
    )
    critical_hours, _ = resolve_sla_and_department(
        CivicIssueType.POTHOLE, CivicIssueSeverity.CRITICAL
    )
    assert critical_hours < moderate_hours


def test_low_and_moderate_severity_share_base_sla():
    low_hours, _ = resolve_sla_and_department(
        CivicIssueType.GARBAGE, CivicIssueSeverity.LOW
    )
    moderate_hours, _ = resolve_sla_and_department(
        CivicIssueType.GARBAGE, CivicIssueSeverity.MODERATE
    )
    assert low_hours == moderate_hours


def test_department_is_never_a_named_individual():
    # Sanity check the anti-fabrication rule: departments are generic
    # administrative categories, not people's names.
    for issue_type in CivicIssueType:
        _, department = resolve_sla_and_department(
            issue_type, CivicIssueSeverity.MODERATE
        )
        assert "Department" in department or "Administration" in department
