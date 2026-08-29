"""City Sustainability Score endpoint.

Thin wrapper around app.services.sustainability_score — see that
module's docstring for the scoring methodology and the data-truthfulness
rules (a component with no on-record data is reported unavailable,
never defaulted to a placeholder value).
"""

from typing import Annotated

from app.api.deps import CurrentUser, get_db
from app.schemas.base import APIResponse
from app.schemas.sustainability import SustainabilityScoreResponse
from app.services.sustainability_score import compute_city_sustainability_score
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/sustainability", tags=["Sustainability Score"])


@router.get("/score", response_model=APIResponse[SustainabilityScoreResponse])
async def get_sustainability_score(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[SustainabilityScoreResponse]:
    result = await compute_city_sustainability_score(session, city)
    return APIResponse(
        data=SustainabilityScoreResponse(
            city=result.city,
            overall_score=result.overall_score,
            indicators_available=result.indicators_available,
            indicators_total=result.indicators_total,
            components=[
                {
                    "name": c.name,
                    "score": c.score,
                    "classification": c.classification,
                    "note": c.note,
                }
                for c in result.components
            ],
            methodology=result.methodology,
            generated_at=result.generated_at,
        )
    )
