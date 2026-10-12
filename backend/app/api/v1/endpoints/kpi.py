from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.schemas.base import APIResponse
from app.schemas.kpi import DataFreshnessKPI
from app.services.kpi_freshness import compute_data_freshness_kpi

router = APIRouter(prefix="/kpi", tags=["KPIs"])


@router.get("/data-freshness", response_model=APIResponse[DataFreshnessKPI])
async def data_freshness_kpi(
    _: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: Annotated[str, Query(min_length=1, max_length=100)] = "Pune",
) -> APIResponse[DataFreshnessKPI]:
    """K1 data-freshness KPI for a city (see docs/week-1/kpi-definitions.md)."""
    return APIResponse(data=await compute_data_freshness_kpi(session, city))
