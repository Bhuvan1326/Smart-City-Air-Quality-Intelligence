from datetime import UTC, datetime
from typing import Annotated

from app.api.deps import CurrentUser, get_db
from app.schemas.base import APIResponse
from app.services.whatif_simulator import WhatIfSimulator
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/simulator", tags=["What-if Simulator"])


class SimulationRequest(BaseModel):
    city: str = "Pune"
    scenario: str
    ward_id: str | None = None
    custom_reduction_pct: float | None = Field(None, ge=0.0, le=1.0)
    custom_reductions: dict[str, float] | None = Field(
        None,
        description="Per-source reduction fractions for the 'policy_bundle' scenario, e.g. {'vehicular': 0.3, 'industrial': 0.5}",
    )
    weather_wind_speed_mps: float | None = Field(
        None,
        ge=0.1,
        le=30.0,
        description="Hypothetical wind speed for the 'weather_shift' scenario",
    )


class SimulationResponse(BaseModel):
    scenario: str
    baseline_aqi: float
    simulated_aqi: float
    aqi_delta: float
    pm25_delta: float
    confidence: float
    affected_wards: list[str]
    co2_impact_kg_day: float
    time_to_effect_hours: int
    reasoning: str
    dispersion_map: list[dict]
    impact_score: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    secondary_effects: list[dict]


@router.get("/scenarios", response_model=APIResponse[list[dict]])
async def list_scenarios(current_user: CurrentUser) -> APIResponse[list[dict]]:
    """List all available what-if scenarios with parameters."""
    sim = WhatIfSimulator(None)  # type: ignore
    scenarios = await sim.list_scenarios()
    return APIResponse(data=scenarios)


@router.post("/whatif", response_model=APIResponse[SimulationResponse])
async def run_whatif(
    request: SimulationRequest,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[SimulationResponse]:
    """
    Run a what-if simulation for a given scenario and city.

    Scenarios: close_construction_site, restrict_truck_traffic, shutdown_industrial_unit,
               odd_even_vehicles, dust_suppression, ban_biomass_burning
    """
    sim = WhatIfSimulator(session)
    try:
        result = await sim.simulate(
            city=request.city,
            scenario_key=request.scenario,
            ward_id=request.ward_id,
            custom_reduction_pct=request.custom_reduction_pct,
            custom_reductions=request.custom_reductions,
            weather_wind_speed_mps=request.weather_wind_speed_mps,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e

    return APIResponse(
        data=SimulationResponse(
            scenario=result.scenario,
            baseline_aqi=result.baseline_aqi,
            simulated_aqi=result.simulated_aqi,
            aqi_delta=result.aqi_delta,
            pm25_delta=result.pm25_delta,
            confidence=result.confidence,
            affected_wards=result.affected_wards,
            co2_impact_kg_day=result.co2_impact_kg_day,
            time_to_effect_hours=result.time_to_effect_hours,
            reasoning=result.reasoning,
            dispersion_map=result.dispersion_map,
            impact_score=result.impact_score,
            confidence_interval_lower=result.confidence_interval_lower,
            confidence_interval_upper=result.confidence_interval_upper,
            secondary_effects=result.secondary_effects,
        )
    )


@router.get("/twin/dispersion", response_model=APIResponse[dict])
async def digital_twin_dispersion(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
    ward_id: str = Query(default="W07"),
    wind_speed: float = Query(default=3.0, ge=0.1, le=30.0),
    wind_direction: float = Query(default=225.0, ge=0.0, le=360.0),
    emission_rate_kg_hr: float = Query(default=50.0, ge=1.0, le=5000.0),
) -> APIResponse[dict]:
    """
    AI Digital Twin: simulate Gaussian plume dispersion from a source.
    Returns a spatial grid of estimated AQI contribution at each point.

    Uses the real Pasquill-Gifford stability classification and Briggs
    dispersion coefficients from app.services.dispersion (classified from
    the given wind speed and current time of day) rather than a hardcoded
    stability class C, so the plume shape actually responds to conditions —
    a calm night gives a narrow, slow-dispersing plume; a windy midday
    gives a wide, fast-dispersing one.
    """
    import math

    from app.gis.operations import PUNE_WARD_BOUNDARIES
    from app.services.dispersion import (classify_stability,
                                         gaussian_plume_concentration,
                                         plume_spread)

    meta = PUNE_WARD_BOUNDARIES.get(
        ward_id, {"center": [73.85, 18.52], "name": ward_id}
    )
    cx, cy = meta["center"]
    wind_dir_rad = math.radians(wind_direction)

    current_hour = datetime.now(UTC).hour
    stability = classify_stability(wind_speed, current_hour)
    u = max(wind_speed, 0.5)
    H = 20.0  # effective stack height (m)

    grid_points = []
    for di in range(-5, 6):
        for dj in range(-5, 6):
            lon = cx + di * 0.008
            lat = cy + dj * 0.008
            # Distance from source in km
            x_km = di * 0.008 * 111.32 * math.cos(math.radians(cy))
            y_km = dj * 0.008 * 110.54

            # Wind-axis projection
            wind_x = math.cos(wind_dir_rad)
            wind_y = math.sin(wind_dir_rad)
            along_wind_m = (x_km * wind_x + y_km * wind_y) * 1000
            cross_wind_m = abs(-x_km * wind_y + y_km * wind_x) * 1000

            if along_wind_m <= 0:
                concentration = 0.0
            else:
                _sigma_y, sigma_z = plume_spread(along_wind_m, stability)
                ground_term = math.exp(
                    -0.5 * (H / sigma_z) ** 2
                )  # elevated-source ground-level factor
                concentration = (
                    gaussian_plume_concentration(
                        along_wind_m,
                        cross_wind_m,
                        u,
                        stability,
                        source_strength=emission_rate_kg_hr,
                    )
                    * ground_term
                )
                concentration = min(concentration * 1e6, 500)  # μg/m³ cap

            aqi_contribution = min(500, int(concentration * 0.8))
            grid_points.append(
                {
                    "latitude": round(lat, 6),
                    "longitude": round(lon, 6),
                    "concentration_ug_m3": round(concentration, 2),
                    "aqi_contribution": aqi_contribution,
                }
            )

    return APIResponse(
        data={
            "source": {
                "ward_id": ward_id,
                "latitude": cy,
                "longitude": cx,
                "name": meta.get("name"),
            },
            "parameters": {
                "wind_speed_ms": wind_speed,
                "wind_direction_deg": wind_direction,
                "emission_rate_kg_hr": emission_rate_kg_hr,
                "effective_stack_height_m": H,
                "stability_class": stability.value,
                "model": "gaussian_plume_pasquill_gifford",
            },
            "grid_points": grid_points,
            "city": city,
            "generated_at": datetime.now(UTC).isoformat(),
        }
    )
