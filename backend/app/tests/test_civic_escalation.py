"""Unit tests for civic_escalation, using a fake in-memory session."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.civic_issue import CivicIssue, CivicIssueStatus
from app.services.civic_escalation import check_and_escalate_overdue_issues


def _issue(status: str, sla_deadline: datetime, is_overdue: bool = False) -> CivicIssue:
    issue = CivicIssue(
        id=uuid4(),
        reporter_id=uuid4(),
        city="Pune",
        ward_id="W01",
        ward_assignment_method="unavailable",
        latitude=18.5,
        longitude=73.8,
        issue_type="pothole",
        classification_source="citizen_reported",
        severity="moderate",
        status=status,
        sla_hours=72.0,
        sla_deadline=sla_deadline,
        is_overdue=is_overdue,
    )
    return issue


def _session_with(issues: list[CivicIssue]) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = issues
    session.execute = AsyncMock(return_value=result)
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.mark.asyncio
async def test_overdue_in_progress_issue_gets_escalated():
    now = datetime.now(UTC)
    issue = _issue(CivicIssueStatus.IN_PROGRESS.value, now - timedelta(hours=1))
    session = _session_with([issue])

    result = await check_and_escalate_overdue_issues(session, city="Pune")

    assert result.checked == 1
    assert result.newly_overdue == 1
    assert result.newly_escalated == 1
    assert issue.is_overdue is True
    assert issue.status == CivicIssueStatus.ESCALATED.value


@pytest.mark.asyncio
async def test_already_escalated_issue_not_double_counted():
    now = datetime.now(UTC)
    issue = _issue(
        CivicIssueStatus.ESCALATED.value, now - timedelta(hours=1), is_overdue=True
    )
    session = _session_with([issue])

    result = await check_and_escalate_overdue_issues(session, city="Pune")

    assert result.newly_overdue == 0
    assert result.newly_escalated == 0


@pytest.mark.asyncio
async def test_no_overdue_issues_reports_zero():
    session = _session_with([])
    result = await check_and_escalate_overdue_issues(session, city="Pune")
    assert result.checked == 0
    assert result.newly_overdue == 0
    assert result.newly_escalated == 0
