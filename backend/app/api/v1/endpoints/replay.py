from datetime import datetime, timedelta, timezone
from typing import Annotated

from app.api.deps import CurrentUser, get_db
from app.core.redis_client import cache_get, cache_set
from app.schemas.base import APIResponse
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/replay", tags=["AQI Replay & Timeline"])

# cause_category (real, stored) -> most plausible driving pollutant. There is
# no pollutant column on anomaly_events, so this is a reasonable mapping from
# the recorded cause rather than a fabricated value.
_CAUSE_TO_POLLUTANT = {
    "vehicular": "no2",
    "industrial": "so2",
    "construction": "pm10",
    "biomass_burning": "pm25",
    "biomass": "pm25",
    "dust": "pm10",
    "stubble_burning": "pm25",
    "secondary_aerosol": "pm25",
}

_SEVERITY_ORDER = {"moderate": 0, "high": 1, "severe": 2, "critical": 3}


def _severity_from_spike(spike_value: int) -> str:
    """Severity tier aligned with the app's existing AQI category bands
    (see app.schemas.aqi.get_aqi_category)."""
    if spike_value <= 150:
        return "moderate"
    elif spike_value <= 200:
        return "high"
    elif spike_value <= 300:
        return "severe"
    return "critical"


@router.get("/aqi-history", response_model=APIResponse[list[dict]])
async def get_aqi_replay_data(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
    hours: int = Query(default=24, ge=1, le=168),
    interval_minutes: int = Query(default=30, ge=5, le=60),
) -> APIResponse[list[dict]]:
    """
    Return time-bucketed AQI data for all wards suitable for timeline replay animation.
    Each bucket contains ward-level AQI values at that timestamp.
    """
    cache_key = f"replay:{city}:{hours}:{interval_minutes}"
    cached = await cache_get(cache_key)
    if cached:
        return APIResponse(data=cached)

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await session.execute(
        text(
            """
        SELECT
            time_bucket(:interval::interval, r.timestamp) AS bucket,
            s.ward_id,
            AVG(r.aqi) AS avg_aqi,
            AVG(r.pm25) AS avg_pm25,
            MAX(r.aqi) AS max_aqi,
            COUNT(DISTINCT s.id) AS station_count
        FROM aqi_readings r
        JOIN monitoring_stations s ON r.station_id = s.id
        WHERE s.city = :city
          AND r.timestamp >= :since
          AND r.is_deleted = false
          AND r.quality_flag != 'invalid'
          AND s.ward_id IS NOT NULL
        GROUP BY bucket, s.ward_id
        ORDER BY bucket, s.ward_id
    """
        ),
        {
            "city": city,
            "since": since,
            "interval": f"{interval_minutes} minutes",
        },
    )
    rows = [dict(row._mapping) for row in result]

    # Pivot into frames: [{timestamp, wards: {W01: aqi, W02: aqi, ...}}]
    frames: dict[str, dict] = {}
    for row in rows:
        bucket_str = str(row["bucket"])
        if bucket_str not in frames:
            frames[bucket_str] = {"timestamp": bucket_str, "wards": {}}
        ward = row["ward_id"]
        frames[bucket_str]["wards"][ward] = {
            "aqi": round(float(row["avg_aqi"] or 0)),
            "pm25": round(float(row["avg_pm25"] or 0), 1),
            "max_aqi": round(float(row["max_aqi"] or 0)),
        }

    sorted_frames = sorted(frames.values(), key=lambda f: f["timestamp"])
    await cache_set(cache_key, sorted_frames, ttl=300)
    return APIResponse(data=sorted_frames)


@router.get("/root-cause-timeline/{anomaly_id}", response_model=APIResponse[dict])
async def get_root_cause_timeline(
    anomaly_id: str,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[dict]:
    """
    Return the full root cause timeline for an anomaly event,
    including step-by-step explanation of how the AQI spike developed.
    """
    result = await session.execute(
        text(
            """
        SELECT ae.id, ae.ward_id, ae.city, ae.detected_at,
               ae.aqi_spike_value, ae.baseline_aqi, ae.probable_cause,
               ae.cause_category, ae.confidence_score, ae.is_resolved,
               ae.root_cause_timeline, ae.contributing_sources,
               s.name AS station_name, s.latitude, s.longitude
        FROM anomaly_events ae
        JOIN monitoring_stations s ON ae.station_id = s.id
        WHERE ae.id = :id AND ae.is_deleted = false
    """
        ),
        {"id": anomaly_id},
    )
    row = result.one_or_none()
    if not row:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Anomaly not found"
        )

    data = dict(row._mapping)

    # Enrich with hourly AQI leading up to the spike
    detected_at = data["detected_at"]
    lead_up = await session.execute(
        text(
            """
        SELECT time_bucket('30 minutes', r.timestamp) AS bucket,
               AVG(r.aqi) AS avg_aqi, AVG(r.pm25) AS avg_pm25,
               AVG(r.wind_speed) AS wind_speed
        FROM aqi_readings r
        JOIN monitoring_stations s ON r.station_id = s.id
        WHERE s.ward_id = :ward AND s.city = :city
          AND r.timestamp BETWEEN :start AND :end
          AND r.is_deleted = false
        GROUP BY bucket ORDER BY bucket
    """
        ),
        {
            "ward": data["ward_id"],
            "city": data["city"],
            "start": (
                detected_at - timedelta(hours=6)
                if detected_at
                else datetime.now(timezone.utc) - timedelta(hours=6)
            ),
            "end": detected_at or datetime.now(timezone.utc),
        },
    )
    lead_up_data = [dict(r._mapping) for r in lead_up]

    # Attribution at time of spike
    attr = await session.execute(
        text(
            """
        SELECT vehicular_pct, industrial_pct, construction_pct, biomass_pct,
               overall_confidence
        FROM pollution_attributions
        WHERE ward_id = :ward AND city = :city
          AND timestamp <= :ts
        ORDER BY timestamp DESC LIMIT 1
    """
        ),
        {
            "ward": data["ward_id"],
            "city": data["city"],
            "ts": data["detected_at"] or datetime.now(timezone.utc),
        },
    )
    attr_row = attr.one_or_none()

    return APIResponse(
        data={
            "anomaly": {
                "id": str(data["id"]),
                "ward_id": data["ward_id"],
                "station": data["station_name"],
                "detected_at": str(data["detected_at"]),
                "aqi_spike": data["aqi_spike_value"],
                "baseline_aqi": data["baseline_aqi"],
                "cause": data["probable_cause"],
                "category": data["cause_category"],
                "confidence": data["confidence_score"],
                "is_resolved": data["is_resolved"],
                "location": {
                    "latitude": data["latitude"],
                    "longitude": data["longitude"],
                },
            },
            "root_cause_timeline": data.get("root_cause_timeline") or {},
            "contributing_sources": data.get("contributing_sources") or {},
            "lead_up_readings": [
                {
                    "timestamp": str(r["bucket"]),
                    "aqi": round(float(r["avg_aqi"] or 0)),
                    "pm25": round(float(r["avg_pm25"] or 0), 1),
                    "wind_speed": round(float(r["wind_speed"] or 0), 1),
                }
                for r in lead_up_data
            ],
            "attribution_at_spike": dict(attr_row._mapping) if attr_row else None,
        }
    )


@router.get("/anomalies", response_model=APIResponse[list[dict]])
async def list_anomalies(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
    resolved: bool | None = Query(default=None),
    hours: int = Query(default=48),
    min_severity: str | None = Query(
        default=None,
        description="Minimum severity tier: moderate, high, severe, critical",
    ),
    pollutant: str | None = Query(default=None),
) -> APIResponse[list[dict]]:
    """
    List all anomaly events for a city, optionally filtered by resolved
    status, minimum severity, and dominant pollutant. Also includes station
    coordinates and a few derived map-display fields (severity, pollutant,
    anomaly_score, detection_method) on top of the stored event data.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    where_resolved = ""
    if resolved is not None:
        where_resolved = f"AND ae.is_resolved = {'true' if resolved else 'false'}"

    result = await session.execute(
        text(
            f"""
        SELECT ae.id, ae.ward_id, ae.city, ae.detected_at, ae.aqi_spike_value,
               ae.baseline_aqi, ae.probable_cause, ae.cause_category,
               ae.confidence_score, ae.is_resolved, ae.resolved_at,
               s.name AS station_name, s.latitude, s.longitude
        FROM anomaly_events ae
        JOIN monitoring_stations s ON ae.station_id = s.id
        WHERE ae.city = :city AND ae.detected_at >= :since AND ae.is_deleted = false
          {where_resolved}
        ORDER BY ae.detected_at DESC
        LIMIT 50
    """
        ),
        {"city": city, "since": since},
    )

    events = []
    for row in result:
        r = dict(row._mapping)
        severity = _severity_from_spike(r["aqi_spike_value"] or 0)
        event_pollutant = _CAUSE_TO_POLLUTANT.get(
            (r["cause_category"] or "").lower(), "pm25"
        )

        if min_severity and _SEVERITY_ORDER.get(severity, 0) < _SEVERITY_ORDER.get(
            min_severity, 0
        ):
            continue
        if pollutant and event_pollutant != pollutant:
            continue

        events.append(
            {
                **r,
                "severity": severity,
                "pollutant": event_pollutant,
                "observed_value": r["aqi_spike_value"],
                "expected_value": r["baseline_aqi"],
                "anomaly_score": r["confidence_score"],
                "detection_method": "statistical_zscore",
            }
        )

    return APIResponse(data=events)
