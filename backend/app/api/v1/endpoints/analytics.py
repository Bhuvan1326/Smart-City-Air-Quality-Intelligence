from datetime import date, datetime, timedelta, timezone
from typing import Annotated
from zoneinfo import ZoneInfo

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

# Analytics is restricted to administrators/officers on the frontend
# sidebar; enforce the same boundary server-side (BUG 012) so it can't be
# bypassed by calling the API URL directly.
router = APIRouter(
    prefix="/analytics", tags=["Analytics"], dependencies=[RequireAnalyst]
)

# This deployment's cities are all Indian cities, and calendar-day grouping
# (daily trend buckets, "unhealthy days", custom date-range boundaries) must
# align with the local IST calendar day, not the UTC day. Truncating a
# timestamptz to a day without this conversion silently shifts any reading
# taken between 00:00-05:29 IST onto the previous UTC day.
IST = ZoneInfo("Asia/Kolkata")


def _ist_day_bounds_utc(day: date) -> datetime:
    """UTC instant corresponding to 00:00 on `day` in IST."""
    return datetime(day.year, day.month, day.day, tzinfo=IST).astimezone(timezone.utc)


async def _fetch_daily_trend_from_raw_readings(
    session: AsyncSession, city: str, since: datetime, until: datetime | None = None
) -> list[dict]:
    """Compute the (day, avg_aqi, max_aqi, min_aqi) trend directly from raw
    aqi_readings, bucketed by IST calendar day.

    This is the source of truth for the trend chart rather than an
    opportunistic fallback: the `aqi_daily_by_station` TimescaleDB
    continuous aggregate (see db_migrations/versions/003_timescaledb_
    optimization.py) buckets days using `time_bucket('1 day', timestamp)`,
    which groups by UTC calendar day. For IST readings that means anything
    observed between 00:00 and 05:29 IST is silently attributed to the
    previous day. Recomputing from raw readings with an explicit IST
    truncation avoids that shift; it also needs no extra schema, so it
    works whether or not the continuous aggregate/migration has been
    applied to this database.
    """
    until_clause = "AND r.timestamp < :until" if until is not None else ""
    params = {"city": city, "since": since}
    if until is not None:
        params["until"] = until

    result = await session.execute(
        text(
            f"""
        SELECT
            (date_trunc('day', r.timestamp AT TIME ZONE 'Asia/Kolkata'))::date AS day,
            AVG(r.aqi) AS avg_aqi,
            MAX(r.aqi) AS max_aqi,
            MIN(r.aqi) AS min_aqi
        FROM aqi_readings r
        JOIN monitoring_stations s ON r.station_id = s.id
        WHERE s.city = :city AND r.timestamp >= :since
          {until_clause}
          AND r.is_deleted = false AND r.quality_flag != 'invalid'
        GROUP BY date_trunc('day', r.timestamp AT TIME ZONE 'Asia/Kolkata')
        ORDER BY day
    """
        ),
        params,
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

    # The aqi_daily_by_station continuous aggregate buckets days in UTC
    # (see _fetch_daily_trend_from_raw_readings' docstring), which shifts
    # early-morning IST readings onto the wrong calendar day, so it is not
    # used here even as a fast path — the raw-reading query below is the
    # only source that can bucket correctly by IST day. It's still guarded
    # against a query failure so a transient DB error surfaces as an empty
    # trend (empty state) rather than a 500.
    try:
        trend_data = await _fetch_daily_trend_from_raw_readings(session, city, since)
    except (ProgrammingError, DBAPIError):
        await session.rollback()
        trend_data = []

    p95_window = min(days, 7)
    p95_since = datetime.now(timezone.utc) - timedelta(days=p95_window)
    p95_result = await session.execute(
        text(
            """
        SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY r.aqi) AS p95_aqi
        FROM aqi_readings r
        JOIN monitoring_stations s ON r.station_id = s.id
        WHERE s.city = :city AND r.timestamp >= :since
          AND r.is_deleted = false AND r.quality_flag != 'invalid'
    """
        ),
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
        # start_date/end_date are IST calendar dates (the app's cities are
        # all in India, and the frontend's native <input type="date">
        # reflects the user's local — IST — calendar day). Use an explicit
        # [start, end) interval: since = IST midnight of start_date, until
        # = IST midnight of the day *after* end_date, so the whole of
        # end_date is included without also pulling in the first instant
        # of the following day.
        since = _ist_day_bounds_utc(start_date)
        until = _ist_day_bounds_utc(end_date + timedelta(days=1))
        period_start = start_date.isoformat()
        period_end = end_date.isoformat()
    else:
        since = now - timedelta(days=days)
        until = now
        period_start = since.date().isoformat()
        period_end = until.date().isoformat()
    midpoint = since + (until - since) / 2

    gis_svc = GISService(session)

    comparison: dict[str, dict] = {}
    for city in cities[:6]:  # cap at 6 cities
        stats = await session.execute(
            text(
                """
            SELECT
                COUNT(*) AS reading_count,
                AVG(r.aqi) AS avg_aqi, MAX(r.aqi) AS max_aqi, MIN(r.aqi) AS min_aqi,
                AVG(r.pm25) AS avg_pm25, AVG(r.pm10) AS avg_pm10,
                AVG(r.no2) AS avg_no2, AVG(r.so2) AS avg_so2, AVG(r.o3) AS avg_o3
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city
              AND r.timestamp >= :since AND r.timestamp < :until
              AND r.is_deleted = false AND r.quality_flag != 'invalid'
        """
            ),
            {"city": city, "since": since, "until": until},
        )
        row = stats.one_or_none()

        if not row or not row.reading_count:
            comparison[city] = _empty_city_comparison_entry()
            continue

        current_aqi = await session.scalar(
            text(
                """
            SELECT AVG(r.aqi) FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city AND r.timestamp > NOW() - INTERVAL '1 hour'
              AND r.is_deleted = false AND r.quality_flag != 'invalid'
        """
            ),
            {"city": city},
        )

        halves = await session.execute(
            text(
                """
            SELECT
                AVG(CASE WHEN r.timestamp < :mid THEN r.aqi END) AS first_half_avg,
                AVG(CASE WHEN r.timestamp >= :mid THEN r.aqi END) AS second_half_avg
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city AND r.timestamp >= :since AND r.timestamp < :until
              AND r.is_deleted = false AND r.quality_flag != 'invalid'
        """
            ),
            {"city": city, "since": since, "until": until, "mid": midpoint},
        )
        half_row = halves.one_or_none()
        # `trend` is only meaningful when the period actually has readings
        # on both sides of the midpoint — e.g. a handful of readings all
        # taken in the last couple of hours of a 30-day window have no
        # "before" half to compare against. Previously this fell through to
        # a hard-coded "stable" default, which misrepresents genuinely
        # insufficient data as a real (flat) trend. Leave it unset (None)
        # in that case instead; the frontend already renders a null trend
        # as "—".
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

        # Computed directly from raw aqi_readings (not the aqi_daily_by_station
        # continuous aggregate that get_city_analytics uses above) — that
        # aggregate is created by an Alembic migration (see
        # db_migrations/versions/003_timescaledb_optimization.py), not by the
        # SQLAlchemy ORM metadata the test suite provisions, so relying on it
        # here would make this endpoint untestable without also running
        # migrations. Grouping raw readings by day is a little more work per
        # query but needs no extra schema and has no refresh lag. Days are
        # bucketed in IST (see _fetch_daily_trend_from_raw_readings) so a
        # reading just after midnight IST counts toward the correct day.
        unhealthy_days = await session.scalar(
            text(
                """
            SELECT COUNT(*) FROM (
                SELECT date_trunc('day', r.timestamp AT TIME ZONE 'Asia/Kolkata') AS day,
                       AVG(r.aqi) AS day_avg
                FROM aqi_readings r
                JOIN monitoring_stations s ON r.station_id = s.id
                WHERE s.city = :city AND r.timestamp >= :since AND r.timestamp < :until
                  AND r.is_deleted = false AND r.quality_flag != 'invalid'
                GROUP BY date_trunc('day', r.timestamp AT TIME ZONE 'Asia/Kolkata')
            ) d WHERE d.day_avg > 100
        """
            ),
            {"city": city, "since": since, "until": until},
        )

        enforcement_count = await session.scalar(
            select(func.count(EnforcementAction.id)).where(
                EnforcementAction.city == city,
                EnforcementAction.created_at >= since,
                EnforcementAction.created_at < until,
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
            "period_start": period_start,
            "period_end": period_end,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
