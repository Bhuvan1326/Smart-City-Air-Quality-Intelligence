"""Celery application instance.

`app/workers/tasks/aqi_ingestion.py` decorates its ingestion functions
with `@celery_app.task(...)` so that they:

  - carry a stable, explicit task `name` (useful for logging/metrics),
  - accept `bind=True`/`max_retries` for the standard Celery retry API,
  - stay import-compatible with the existing test suite, which calls
    these functions both as plain callables (`fetch_live_aqi_all_cities()`)
    and via the Celery Task API (`fetch_live_aqi_pune_stations.run()`).

This project does NOT run a separate Celery worker/beat process (see
docker-compose.yml and backend/Dockerfile — only `uvicorn app.main:app`
is started). All scheduling is handled in-process by the custom asyncio
scheduler in `app/workers/scheduler.py`, which calls these task objects
directly (never `.delay()`/`.apply_async()`). Because of that, this app
is intentionally never started as a worker and never needs to actually
connect to a broker at runtime — it only needs to exist so the
`@celery_app.task` decorator can produce valid, callable Task objects.

The broker/backend URL reuses `settings.REDIS_URL`, the same Redis
instance already used elsewhere in this project (see
`app/core/redis_client.py`), rather than introducing a new service.
"""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "airquality",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # No worker process consumes this queue today (see module docstring),
    # so keep Celery from trying to eagerly connect to the broker just
    # because the app object was imported/instantiated.
    broker_connection_retry_on_startup=False,
)
