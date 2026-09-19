import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.workers import scheduler


def test_india_discovery_and_ingestion_jobs_are_registered():
    names = {job.name for job in scheduler.JOBS}
    assert "discover-india-aqi-stations" in names
    assert "ingest-india-aqi-measurements" in names


def test_india_discovery_job_configured_to_run_immediately():

    job = next(j for j in scheduler.JOBS if j.name == "discover-india-aqi-stations")
    assert job.run_immediately is True


def test_india_ingestion_job_configured_to_run_immediately():
    job = next(j for j in scheduler.JOBS if j.name == "ingest-india-aqi-measurements")
    assert job.run_immediately is True


def test_other_interval_jobs_unchanged_default_to_not_immediate():

    unaffected = {
        "fetch-live-aqi",
        "fetch-live-aqi-pune-stations",
        "fetch-weather",
        "regenerate-forecasts",
        "run-anomaly-detection",
        "run-attribution",
        "dispatch-pending-alerts",
        "escalate-overdue-civic-issues",
    }
    for job in scheduler.JOBS:
        if job.name in unaffected:
            assert job.run_immediately is False


def test_next_run_at_for_interval_job_is_one_interval_away():
    job = scheduler.ScheduledJob("x", lambda: None, interval_seconds=100)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert job.next_run_at(now) == now + timedelta(seconds=100)


@pytest.mark.asyncio
async def test_run_job_loop_executes_immediately_when_run_immediately_true():
    """With `run_immediately=True`, the very first iteration of the job
    loop must not wait out the full interval before its first execution."""
    calls = []

    def fake_func():
        calls.append(datetime.now(UTC))

    job = scheduler.ScheduledJob(
        "immediate-job", fake_func, interval_seconds=21600, run_immediately=True
    )
    stop_event = asyncio.Event()

    async def stop_after_first_run():
        # Give the loop a moment to execute the immediate run, then stop
        # it before it would ever wait out the real 6-hour interval.
        for _ in range(50):
            if calls:
                break
            await asyncio.sleep(0.01)
        stop_event.set()

    await asyncio.wait_for(
        asyncio.gather(
            scheduler._run_job_loop(job, stop_event), stop_after_first_run()
        ),
        timeout=5,
    )

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_run_job_loop_without_run_immediately_waits_for_interval():
    """Default behavior (run_immediately=False, the pre-existing default
    for every job except the two India jobs) is unchanged: nothing runs
    before the first interval elapses."""
    calls = []

    def fake_func():
        calls.append(datetime.now(UTC))

    job = scheduler.ScheduledJob(
        "delayed-job", fake_func, interval_seconds=3600, run_immediately=False
    )
    stop_event = asyncio.Event()

    async def stop_soon():
        await asyncio.sleep(0.1)
        stop_event.set()

    await asyncio.wait_for(
        asyncio.gather(scheduler._run_job_loop(job, stop_event), stop_soon()),
        timeout=5,
    )

    assert calls == []
