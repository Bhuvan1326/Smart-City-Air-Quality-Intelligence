from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.core.redis_client import cache_get, cache_set
from app.models.analytics import AnomalyEvent
from app.models.enforcement import ActionStatus, CitizenAlert, EnforcementAction
from app.repositories.aqi import AQIReadingRepository, MonitoringStationRepository
from app.schemas.base import APIResponse
from app.schemas.enforcement import DashboardOverview

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/overview", response_model=APIResponse[DashboardOverview])
async def get_dashboard_overview(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[DashboardOverview]:
    cache_key = f"dashboard:overview:{city}"
    cached = await cache_get(cache_key)
    if cached:
        return APIResponse(data=cached)

    station_repo = MonitoringStationRepository(session)
    reading_repo = AQIReadingRepository(session)

    # Active stations
    stations = await station_repo.get_active_by_city(city)
    active_count = len(stations)

    # Ward AQI snapshot
    ward_data = await reading_repo.get_ward_aqi_snapshot(city)

    avg_aqi = 0.0
    max_aqi = 0
    max_aqi_ward = None
    unhealthy_wards = 0
    aqi_summary: dict[str, int] = {
        "Good": 0,
        "Moderate": 0,
        "Unhealthy": 0,
        "Very Unhealthy": 0,
        "Hazardous": 0,
    }

    for w in ward_data:
        aqi_val = int(w["avg_aqi"] or 0)
        avg_aqi += aqi_val
        if aqi_val > max_aqi:
            max_aqi = aqi_val
            max_aqi_ward = w["ward_id"]
        if aqi_val > 100:
            unhealthy_wards += 1

        if aqi_val <= 50:
            aqi_summary["Good"] += 1
        elif aqi_val <= 100:
            aqi_summary["Moderate"] += 1
        elif aqi_val <= 200:
            aqi_summary["Unhealthy"] += 1
        elif aqi_val <= 300:
            aqi_summary["Very Unhealthy"] += 1
        else:
            aqi_summary["Hazardous"] += 1

    if ward_data:
        avg_aqi = avg_aqi / len(ward_data)

    # Trend: current city average vs. the average from ~24h ago, computed
    # from actual historical readings (falls back to 0.0, i.e. "no change
    # detectable", only when there isn't enough historical data yet).
    prior_avg_aqi = await reading_repo.get_city_average_aqi_around(city, hours_ago=24)
    if prior_avg_aqi is not None and ward_data:
        aqi_trend_24h = round(avg_aqi - prior_avg_aqi, 1)
    else:
        aqi_trend_24h = 0.0

    # Active alerts
    alert_count_result = await session.scalar(
        select(func.count(CitizenAlert.id)).where(
            CitizenAlert.city == city,
            CitizenAlert.delivery_status == "pending",
            CitizenAlert.is_deleted.is_(False),
        )
    )

    # Pending enforcements
    enforcement_count_result = await session.scalar(
        select(func.count(EnforcementAction.id)).where(
            EnforcementAction.city == city,
            EnforcementAction.status == ActionStatus.PENDING,
            EnforcementAction.is_deleted.is_(False),
        )
    )

    # Anomalies today
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    anomaly_count_result = await session.scalar(
        select(func.count(AnomalyEvent.id)).where(
            AnomalyEvent.city == city,
            AnomalyEvent.detected_at >= today_start,
            AnomalyEvent.is_deleted.is_(False),
        )
    )

    overview = DashboardOverview(
        city=city,
        timestamp=datetime.now(timezone.utc),
        active_stations=active_count,
        avg_aqi=round(avg_aqi, 1),
        max_aqi=max_aqi,
        max_aqi_ward=max_aqi_ward,
        unhealthy_wards=unhealthy_wards,
        active_alerts=alert_count_result or 0,
        pending_enforcements=enforcement_count_result or 0,
        anomalies_today=anomaly_count_result or 0,
        aqi_trend_24h=aqi_trend_24h,
        top_pollutant="PM2.5",
        air_quality_index_summary=aqi_summary,
    )

    await cache_set(cache_key, overview.model_dump(mode="json"), ttl=120)
    return APIResponse(data=overview)
