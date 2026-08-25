from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, RequireAdmin, get_db
from app.core.redis_client import cache_delete_pattern, cache_get, cache_set
from app.models.analytics import PollutionAttribution
from app.models.enforcement import AlertThreshold, CitizenAlert
from app.repositories.aqi import AQIReadingRepository, MonitoringStationRepository
from app.schemas.base import APIResponse, PaginatedResponse
from app.schemas.enforcement import (
    AlertThresholdCreate,
    AlertThresholdResponse,
    AlertThresholdUpdate,
    AttributionResponse,
    CitizenAlertCreate,
    CitizenAlertResponse,
    MitigationRecommendationResponse,
    RecommendedActionResponse,
)
from app.services.mitigation_recommendations import generate_recommendation

attribution_router = APIRouter(prefix="/attribution", tags=["Pollution Attribution"])
alerts_router = APIRouter(prefix="/alerts", tags=["Citizen Alerts"])
thresholds_router = APIRouter(
    prefix="/alerts/thresholds", tags=["Alert Thresholds"]
)
mitigation_router = APIRouter(prefix="/mitigation", tags=["Mitigation Recommendations"])


@attribution_router.get("/live", response_model=APIResponse[list[AttributionResponse]])
async def get_live_attribution(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[list[AttributionResponse]]:
    cache_key = f"attribution:live:{city}"
    cached = await cache_get(cache_key)
    if cached:
        return APIResponse(data=cached)

    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    result = await session.execute(
        select(PollutionAttribution)
        .where(
            PollutionAttribution.city == city,
            PollutionAttribution.timestamp >= one_hour_ago,
            PollutionAttribution.is_deleted.is_(False),
        )
        .order_by(desc(PollutionAttribution.timestamp))
    )
    attributions = list(result.scalars().all())

    items = [AttributionResponse.model_validate(a) for a in attributions]
    serialized = [i.model_dump(mode="json") for i in items]
    await cache_set(cache_key, serialized, ttl=600)
    return APIResponse(data=items)


@attribution_router.get(
    "/history", response_model=APIResponse[list[AttributionResponse]]
)
async def get_attribution_history(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
    ward_id: str | None = Query(None),
    start_time: datetime = Query(
        default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=7)
    ),
    end_time: datetime = Query(default_factory=lambda: datetime.now(timezone.utc)),
) -> APIResponse[list[AttributionResponse]]:
    query = select(PollutionAttribution).where(
        PollutionAttribution.city == city,
        PollutionAttribution.timestamp.between(start_time, end_time),
        PollutionAttribution.is_deleted.is_(False),
    )
    if ward_id:
        query = query.where(PollutionAttribution.ward_id == ward_id)
    query = query.order_by(PollutionAttribution.timestamp)

    result = await session.execute(query)
    attributions = list(result.scalars().all())
    return APIResponse(
        data=[AttributionResponse.model_validate(a) for a in attributions]
    )


@alerts_router.get(
    "", response_model=APIResponse[PaginatedResponse[CitizenAlertResponse]]
)
async def list_alerts(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str | None = Query(None),
    ward_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> APIResponse[PaginatedResponse[CitizenAlertResponse]]:
    query = select(CitizenAlert).where(CitizenAlert.is_deleted.is_(False))
    if city:
        query = query.where(CitizenAlert.city == city)
    if ward_id:
        query = query.where(CitizenAlert.ward_id == ward_id)

    query = query.order_by(desc(CitizenAlert.created_at))

    from sqlalchemy import func

    count_q = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_q) or 0
    result = await session.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )
    alerts = list(result.scalars().all())
    items = [CitizenAlertResponse.model_validate(a) for a in alerts]
    return APIResponse(data=PaginatedResponse.create(items, total, page, page_size))


@alerts_router.post(
    "",
    response_model=APIResponse[CitizenAlertResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_alert(
    data: CitizenAlertCreate,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[CitizenAlertResponse]:
    from app.models.user import UserRole

    if current_user.role == UserRole.CITIZEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    # Generate message via AI agent (called from service layer in full implementation)
    message_title = f"Air Quality Alert - Ward {data.ward_id}"
    message_text = (
        f"AQI level is {data.risk_level.value.replace('_', ' ').title()} in your area."
    )

    alert = CitizenAlert(
        ward_id=data.ward_id,
        city=data.city,
        language=data.language,
        channel=data.channel,
        risk_level=data.risk_level,
        message_title=message_title,
        message_text=message_text,
        vulnerability_groups_targeted=data.vulnerability_groups,
        aqi_value=data.aqi_value,
        delivery_status="pending",
        ai_generated=True,
    )
    session.add(alert)
    await session.flush()
    await session.refresh(alert)
    return APIResponse(
        data=CitizenAlertResponse.model_validate(alert), message="Alert created"
    )


# ---------------------------------------------------------------------------
# Alert Thresholds
#
# Reads are available to any authenticated user (thresholds inform citizens
# what "unhealthy" means for their city). Writes are restricted to City
# Administrators via RequireAdmin.
# ---------------------------------------------------------------------------


@thresholds_router.get("", response_model=APIResponse[list[AlertThresholdResponse]])
async def list_thresholds(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[list[AlertThresholdResponse]]:
    result = await session.execute(
        select(AlertThreshold)
        .where(
            AlertThreshold.city == city,
            AlertThreshold.is_deleted.is_(False),
        )
        .order_by(AlertThreshold.alert_type)
    )
    thresholds = list(result.scalars().all())
    return APIResponse(
        data=[AlertThresholdResponse.model_validate(t) for t in thresholds]
    )


@thresholds_router.post(
    "",
    response_model=APIResponse[AlertThresholdResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[RequireAdmin],
)
async def create_threshold(
    data: AlertThresholdCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[AlertThresholdResponse]:
    existing = await session.execute(
        select(AlertThreshold).where(
            AlertThreshold.city == data.city,
            AlertThreshold.alert_type == data.alert_type,
            AlertThreshold.is_deleted.is_(False),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A threshold for '{data.alert_type}' already exists in {data.city}. Use PATCH to edit it.",
        )

    threshold = AlertThreshold(
        city=data.city,
        alert_type=data.alert_type,
        threshold_value=data.threshold_value,
        cooldown_minutes=data.cooldown_minutes,
        is_enabled=data.is_enabled,
    )
    session.add(threshold)
    await session.flush()
    await session.refresh(threshold)
    await cache_delete_pattern(f"thresholds:{data.city}:*")
    return APIResponse(
        data=AlertThresholdResponse.model_validate(threshold),
        message="Threshold created",
    )


@thresholds_router.patch(
    "/{threshold_id}",
    response_model=APIResponse[AlertThresholdResponse],
    dependencies=[RequireAdmin],
)
async def update_threshold(
    threshold_id: str,
    data: AlertThresholdUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[AlertThresholdResponse]:
    result = await session.execute(
        select(AlertThreshold).where(
            AlertThreshold.id == threshold_id,
            AlertThreshold.is_deleted.is_(False),
        )
    )
    threshold = result.scalar_one_or_none()
    if threshold is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Threshold not found"
        )

    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(threshold, field, value)

    await session.flush()
    await session.refresh(threshold)
    await cache_delete_pattern(f"thresholds:{threshold.city}:*")
    return APIResponse(
        data=AlertThresholdResponse.model_validate(threshold),
        message="Threshold updated",
    )


@thresholds_router.delete(
    "/{threshold_id}",
    response_model=APIResponse[None],
    dependencies=[RequireAdmin],
)
async def delete_threshold(
    threshold_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[None]:
    result = await session.execute(
        select(AlertThreshold).where(
            AlertThreshold.id == threshold_id,
            AlertThreshold.is_deleted.is_(False),
        )
    )
    threshold = result.scalar_one_or_none()
    if threshold is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Threshold not found"
        )

    threshold.soft_delete()
    await session.flush()
    await cache_delete_pattern(f"thresholds:{threshold.city}:*")
    return APIResponse(data=None, message="Threshold deleted")


# ---------------------------------------------------------------------------
# Mitigation Recommendations
#
# "Recommend" step of Detect -> Predict -> Recommend -> Simulate. Combines
# the latest AQI reading and pollution-attribution snapshot for a ward and
# runs them through the deterministic rules engine in
# app/services/mitigation_recommendations.py. No AQI reduction number is
# ever invented here — recommended actions link to real scenario keys in
# the What-If Simulator (POST /simulator/whatif) for an actual quantified
# estimate.
# ---------------------------------------------------------------------------


@mitigation_router.get(
    "/recommendations", response_model=APIResponse[MitigationRecommendationResponse]
)
async def get_mitigation_recommendations(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
    ward_id: str | None = Query(default=None, description="Ward to scope to"),
) -> APIResponse[MitigationRecommendationResponse]:
    station_repo = MonitoringStationRepository(session)
    reading_repo = AQIReadingRepository(session)

    stations = await station_repo.get_active_by_city(city)
    if ward_id:
        stations = [s for s in stations if s.ward_id == ward_id]
    if not stations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active monitoring stations found for this city/ward",
        )

    # Same "worst-case station" convention used by /aqi/health-risk — a
    # mitigation recommendation should target the worst reading available,
    # not an arbitrary station.
    candidates = []
    for station in stations:
        r = await reading_repo.get_latest_by_station(station.id)
        if r is not None:
            candidates.append((station, r))
    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No recent readings available for this city/ward",
        )
    worst_station, reading = max(candidates, key=lambda pair: pair[1].aqi or 0)
    resolved_ward_id = ward_id or worst_station.ward_id

    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=3)
    attr_result = await session.execute(
        select(PollutionAttribution)
        .where(
            PollutionAttribution.city == city,
            PollutionAttribution.ward_id == resolved_ward_id,
            PollutionAttribution.timestamp >= one_hour_ago,
            PollutionAttribution.is_deleted.is_(False),
        )
        .order_by(desc(PollutionAttribution.timestamp))
        .limit(1)
    )
    attribution = attr_result.scalar_one_or_none()

    rec = generate_recommendation(
        aqi=reading.aqi,
        pm25=reading.pm25,
        pm10=reading.pm10,
        no2=reading.no2,
        co=reading.co,
        o3=reading.o3,
        so2=None,  # not currently on the AQIReading model
        vehicular_pct=attribution.vehicular_pct if attribution else None,
        industrial_pct=attribution.industrial_pct if attribution else None,
        construction_pct=attribution.construction_pct if attribution else None,
        biomass_pct=attribution.biomass_pct if attribution else None,
        dust_pct=attribution.dust_pct if attribution else None,
        domestic_pct=attribution.domestic_pct if attribution else None,
        wind_speed_mps=reading.wind_speed,
    )

    return APIResponse(
        data=MitigationRecommendationResponse(
            ward_id=resolved_ward_id,
            city=city,
            aqi=rec.aqi,
            primary_pollutant=rec.primary_pollutant,
            overall_risk=rec.overall_risk.value,
            contributing_factors=rec.contributing_factors,
            recommended_actions=[
                RecommendedActionResponse(
                    action=a.action,
                    target_source=a.target_source,
                    rationale=a.rationale,
                    simulation_scenario_key=a.simulation_scenario_key,
                )
                for a in rec.recommended_actions
            ],
            impact_disclaimer=rec.impact_disclaimer,
            attribution_confidence=attribution.overall_confidence if attribution else None,
            attribution_timestamp=attribution.timestamp if attribution else None,
        )
    )
