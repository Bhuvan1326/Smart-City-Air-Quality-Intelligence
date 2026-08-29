from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.models.enforcement import DroneFlightPlan
from app.schemas.base import APIResponse
from app.schemas.drone import DroneFlightPlanRequest, DroneFlightPlanResponse
from app.services.drone_planner import DronePlanner

router = APIRouter(prefix="/drone", tags=["Drone Inspection Planning"])


@router.post("/plan", response_model=APIResponse[DroneFlightPlanResponse])
async def create_flight_plan(
    data: DroneFlightPlanRequest,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[DroneFlightPlanResponse]:
    """Generate (and persist) a coverage flight plan for a pollution hotspot."""
    planner = DronePlanner()
    launch = (
        (data.launch_latitude, data.launch_longitude)
        if data.launch_latitude is not None and data.launch_longitude is not None
        else None
    )
    no_fly = [
        (z.center_latitude, z.center_longitude, z.radius_meters)
        for z in data.no_fly_zones
    ]

    result = planner.plan_coverage(
        data.hotspot_id,
        bbox=(
            data.min_latitude,
            data.min_longitude,
            data.max_latitude,
            data.max_longitude,
        ),
        launch_point=launch,
        no_fly_zones=no_fly,
        swath_meters=data.swath_meters,
        max_flight_minutes=data.max_flight_minutes,
        cruise_speed_mps=data.cruise_speed_mps,
    )

    plan = DroneFlightPlan(
        hotspot_id=data.hotspot_id,
        city=data.city,
        ward_id=data.ward_id,
        launch_latitude=result.launch_point[0],
        launch_longitude=result.launch_point[1],
        total_sorties=len(result.sorties),
        total_waypoints=result.total_waypoints,
        total_distance_meters=result.total_distance_meters,
        coverage_area_sq_meters=result.coverage_area_sq_meters,
        excluded_no_fly_zones=result.excluded_no_fly_zones,
        reasoning=result.reasoning,
        geojson=result.to_geojson(),
        status="planned",
        created_by=current_user.id,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)

    return APIResponse(data=DroneFlightPlanResponse.model_validate(plan))


@router.get("/plans", response_model=APIResponse[list[DroneFlightPlanResponse]])
async def list_flight_plans(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str | None = None,
    limit: int = 50,
) -> APIResponse[list[DroneFlightPlanResponse]]:
    query = (
        select(DroneFlightPlan).order_by(desc(DroneFlightPlan.created_at)).limit(limit)
    )
    if city:
        query = query.where(DroneFlightPlan.city == city)
    plans = (await session.execute(query)).scalars().all()
    return APIResponse(data=[DroneFlightPlanResponse.model_validate(p) for p in plans])


@router.get("/plans/{plan_id}/geojson")
async def get_flight_plan_geojson(
    plan_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Raw GeoJSON FeatureCollection for direct rendering on the frontend map."""
    plan = await session.get(DroneFlightPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Flight plan not found")
    return plan.geojson or {"type": "FeatureCollection", "features": []}
