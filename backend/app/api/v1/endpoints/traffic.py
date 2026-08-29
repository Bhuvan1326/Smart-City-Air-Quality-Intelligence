"""
Traffic Layer — synthetic demo overlay.

There is no live traffic-sensor integration in this deployment. Instead of
querying a third-party traffic API, this module derives a simulated traffic
signal from the same time-of-day rush-hour heuristic already used by the
forecast and ingestion pipelines (see app/workers/tasks/aqi_ingestion.py and
app/workers/tasks/forecast.py), anchored to real monitoring station
locations. Every response is explicitly marked `is_simulated: true` so the
frontend can label it as demo data (see the "Traffic (Demo)" heatmap layer
and "Demo Data — not real-time" badge it already ships with).

The AQI-vs-traffic correlation coefficient IS computed for real, with numpy,
from the paired (simulated traffic level, real observed AQI) series — only
the traffic input signal itself is synthetic.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Annotated

import numpy as np
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.schemas.base import APIResponse

router = APIRouter(prefix="/traffic", tags=["Traffic (Demo)"])


def _traffic_level_for_hour(hour: int, day_of_week: int, offset: float = 0.0) -> float:
    """Rush-hour heuristic shared with the forecast/ingestion pipelines,
    rescaled to a 0-100 congestion index."""
    if 7 <= hour <= 10 or 17 <= hour <= 20:
        base = 70.0
    elif 0 <= hour <= 5:
        base = 12.0
    else:
        base = 40.0
    if day_of_week >= 5:  # weekend
        base *= 0.75
    return max(0.0, min(100.0, base + offset))


def _congestion_category(level: float) -> str:
    if level < 20:
        return "free_flow"
    elif level < 45:
        return "light"
    elif level < 65:
        return "moderate"
    elif level < 85:
        return "heavy"
    return "gridlock"


@router.get("/current", response_model=APIResponse[list[dict]])
async def get_current_traffic(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[list[dict]]:
    """
    Simulated current traffic readings near each active monitoring station
    in the city. No live traffic feed is integrated in this deployment —
    see module docstring. Always marked is_simulated=true.
    """
    result = await session.execute(
        text(
            """
        SELECT name, latitude, longitude
        FROM monitoring_stations
        WHERE city = :city AND is_active = true AND is_deleted = false
    """
        ),
        {"city": city},
    )
    stations = [dict(row._mapping) for row in result]

    now = datetime.now(timezone.utc)
    rng = random.Random(f"{city}-{now.strftime('%Y%m%d%H')}")
    readings = []
    for s in stations:
        base = _traffic_level_for_hour(now.hour, now.weekday())
        level = max(0.0, min(100.0, base + rng.uniform(-12, 12)))
        readings.append(
            {
                "road_name": f"Near {s['name']}",
                "latitude": s["latitude"],
                "longitude": s["longitude"],
                "traffic_level": round(level, 1),
                "congestion_category": _congestion_category(level),
                "is_simulated": True,
                "timestamp": now.isoformat(),
            }
        )

    return APIResponse(data=readings)


@router.get("/correlation", response_model=APIResponse[dict])
async def get_traffic_correlation(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
    hours: int = Query(default=720, ge=1, le=8760),
) -> APIResponse[dict]:
    """
    Correlation between a simulated hourly traffic-congestion index and real
    observed AQI for the city. The traffic signal is synthetic (see module
    docstring); the correlation coefficient itself is a genuine statistic
    computed from the paired series.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await session.execute(
        text(
            """
        SELECT date_trunc('hour', r.timestamp AT TIME ZONE 'UTC') AS bucket, AVG(r.aqi) AS avg_aqi
        FROM aqi_readings r
        JOIN monitoring_stations s ON r.station_id = s.id
        WHERE s.city = :city AND r.timestamp >= :since
          AND r.is_deleted = false AND r.quality_flag != 'invalid'
        GROUP BY bucket
        ORDER BY bucket
    """
        ),
        {"city": city, "since": since},
    )
    rows = [dict(row._mapping) for row in result if row.avg_aqi is not None]

    if len(rows) < 5:
        return APIResponse(
            data={
                "city": city,
                "is_simulated": True,
                "correlation_coefficient": None,
                "strength": "insufficient_data",
                "sample_count": len(rows),
                "insight": "Not enough paired traffic and AQI data yet for this city and period.",
                "samples": [],
            }
        )

    rng = random.Random(f"{city}-correlation")
    traffic_levels: list[float] = []
    aqi_values: list[float] = []
    samples = []
    for row in rows:
        bucket_dt = row["bucket"]
        base = _traffic_level_for_hour(bucket_dt.hour, bucket_dt.weekday())
        level = max(0.0, min(100.0, base + rng.uniform(-10, 10)))
        aqi = float(row["avg_aqi"])
        traffic_levels.append(level)
        aqi_values.append(aqi)
        samples.append({"traffic_level": round(level, 1), "aqi": round(aqi, 1)})

    corr_matrix = np.corrcoef(traffic_levels, aqi_values)
    raw_coefficient = corr_matrix[0, 1]
    coefficient = float(raw_coefficient) if not np.isnan(raw_coefficient) else None

    if coefficient is None:
        strength = "insufficient_data"
    else:
        abs_r = abs(coefficient)
        if abs_r < 0.3:
            strength = "weak"
        elif abs_r < 0.6:
            strength = "moderate"
        else:
            strength = "strong"

    if coefficient is None:
        insight = "Not enough variation in the data to compute a reliable correlation."
    elif coefficient > 0.3:
        insight = (
            f"Higher simulated traffic congestion tracks with higher AQI in {city} "
            f"({strength} positive correlation)."
        )
    elif coefficient < -0.3:
        insight = (
            f"Simulated traffic congestion and AQI move in opposite directions in "
            f"{city} ({strength} negative correlation)."
        )
    else:
        insight = (
            f"Simulated traffic congestion shows little relationship with AQI in "
            f"{city} over this period."
        )

    return APIResponse(
        data={
            "city": city,
            "is_simulated": True,
            "correlation_coefficient": (
                round(coefficient, 3) if coefficient is not None else None
            ),
            "strength": strength,
            "sample_count": len(samples),
            "insight": insight,
            "samples": samples,
        }
    )
