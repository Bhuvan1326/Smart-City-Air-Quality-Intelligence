from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.core.redis_client import cache_get, cache_set
from app.schemas.base import APIResponse
from app.services.model_evaluation import evaluate_model_versions

router = APIRouter(prefix="/model-performance", tags=["Model Performance"])


@router.get("/history", response_model=APIResponse[list[dict]])
async def get_model_performance_history(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
    target: str = Query(default="aqi"),
) -> APIResponse[list[dict]]:
    """
    Real backtested evaluation metrics (MAE/RMSE/R²/MAPE) for every trained
    forecast model version, computed against actual historical AQI
    observations for the city. See app.services.model_evaluation.
    """
    cache_key = f"model-performance:history:{city}:{target}"
    cached = await cache_get(cache_key)
    if cached:
        return APIResponse(data=cached)

    records = await evaluate_model_versions(session, city, target)
    await cache_set(cache_key, records, ttl=3600)
    return APIResponse(data=records)


@router.get("/active", response_model=APIResponse[dict | None])
async def get_active_model_performance(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
    target: str = Query(default="aqi"),
) -> APIResponse[dict | None]:
    """Evaluation metrics for the currently active forecast model version,
    or null if no version could be evaluated (e.g. not enough historical
    data yet for this city)."""
    records = await evaluate_model_versions(session, city, target)
    active = next((r for r in records if r["is_active"]), None)
    return APIResponse(data=active)
