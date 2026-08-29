"""Celery task: periodically check civic issues for SLA breach and
escalate. Also callable directly (see app/services/civic_escalation.py)
from a manual admin endpoint so this logic can be exercised without
Celery/Redis actually running.
"""

import asyncio

from app.core.config import settings
from app.core.logging import logger
from app.workers.celery_app import celery_app


@celery_app.task(
    name="app.workers.tasks.civic_escalation.escalate_overdue_civic_issues", bind=True
)
def escalate_overdue_civic_issues(self):
    asyncio.run(_escalate_async())


async def _escalate_async():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.services.civic_escalation import check_and_escalate_overdue_issues

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

    async with AsyncSession() as session:
        result = await check_and_escalate_overdue_issues(session)
        await session.commit()
        logger.info(
            "civic_escalation.run_complete",
            checked=result.checked,
            newly_overdue=result.newly_overdue,
            newly_escalated=result.newly_escalated,
        )

    await engine.dispose()
