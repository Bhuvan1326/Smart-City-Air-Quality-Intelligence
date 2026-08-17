from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.core.redis_client import cache_get, cache_set
from app.models.analytics import AnomalyEvent, PolicySnapshot
from app.models.enforcement import EnforcementAction, InterventionOutcome
from app.schemas.base import APIResponse

router = APIRouter(prefix="/analytics", tags=["Analytics"])


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

    # Daily AQI trend: read from the continuous aggregate (see migration
    # 003_timescaledb_optimization) instead of re-scanning raw aqi_readings
    # across the whole window on every cache miss — TimescaleDB maintains
    # aqi_daily_by_station incrementally, so this is a small, fast read
    # regardless of how many days are requested. Station->city/ward context
    # is joined in from the small monitoring_stations table at query time
    # (continuous aggregates avoid joins for portability across TimescaleDB
    # versions — see the migration for why).
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

    # p95 needs the raw distribution (continuous aggregates can't carry
    # ordered-set aggregates like PERCENTILE_CONT across all TimescaleDB
    # versions) — kept on a short, recent raw-data window rather than the
    # full `days` range, which is the expensive part this change avoids.
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
            EnforcementAction.is_deleted == False,
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
            AnomalyEvent.is_deleted == False,
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
            InterventionOutcome.is_deleted == False,
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


@router.get("/comparison", response_model=APIResponse[dict])
async def get_city_comparison(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    cities: list[str] = Query(default=["Pune", "Mumbai"]),
    days: int = Query(default=30, ge=1, le=365),
) -> APIResponse[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    comparison = {}
    for city in cities[:6]:  # cap at 6 cities
        aqi_avg = await session.execute(
            text("""
            SELECT AVG(r.aqi) as avg_aqi, MAX(r.aqi) as max_aqi
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city
              AND r.timestamp >= :since
              AND r.is_deleted = false
        """),
            {"city": city, "since": since},
        )
        row = aqi_avg.one_or_none()

        enforcement_count = await session.scalar(
            select(func.count(EnforcementAction.id)).where(
                EnforcementAction.city == city,
                EnforcementAction.created_at >= since,
                EnforcementAction.is_deleted == False,
            )
        )

        comparison[city] = {
            "avg_aqi": float(row.avg_aqi or 0) if row else 0,
            "max_aqi": int(row.max_aqi or 0) if row else 0,
            "enforcement_actions": enforcement_count or 0,
        }

    policies = await session.execute(
        select(PolicySnapshot)
        .where(
            PolicySnapshot.city.in_(cities),
            PolicySnapshot.is_deleted == False,
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
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
