from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.core.redis_client import cache_get, cache_set
from app.models.analytics import PollutionAttribution
from app.models.enforcement import CitizenAlert
from app.schemas.base import APIResponse, PaginatedResponse
from app.schemas.enforcement import (
    AttributionResponse,
    CitizenAlertCreate,
    CitizenAlertResponse,
)

attribution_router = APIRouter(prefix="/attribution", tags=["Pollution Attribution"])
alerts_router = APIRouter(prefix="/alerts", tags=["Citizen Alerts"])


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
            PollutionAttribution.is_deleted == False,
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
        PollutionAttribution.is_deleted == False,
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
    query = select(CitizenAlert).where(CitizenAlert.is_deleted == False)
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
