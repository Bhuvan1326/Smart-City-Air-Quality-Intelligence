from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.core.redis_client import cache_get, cache_set
from app.models.enforcement import ForecastGrid
from app.schemas.aqi import get_aqi_category
from app.schemas.base import APIResponse
from app.schemas.enforcement import ForecastResponse, WardForecastSummary
from app.workers.tasks.forecast import compute_live_ward_forecast

router = APIRouter(prefix="/forecast", tags=["Forecasting"])


@router.get("", response_model=APIResponse[list[ForecastResponse]])
async def get_city_forecast(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
    hours_ahead: int = Query(default=24, ge=1, le=72),
) -> APIResponse[list[ForecastResponse]]:
    cache_key = f"forecast:{city}:{hours_ahead}"
    cached = await cache_get(cache_key)
    if cached:
        return APIResponse(data=cached)

    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(ForecastGrid)
        .where(
            ForecastGrid.city == city,
            ForecastGrid.forecast_timestamp >= now,
            ForecastGrid.is_deleted == False,  # noqa: E712
        )
        .order_by(ForecastGrid.forecast_timestamp)
        .limit(hours_ahead * 20)  # multiple wards per hour
    )
    forecasts = list(result.scalars().all())

    items = []
    for f in forecasts:
        category, _ = get_aqi_category(f.aqi_forecast)
        items.append(
            ForecastResponse(
                id=f.id,
                city=f.city,
                ward_id=f.ward_id,
                forecast_timestamp=f.forecast_timestamp,
                generated_at=f.generated_at,
                aqi_forecast=f.aqi_forecast,
                pm25_forecast=f.pm25_forecast,
                confidence_score=f.confidence_score,
                confidence_lower=f.confidence_lower,
                confidence_upper=f.confidence_upper,
                model_version=f.model_version,
                contributing_factors=f.contributing_factors,
                feature_importance=f.feature_importance,
                aqi_category=category,
            )
        )

    serialized = [i.model_dump(mode="json") for i in items]
    await cache_set(cache_key, serialized, ttl=3600)
    return APIResponse(data=items)


@router.get("/{ward_id}", response_model=APIResponse[WardForecastSummary])
async def get_ward_forecast(
    ward_id: str,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
    live: bool = Query(
        default=False,
        description=(
            "If true, bypass the hourly-cached forecast grid and compute a "
            "fresh forecast right now from current AQI/wind observations. "
            "Used by the frontend's manual Refresh action."
        ),
    ),
) -> APIResponse[WardForecastSummary]:
    if live:
        live_result = await compute_live_ward_forecast(session, city, ward_id, hours_ahead=72)
        if live_result is None:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No current AQI data available for this ward — cannot generate a live forecast.",
            )

        forecast_responses = []
        peak_aqi = 0
        peak_at = datetime.now(timezone.utc)
        for fc in live_result["forecasts"]:
            category, _ = get_aqi_category(fc["aqi_forecast"])
            fr = ForecastResponse(
                id=uuid4(),  # not persisted — synthesized id for a point-in-time response
                city=city,
                ward_id=ward_id,
                forecast_timestamp=fc["forecast_timestamp"],
                generated_at=live_result["generated_at"],
                aqi_forecast=fc["aqi_forecast"],
                pm25_forecast=fc["pm25_forecast"],
                confidence_score=fc["confidence_score"],
                confidence_lower=fc["confidence_lower"],
                confidence_upper=fc["confidence_upper"],
                model_version=live_result["model_version"],
                contributing_factors=fc["contributing_factors"],
                feature_importance=fc["feature_importance"],
                aqi_category=category,
            )
            forecast_responses.append(fr)
            if fc["aqi_forecast"] > peak_aqi:
                peak_aqi = fc["aqi_forecast"]
                peak_at = fc["forecast_timestamp"]

        current = int(round(live_result["current_aqi"]))
        last = forecast_responses[-1].aqi_forecast if forecast_responses else current
        trend = (
            "improving"
            if last < current - 10
            else "worsening" if last > current + 10 else "stable"
        )

        return APIResponse(
            data=WardForecastSummary(
                ward_id=ward_id,
                city=city,
                current_aqi=current,
                forecasts=forecast_responses,
                peak_aqi=peak_aqi,
                peak_at=peak_at,
                trend=trend,
            )
        )

    cache_key = f"forecast:ward:{city}:{ward_id}"
    cached = await cache_get(cache_key)
    if cached:
        return APIResponse(data=cached)

    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(ForecastGrid)
        .where(
            ForecastGrid.city == city,
            ForecastGrid.ward_id == ward_id,
            ForecastGrid.forecast_timestamp >= now,
            ForecastGrid.is_deleted == False,  # noqa: E712
        )
        .order_by(ForecastGrid.forecast_timestamp)
        .limit(72)
    )
    forecasts = list(result.scalars().all())

    if not forecasts:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No forecast data for this ward",
        )

    forecast_responses = []
    peak_aqi = 0
    peak_at = now
    for f in forecasts:
        category, _ = get_aqi_category(f.aqi_forecast)
        fr = ForecastResponse(
            id=f.id,
            city=f.city,
            ward_id=f.ward_id,
            forecast_timestamp=f.forecast_timestamp,
            generated_at=f.generated_at,
            aqi_forecast=f.aqi_forecast,
            pm25_forecast=f.pm25_forecast,
            confidence_score=f.confidence_score,
            confidence_lower=f.confidence_lower,
            confidence_upper=f.confidence_upper,
            model_version=f.model_version,
            contributing_factors=f.contributing_factors,
            feature_importance=f.feature_importance,
            aqi_category=category,
        )
        forecast_responses.append(fr)
        if f.aqi_forecast > peak_aqi:
            peak_aqi = f.aqi_forecast
            peak_at = f.forecast_timestamp

    current = forecasts[0].aqi_forecast
    last = forecasts[-1].aqi_forecast
    trend = (
        "improving"
        if last < current - 10
        else "worsening" if last > current + 10 else "stable"
    )

    summary = WardForecastSummary(
        ward_id=ward_id,
        city=city,
        current_aqi=current,
        forecasts=forecast_responses,
        peak_aqi=peak_aqi,
        peak_at=peak_at,
        trend=trend,
    )

    await cache_set(cache_key, summary.model_dump(mode="json"), ttl=3600)
    return APIResponse(data=summary)
