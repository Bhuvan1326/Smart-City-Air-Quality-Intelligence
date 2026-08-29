"""Smart Waste & Circularity Intelligence endpoint.

Waste figures are admin-entered per ward via the existing demographics
CRUD endpoints (POST/PATCH /exposure/demographics — see
app/api/v1/endpoints/exposure.py), reused here rather than duplicated,
since app.models.demographics.WardDemographics now carries the waste_*
fields alongside population/green_cover. See
app/services/waste_circularity.py for the scoring methodology and the
reasoning behind admin-entered (not live-fetched) municipal waste data.
"""

from datetime import UTC, datetime
from typing import Annotated

from app.api.deps import CurrentUser, get_db
from app.models.demographics import WardDemographics
from app.repositories.aqi import MonitoringStationRepository
from app.schemas.base import APIResponse
from app.schemas.waste import CircularityScoreResponse, WasteCircularityCityResponse
from app.services.waste_circularity import METHODOLOGY, score_circularity
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/waste", tags=["Smart Waste & Circularity"])


@router.get("/circularity", response_model=APIResponse[WasteCircularityCityResponse])
async def get_waste_circularity(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[WasteCircularityCityResponse]:
    """Per-ward waste-circularity scoring for a city, built entirely from
    admin-entered figures on file (never a live or fabricated value).
    """
    today = datetime.now(UTC).date()

    demo_result = await session.execute(
        select(WardDemographics).where(
            WardDemographics.city == city, WardDemographics.is_deleted.is_(False)
        )
    )
    demographics_by_ward = {d.ward_id: d for d in demo_result.scalars().all()}

    station_repo = MonitoringStationRepository(session)
    stations = await station_repo.get_active_by_city(city)
    ward_ids = sorted(
        {s.ward_id for s in stations if s.ward_id} | set(demographics_by_ward)
    )

    scores: list[CircularityScoreResponse] = []
    wards_with_no_data_on_file: list[str] = []
    for ward_id in ward_ids:
        demo = demographics_by_ward.get(ward_id)
        result = score_circularity(
            ward_id=ward_id,
            today=today,
            waste_generation_tons_per_day=(
                demo.waste_generation_tons_per_day if demo else None
            ),
            collection_efficiency_pct=(
                demo.waste_collection_efficiency_pct if demo else None
            ),
            recycling_pct=demo.waste_recycling_pct if demo else None,
            composting_pct=demo.waste_composting_pct if demo else None,
            landfill_pct=demo.waste_landfill_pct if demo else None,
            data_as_of=demo.waste_data_as_of if demo else None,
        )
        if not result.is_data_configured:
            wards_with_no_data_on_file.append(ward_id)
        scores.append(
            CircularityScoreResponse(
                ward_id=result.ward_id,
                waste_generation_tons_per_day=result.waste_generation_tons_per_day,
                collection_efficiency_pct=result.collection_efficiency_pct,
                recycling_pct=result.recycling_pct,
                composting_pct=result.composting_pct,
                landfill_pct=result.landfill_pct,
                recovery_rate_pct=result.recovery_rate_pct,
                recovery_rate_includes_recycling=result.recovery_rate_includes_recycling,
                recovery_rate_includes_composting=result.recovery_rate_includes_composting,
                landfill_dependency_pct=result.landfill_dependency_pct,
                circularity_score=result.circularity_score,
                circularity_unavailable_reason=result.circularity_unavailable_reason,
                data_as_of=result.data_as_of,
                freshness_label=result.freshness_label,
                is_data_configured=result.is_data_configured,
                missing_fields=result.missing_fields,
                methodology=result.methodology,
            )
        )

    return APIResponse(
        data=WasteCircularityCityResponse(
            city=city,
            wards=scores,
            wards_with_no_data_on_file=wards_with_no_data_on_file,
            methodology=METHODOLOGY,
        )
    )
