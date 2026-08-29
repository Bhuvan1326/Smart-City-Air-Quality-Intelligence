"""SLA breach detection and escalation for civic issues.

A dedicated function (not just a cron-only script) so it can be called
both from a Celery periodic task (app/workers/tasks/civic_escalation.py)
and from a manual admin-triggered endpoint — useful when Celery/Redis
isn't running (e.g. this sandbox), so escalation can still be exercised
and tested without depending on infrastructure that may be unavailable.

Terminal statuses (RESOLVED, VERIFICATION_PENDING, VERIFIED, CLOSED) are
never escalated — an issue already being worked through the resolution
loop shouldn't be flagged overdue just because its SLA clock ran out
mid-verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.models.civic_issue import (CivicIssue, CivicIssueStatus,
                                    CivicIssueStatusEvent)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_NON_ESCALATABLE_STATUSES = {
    CivicIssueStatus.RESOLVED.value,
    CivicIssueStatus.VERIFICATION_PENDING.value,
    CivicIssueStatus.VERIFIED.value,
    CivicIssueStatus.CLOSED.value,
    CivicIssueStatus.ESCALATED.value,  # already escalated
}


@dataclass
class EscalationRunResult:
    checked: int
    newly_overdue: int
    newly_escalated: int


async def check_and_escalate_overdue_issues(
    session: AsyncSession, *, city: str | None = None
) -> EscalationRunResult:
    now = datetime.now(UTC)
    stmt = select(CivicIssue).where(
        CivicIssue.is_deleted.is_(False),
        CivicIssue.sla_deadline < now,
        CivicIssue.status.not_in(_NON_ESCALATABLE_STATUSES),
    )
    if city:
        stmt = stmt.where(CivicIssue.city == city)

    result = await session.execute(stmt)
    overdue_issues = result.scalars().all()

    newly_overdue = 0
    newly_escalated = 0
    for issue in overdue_issues:
        if not issue.is_overdue:
            issue.is_overdue = True
            newly_overdue += 1

        if issue.status != CivicIssueStatus.ESCALATED.value:
            previous_status = issue.status
            issue.status = CivicIssueStatus.ESCALATED.value
            session.add(
                CivicIssueStatusEvent(
                    issue_id=issue.id,
                    from_status=previous_status,
                    to_status=CivicIssueStatus.ESCALATED.value,
                    changed_by_id=None,
                    note=(
                        "This complaint is overdue under the published SLA "
                        f"({issue.sla_hours:.0f}h) and has been automatically escalated."
                    ),
                )
            )
            newly_escalated += 1

    await session.flush()
    return EscalationRunResult(
        checked=len(overdue_issues),
        newly_overdue=newly_overdue,
        newly_escalated=newly_escalated,
    )
