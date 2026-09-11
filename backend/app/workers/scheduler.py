import asyncio
from datetime import UTC, datetime, timedelta

import pytz

from app.core.config import settings
from app.core.logging import logger
from app.core.redis_client import get_redis
from app.workers.tasks import (
    anomaly_detection,
    aqi_ingestion,
    attribution,
    civic_escalation,
    drone,
    forecast,
    notifications,
    satellite,
)

IST = pytz.timezone("Asia/Kolkata")
LOCK_PREFIX = "lock:scheduler:"
LOCK_TTL_SECONDS = 1800


class ScheduledJob:
    def __init__(
        self,
        name,
        func,
        interval_seconds=None,
        crontab_hours=None,
        crontab_minute=None,
    ):
        self.name = name
        self.func = func
        self.interval_seconds = interval_seconds
        self.crontab_hours = crontab_hours
        self.crontab_minute = crontab_minute

    def next_run_at(self, now_utc):
        if self.interval_seconds is not None:
            return now_utc + timedelta(seconds=self.interval_seconds)
        now_ist = now_utc.astimezone(IST)
        candidates = []
        for hour in self.crontab_hours:
            candidate = now_ist.replace(
                hour=hour, minute=self.crontab_minute, second=0, microsecond=0
            )
            if candidate <= now_ist:
                candidate += timedelta(days=1)
            candidates.append(candidate)
        return min(candidates).astimezone(UTC)

    def run_marker(self, run_at):
        if self.interval_seconds is not None:
            bucket = int(run_at.timestamp() // self.interval_seconds)
            return str(bucket)
        return run_at.strftime("%Y%m%dT%H%M")


JOBS = [
    ScheduledJob(
        "fetch-live-aqi", aqi_ingestion.fetch_live_aqi_all_cities, interval_seconds=600
    ),
    ScheduledJob(
        "fetch-live-aqi-pune-stations",
        aqi_ingestion.fetch_live_aqi_pune_stations,
        interval_seconds=60,
    ),
    ScheduledJob(
        "discover-india-aqi-stations",
        aqi_ingestion.discover_and_ingest_india_locations,
        interval_seconds=settings.OPENAQ_INDIA_DISCOVERY_INTERVAL_SECONDS,
    ),
    ScheduledJob(
        "ingest-india-aqi-measurements",
        aqi_ingestion.ingest_india_latest_measurements,
        interval_seconds=settings.OPENAQ_INDIA_INGEST_INTERVAL_SECONDS,
    ),
    ScheduledJob(
        "fetch-weather", aqi_ingestion.fetch_weather_data, interval_seconds=900
    ),
    ScheduledJob(
        "regenerate-forecasts",
        forecast.regenerate_ward_forecasts,
        interval_seconds=1800,
    ),
    ScheduledJob(
        "run-anomaly-detection",
        anomaly_detection.detect_anomalies,
        interval_seconds=250,
    ),
    ScheduledJob(
        "run-attribution", attribution.compute_attribution, interval_seconds=1800
    ),
    ScheduledJob(
        "midnight-retraining",
        forecast.trigger_model_retraining,
        crontab_hours=[0],
        crontab_minute=30,
    ),
    ScheduledJob(
        "maintenance-prediction",
        anomaly_detection.predict_sensor_maintenance,
        crontab_hours=[6],
        crontab_minute=0,
    ),
    ScheduledJob(
        "fetch-satellite-features",
        satellite.fetch_satellite_features,
        crontab_hours=[0, 6, 12, 18],
        crontab_minute=15,
    ),
    ScheduledJob(
        "dispatch-pending-alerts",
        notifications.dispatch_pending_alerts,
        interval_seconds=60,
    ),
    ScheduledJob(
        "escalate-overdue-civic-issues",
        civic_escalation.escalate_overdue_civic_issues,
        interval_seconds=900,
    ),
    ScheduledJob(
        "detect-drone-hotspots",
        drone.detect_hotspots_and_plan,
        crontab_hours=[7],
        crontab_minute=0,
    ),
]

_tasks: list[asyncio.Task] = []
_stop_event: asyncio.Event | None = None


async def _acquire_lock(key):
    try:
        redis = await get_redis()
        return bool(await redis.set(key, "1", nx=True, ex=LOCK_TTL_SECONDS))
    except Exception as e:
        logger.warning("scheduler.lock_error", key=key, error=str(e))
        return True


async def _execute_job(job, run_at):
    lock_key = f"{LOCK_PREFIX}{job.name}:{job.run_marker(run_at)}"
    if not await _acquire_lock(lock_key):
        logger.info("scheduler.job_skipped_locked", job=job.name)
        return
    loop = asyncio.get_running_loop()
    logger.info("scheduler.job_start", job=job.name)
    try:
        await loop.run_in_executor(None, job.func)
        logger.info("scheduler.job_complete", job=job.name)
    except Exception as e:
        logger.error("scheduler.job_failed", job=job.name, error=str(e), exc_info=e)


async def _run_job_loop(job, stop_event):
    while not stop_event.is_set():
        now = datetime.now(UTC)
        target = job.next_run_at(now)
        delay = max((target - now).total_seconds(), 0)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
            break
        except TimeoutError:
            pass
        await _execute_job(job, target)


async def start_scheduler():
    global _stop_event, _tasks
    if _stop_event is not None:
        return
    _stop_event = asyncio.Event()
    _tasks = [
        asyncio.create_task(
            _run_job_loop(job, _stop_event), name=f"scheduler:{job.name}"
        )
        for job in JOBS
    ]
    logger.info("scheduler.started", job_count=len(_tasks))


async def stop_scheduler():
    global _stop_event, _tasks
    if _stop_event is None:
        return
    _stop_event.set()
    await asyncio.gather(*_tasks, return_exceptions=True)
    _tasks = []
    _stop_event = None
    logger.info("scheduler.stopped")
