"""
Celery task: dispatch every CitizenAlert still sitting in delivery_status
"pending" through the NotificationDispatcher (Firebase push / free SMTP
email by default; Twilio SMS/IVR only if explicitly enabled and funded).
"""

import asyncio

from app.core.config import settings
from app.core.logging import logger
from app.workers.celery_app import celery_app


@celery_app.task(
    name="app.workers.tasks.notifications.dispatch_pending_alerts", bind=True
)
def dispatch_pending_alerts(self):
    asyncio.run(_dispatch_async())


async def _dispatch_async():
    if not settings.NOTIFICATIONS_ENABLED:
        logger.info("notifications.disabled")
        return

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.enforcement import CitizenAlert
    from app.services.notifications.dispatcher import NotificationDispatcher

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

    async with AsyncSession() as session:
        result = await session.execute(
            select(CitizenAlert)
            .where(
                CitizenAlert.delivery_status == "pending",
                CitizenAlert.is_deleted == False,  # noqa: E712
            )
            .limit(200)
        )
        pending = list(result.scalars().all())
        if not pending:
            return

        dispatcher = NotificationDispatcher(session)
        outcomes = []
        for alert in pending:
            outcome = await dispatcher.dispatch_alert(alert)
            outcomes.append(outcome)

        await session.commit()
        logger.info(
            "notifications.batch_complete",
            processed=len(outcomes),
            delivered=sum(o.delivered for o in outcomes),
            failed=sum(o.failed for o in outcomes),
            skipped_no_config=sum(o.skipped_no_config for o in outcomes),
        )

    await engine.dispose()
