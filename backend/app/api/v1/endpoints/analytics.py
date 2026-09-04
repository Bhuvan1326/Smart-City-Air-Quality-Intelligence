from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, RequireAnalyst, get_db
from app.core.redis_client import cache_get, cache_set
from app.gis.operations import GISService
from app.models.analytics import AnomalyEvent, PolicySnapshot
from app.models.enforcement import EnforcementAction, InterventionOutcome
from app.schemas.base import APIResponse

router = APIRouter(
    prefix="/analytics", tags=["Analytics"], dependencies=[RequireAnalyst]
)


async def _fetch_daily_trend_from_raw_readings(
    session: AsyncSession, city: str, since: datetime
) -> list[dict]:
    """Compute the same (day, avg_aqi, max_aqi, min_aqi) shape directly
    from raw aqi_readings, bypassing the aqi_daily_by_station continuous
    aggregate entirely.
    """
    result = await session.execute(
        text("""
        SELECT
            date_trunc('day', r.timestamp)::date AS day,
            AVG(r.aqi) AS avg_aqi,
            MAX(r.aqi) AS max_aqi,
            MIN(r.aqi) AS min_aqi
        FROM aqi_readings r
        JOIN monitoring_stations s ON r.station_id = s.id
        WHERE s.city = :city AND r.timestamp >= :since
          AND r.is_deleted = false AND r.quality_flag != 'invalid'
        GROUP BY date_trunc('day', r.timestamp)
        ORDER BY day
    """),
        {"city": city, "since": since},
    )
    return [dict(row._mapping) for row in result]


@router.get("", response_model=APIResponse[dict])
async def get_city_analytics(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
    days: int = Query(default=30, ge=1, le=365),
) -> APIResponse[dict]:
    cache_key = f"analytics:{city}:{days}"
    cached = await cache_get(cache_key)
    if cached:
        return APIResponse(data=cached)

    since = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        aqi_trend = await session.execute(
            text("""
            SELECT
                agg.day AS day,
                AVG(agg.avg_aqi) AS avg_aqi,
                MAX(agg.max_aqi) AS max_aqi,
                MIN(agg.min_aqi) AS min_aqi
            FROM aqi_daily_by_station agg
            JOIN monitoring_stations s ON agg.station_id = s.id
            WHERE s.city = :city AND agg.day >= :since
            GROUP BY agg.day
            ORDER BY agg.day
        """),
            {"city": city, "since": since},
        )
        trend_data = [dict(row._mapping) for row in aqi_trend]
    except (ProgrammingError, DBAPIError):
        await session.rollback()
        trend_data = []

    if not trend_data:
        trend_data = await _fetch_daily_trend_from_raw_readings(session, city, since)

    p95_window = min(days, 7)
    p95_since = datetime.now(timezone.utc) - timedelta(days=p95_window)
    p95_result = await session.execute(
        text("""
        SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY r.aqi) AS p95_aqi
        FROM aqi_readings r
        JOIN monitoring_stations s ON r.station_id = s.id
        WHERE s.city = :city AND r.timestamp >= :since
          AND r.is_deleted = false AND r.quality_flag != 'invalid'
    """),
        {"city": city, "since": p95_since},
    )
    p95_row = p95_result.first()
    recent_p95_aqi = (
        float(p95_row.p95_aqi) if p95_row and p95_row.p95_aqi is not None else None
    )

    # Enforcement actions summary
    enforcement_stats = await session.execute(
        select(
            EnforcementAction.action_type,
            EnforcementAction.status,
            func.count(EnforcementAction.id).label("count"),
        )
        .where(
            EnforcementAction.city == city,
            EnforcementAction.created_at >= since,
            EnforcementAction.is_deleted.is_(False),
        )
        .group_by(EnforcementAction.action_type, EnforcementAction.status)
    )
    enforcement_data = [dict(row._mapping) for row in enforcement_stats]

    # Anomaly events
    anomaly_result = await session.execute(
        select(
            AnomalyEvent.cause_category,
            func.count(AnomalyEvent.id).label("count"),
            func.avg(AnomalyEvent.aqi_spike_value).label("avg_spike"),
        )
        .where(
            AnomalyEvent.city == city,
            AnomalyEvent.detected_at >= since,
            AnomalyEvent.is_deleted.is_(False),
        )
        .group_by(AnomalyEvent.cause_category)
    )
    anomaly_data = [dict(row._mapping) for row in anomaly_result]

    # Intervention outcomes
    outcome_result = await session.execute(
        select(
            func.avg(InterventionOutcome.delta_score).label("avg_aqi_improvement"),
            func.count(InterventionOutcome.id).label("total_interventions"),
            func.avg(InterventionOutcome.carbon_saved_kg).label("avg_carbon_saved"),
        )
        .join(EnforcementAction, InterventionOutcome.action_id == EnforcementAction.id)
        .where(
            EnforcementAction.city == city,
            InterventionOutcome.created_at >= since,
            InterventionOutcome.is_deleted.is_(False),
        )
    )
    outcome_row = outcome_result.one_or_none()

    result = {
        "city": city,
        "period_days": days,
        "aqi_trend": trend_data,
        "recent_p95_aqi": recent_p95_aqi,
        "enforcement_summary": enforcement_data,
        "anomaly_breakdown": anomaly_data,
        "intervention_outcomes": dict(outcome_row._mapping) if outcome_row else {},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    await cache_set(cache_key, result, ttl=1800)
    return APIResponse(data=result)


def _empty_city_comparison_entry() -> dict:
    return {
        "has_data": False,
        "current_aqi": None,
        "avg_aqi": None,
        "max_aqi": None,
        "min_aqi": None,
        "avg_pm25": None,
        "avg_pm10": None,
        "avg_no2": None,
        "avg_so2": None,
        "avg_o3": None,
        "trend": None,
        "unhealthy_days": 0,
        "active_hotspots": 0,
        "enforcement_actions": 0,
    }


@router.get("/comparison", response_model=APIResponse[dict])
async def get_city_comparison(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    cities: list[str] = Query(default=["Pune", "Mumbai"]),
    days: int = Query(default=30, ge=1, le=365),
    start_date: date | None = Query(
        default=None,
        description="Custom range start (overrides `days` when combined with end_date)",
    ),
    end_date: date | None = Query(
        default=None,
        description="Custom range end (overrides `days` when combined with start_date)",
    ),
) -> APIResponse[dict]:
    now = datetime.now(timezone.utc)
    if start_date and end_date:
        since = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        until = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
    else:
        since = now - timedelta(days=days)
        until = now
    midpoint = since + (until - since) / 2

    gis_svc = GISService(session)

    comparison: dict[str, dict] = {}
    for city in cities[:6]:  # cap at 6 cities
        stats = await session.execute(
            text("""
            SELECT
                COUNT(*) AS reading_count,
                AVG(r.aqi) AS avg_aqi, MAX(r.aqi) AS max_aqi, MIN(r.aqi) AS min_aqi,
                AVG(r.pm25) AS avg_pm25, AVG(r.pm10) AS avg_pm10,
                AVG(r.no2) AS avg_no2, AVG(r.so2) AS avg_so2, AVG(r.o3) AS avg_o3
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city
              AND r.timestamp BETWEEN :since AND :until
              AND r.is_deleted = false AND r.quality_flag != 'invalid'
        """),
            {"city": city, "since": since, "until": until},
        )
        row = stats.one_or_none()

        if not row or not row.reading_count:
            comparison[city] = _empty_city_comparison_entry()
            continue

        current_aqi = await session.scalar(
            text("""
            SELECT AVG(r.aqi) FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city AND r.timestamp > NOW() - INTERVAL '1 hour'
              AND r.is_deleted = false AND r.quality_flag != 'invalid'
        """),
            {"city": city},
        )

        halves = await session.execute(
            text("""
            SELECT
                AVG(CASE WHEN r.timestamp < :mid THEN r.aqi END) AS first_half_avg,
                AVG(CASE WHEN r.timestamp >= :mid THEN r.aqi END) AS second_half_avg
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city AND r.timestamp BETWEEN :since AND :until
              AND r.is_deleted = false AND r.quality_flag != 'invalid'
        """),
            {"city": city, "since": since, "until": until, "mid": midpoint},
        )
        half_row = halves.one_or_none()
        trend = None
        if (
            half_row
            and half_row.first_half_avg is not None
            and half_row.second_half_avg is not None
        ):
            delta = half_row.second_half_avg - half_row.first_half_avg
            if delta > 5:
                trend = "worsening"
            elif delta < -5:
                trend = "improving"
            else:
                trend = "stable"

        unhealthy_days = await session.scalar(
            text("""
            SELECT COUNT(*) FROM (
                SELECT date_trunc('day', r.timestamp) AS day, AVG(r.aqi) AS day_avg
                FROM aqi_readings r
                JOIN monitoring_stations s ON r.station_id = s.id
                WHERE s.city = :city AND r.timestamp BETWEEN :since AND :until
                  AND r.is_deleted = false AND r.quality_flag != 'invalid'
                GROUP BY date_trunc('day', r.timestamp)
            ) d WHERE d.day_avg > 100
        """),
            {"city": city, "since": since, "until": until},
        )

        enforcement_count = await session.scalar(
            select(func.count(EnforcementAction.id)).where(
                EnforcementAction.city == city,
                EnforcementAction.created_at >= since,
                EnforcementAction.created_at <= until,
                EnforcementAction.is_deleted.is_(False),
            )
        )

        try:
            hotspots = await gis_svc.pollution_hotspots(city)
            active_hotspots = len(hotspots)
        except Exception:  # noqa: BLE001 -- hotspot clustering is best-effort here
            active_hotspots = 0

        comparison[city] = {
            "has_data": True,
            "current_aqi": (
                round(float(current_aqi), 1) if current_aqi is not None else None
            ),
            "avg_aqi": (
                round(float(row.avg_aqi), 1) if row.avg_aqi is not None else None
            ),
            "max_aqi": int(row.max_aqi) if row.max_aqi is not None else None,
            "min_aqi": int(row.min_aqi) if row.min_aqi is not None else None,
            "avg_pm25": (
                round(float(row.avg_pm25), 1) if row.avg_pm25 is not None else None
            ),
            "avg_pm10": (
                round(float(row.avg_pm10), 1) if row.avg_pm10 is not None else None
            ),
            "avg_no2": (
                round(float(row.avg_no2), 1) if row.avg_no2 is not None else None
            ),
            "avg_so2": (
                round(float(row.avg_so2), 1) if row.avg_so2 is not None else None
            ),
            "avg_o3": round(float(row.avg_o3), 1) if row.avg_o3 is not None else None,
            "trend": trend,
            "unhealthy_days": int(unhealthy_days or 0),
            "active_hotspots": active_hotspots,
            "enforcement_actions": enforcement_count or 0,
        }

    policies = await session.execute(
        select(PolicySnapshot)
        .where(
            PolicySnapshot.city.in_(cities),
            PolicySnapshot.is_deleted.is_(False),
        )
        .order_by(desc(PolicySnapshot.implemented_at))
        .limit(20)
    )
    policy_data = [
        {
            "city": p.city,
            "policy_type": p.policy_type,
            "impact_score": p.impact_score,
            "aqi_delta": p.aqi_delta,
            "implemented_at": (
                p.implemented_at.isoformat() if p.implemented_at else None
            ),
        }
        for p in policies.scalars().all()
    ]

    return APIResponse(
        data={
            "cities": comparison,
            "policies": policy_data,
            "period_days": days,
            "period_start": since.date().isoformat(),
            "period_end": until.date().isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
