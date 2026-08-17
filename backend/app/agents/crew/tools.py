"""
CrewAI tools for the Investigation Crew.

CrewAI tool functions execute synchronously (crewai/litellm's own executor
calls them directly, not via an event loop we control), while every data
access in this codebase is async SQLAlchemy. Rather than trying to share
the calling agent's AsyncSession across that sync/async boundary — which
risks concurrent use of one connection from two different execution
contexts — each tool opens its own short-lived engine and event loop via
`asyncio.run`, exactly the same pattern already used by every Celery task
in this codebase (see app/workers/tasks/*.py) for the same reason.
"""

from __future__ import annotations

import asyncio

from crewai.tools import tool

from app.core.config import settings


def _run_query_sync(sql: str, params: dict) -> list[dict]:
    async def _inner():
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
        async with AsyncSession() as session:
            result = await session.execute(text(sql), params)
            rows = [dict(row._mapping) for row in result]
        await engine.dispose()
        return rows

    return asyncio.run(_inner())


@tool("Get satellite evidence for a ward")
def get_satellite_evidence(ward_id: str, city: str) -> str:
    """
    Returns the most recent satellite-derived observation (NDVI/NDBI,
    thermal hotspots) for a ward — see app.services.satellite. Used by the
    investigator to check whether an independent, non-ground-based source
    corroborates a suspected pollution source category.
    """
    rows = _run_query_sync(
        """
        SELECT observed_at, mean_ndvi, mean_ndbi, vegetation_loss_detected,
               construction_activity_detected, thermal_hotspot_count,
               biomass_burning_hotspots, industrial_thermal_hotspots, confidence, notes
        FROM satellite_observations
        WHERE ward_id = :ward AND city = :city AND is_deleted = false
        ORDER BY observed_at DESC LIMIT 1
        """,
        {"ward": ward_id, "city": city},
    )
    if not rows:
        return f"No satellite observation available for ward {ward_id}."
    return str(rows[0])


@tool("Get recent citizen complaints for a ward")
def get_citizen_alert_history(ward_id: str, city: str) -> str:
    """
    Returns recent citizen alerts issued for a ward. Repeated recent alerts
    at high risk levels are independent (crowd-facing) corroboration that a
    ward's air quality problem is real and ongoing, not a sensor artifact.
    """
    rows = _run_query_sync(
        """
        SELECT sent_at, risk_level, aqi_value, channel, delivery_status
        FROM citizen_alerts
        WHERE ward_id = :ward AND city = :city AND is_deleted = false
        ORDER BY sent_at DESC LIMIT 5
        """,
        {"ward": ward_id, "city": city},
    )
    if not rows:
        return f"No recent citizen alerts recorded for ward {ward_id}."
    return str(rows)


@tool("Get enforcement history for a ward")
def get_enforcement_history(ward_id: str, city: str) -> str:
    """
    Returns recent enforcement actions for a ward — prior violations at the
    same location strengthen the case that a recurring source (not a
    one-off event) is responsible for a new attribution finding.
    """
    rows = _run_query_sync(
        """
        SELECT created_at, action_type, status, priority_score, outcome_score
        FROM enforcement_actions
        WHERE ward_id = :ward AND city = :city AND is_deleted = false
        ORDER BY created_at DESC LIMIT 5
        """,
        {"ward": ward_id, "city": city},
    )
    if not rows:
        return f"No enforcement history recorded for ward {ward_id}."
    return str(rows)


@tool("Get monitoring sensor health for a ward")
def get_sensor_health(ward_id: str, city: str) -> str:
    """
    Returns the latest predictive-maintenance assessment (see
    app.ml.sensor_maintenance) for stations in a ward — a low-confidence
    attribution finding paired with a flagged/failing sensor is better
    explained by instrument fault than a genuine pollution event.
    """
    rows = _run_query_sync(
        """
        SELECT s.name, h.maintenance_priority, h.failure_probability, h.flatlined, h.drift_score
        FROM monitoring_stations s
        JOIN sensor_health_assessments h ON h.station_id = s.id
        WHERE s.ward_id = :ward AND s.city = :city AND s.is_deleted = false
        ORDER BY h.assessed_at DESC LIMIT 5
        """,
        {"ward": ward_id, "city": city},
    )
    if not rows:
        return f"No sensor health assessments available for ward {ward_id}."
    return str(rows)
