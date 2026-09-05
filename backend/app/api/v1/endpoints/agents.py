from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, RequireAnalyst, get_db
from app.schemas.base import APIResponse

router = APIRouter(prefix="/agents", tags=["AI Agents"], dependencies=[RequireAnalyst])


@router.post("/run", response_model=APIResponse[dict])
async def run_agent_pipeline(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
    ward_id: str | None = Query(default=None),
    query: str = Query(default=""),
    agents: list[str] = Query(
        default=[
            "ingestion",
            "forecast",
            "attribution",
            "enforcement",
            "advisory",
            "policy",
        ]
    ),
) -> APIResponse[dict]:
    """
    Execute the full LangGraph multi-agent pipeline or a subset of agents.
    Returns aggregated state from all agents with confidence scores and reasoning.

    Available agents: ingestion, forecast, attribution, enforcement, advisory, policy
    """
    from app.agents.langgraph_agents import AirQualityOrchestrator

    orchestrator = AirQualityOrchestrator(session)
    result = await orchestrator.run(
        city=city,
        query=query,
        ward_id=ward_id,
        user_role=current_user.role.value,
        agents_to_run=agents,
    )
    return APIResponse(data=result)


@router.post("/run-graph", response_model=APIResponse[dict])
async def run_agent_pipeline_langgraph(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
    ward_id: str | None = Query(default=None),
    query: str = Query(default=""),
) -> APIResponse[dict]:
    """
    Execute the agent pipeline via a real langgraph.graph.StateGraph
    (see app.agents.graph_orchestrator.LangGraphOrchestrator) rather than
    the hand-rolled sequential orchestrator behind /run. Functionally
    additive — /run is unchanged and remains the default — this endpoint
    also adds a genuine CrewAI Investigation Crew node that autonomously
    corroborates low-confidence Attribution Agent findings (requires
    ANTHROPIC_API_KEY; degrades gracefully to a no-op when unset, like
    every other optional integration in this codebase).

    Always runs the full pipeline (ingestion, forecast, attribution,
    investigation, enforcement, advisory, policy) — unlike /run, individual
    agent selection isn't supported here since the graph's edges encode
    real dependencies between agents, not an arbitrary subset.
    """
    from app.agents.graph_orchestrator import LangGraphOrchestrator

    orchestrator = LangGraphOrchestrator(session)
    result = await orchestrator.run(
        city=city,
        query=query,
        ward_id=ward_id,
        user_role=current_user.role.value,
    )
    return APIResponse(data=result)


@router.get("/status", response_model=APIResponse[dict])
async def get_agent_status(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[dict]:
    """
    Get the latest execution status of each agent for a city.
    Uses recent data timestamps as health indicators.
    """
    from sqlalchemy import text

    # Check data freshness per agent
    aqi_age = await session.scalar(
        text(
            """
        SELECT EXTRACT(EPOCH FROM (NOW() - MAX(r.timestamp))) / 60
        FROM aqi_readings r
        JOIN monitoring_stations s ON r.station_id = s.id
        WHERE s.city = :city AND r.is_deleted = false
    """
        ),
        {"city": city},
    )

    forecast_age = await session.scalar(
        text(
            """
        SELECT EXTRACT(EPOCH FROM (NOW() - MAX(generated_at))) / 60
        FROM forecast_grids WHERE city = :city AND is_deleted = false
    """
        ),
        {"city": city},
    )

    attribution_age = await session.scalar(
        text(
            """
        SELECT EXTRACT(EPOCH FROM (NOW() - MAX(timestamp))) / 60
        FROM pollution_attributions WHERE city = :city AND is_deleted = false
    """
        ),
        {"city": city},
    )

    anomaly_count = await session.scalar(
        text(
            """
        SELECT COUNT(*) FROM anomaly_events
        WHERE city = :city AND is_resolved = false AND is_deleted = false
        AND detected_at > NOW() - INTERVAL '24 hours'
    """
        ),
        {"city": city},
    )

    def status_from_age(age_min: float | None) -> str:
        if age_min is None:
            return "no_data"
        if age_min < 10:
            return "healthy"
        if age_min < 60:
            return "stale"
        return "degraded"

    return APIResponse(
        data={
            "city": city,
            "agents": {
                "data_ingestion": {
                    "status": status_from_age(aqi_age),
                    "last_run_min_ago": round(aqi_age or 0, 1),
                    "schedule": "every 5 minutes",
                },
                "forecast": {
                    "status": status_from_age(forecast_age),
                    "last_run_min_ago": round(forecast_age or 0, 1),
                    "schedule": "every hour",
                },
                "attribution": {
                    "status": status_from_age(attribution_age),
                    "last_run_min_ago": round(attribution_age or 0, 1),
                    "schedule": "every hour",
                },
                "anomaly_detection": {
                    "status": "healthy" if anomaly_count is not None else "no_data",
                    "active_anomalies": int(anomaly_count or 0),
                    "schedule": "every 5 minutes",
                },
                "enforcement": {
                    "status": "healthy",
                    "schedule": "on-demand + enforcement triggers",
                },
                "citizen_advisory": {
                    "status": "healthy",
                    "schedule": "every 5 minutes when AQI > 150",
                },
            },
        }
    )


@router.get("/model-registry", response_model=APIResponse[list[dict]])
async def list_model_versions(current_user: CurrentUser) -> APIResponse[list[dict]]:
    """List all trained ML model versions in the registry."""
    from app.ml.inference import get_model_registry

    registry = get_model_registry()
    models = registry.list_models()
    return APIResponse(
        data=[
            {
                "version": m.version,
                "trained_at": m.trained_at,
                "path": m.path,
                "is_active": m.is_active,
                "feature_names": m.feature_names,
            }
            for m in models
        ]
    )


@router.get("/carbon-estimate", response_model=APIResponse[dict])
async def estimate_carbon(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[dict]:
    """Estimate total CO₂ and PM2.5 from all emission sources in a city."""
    from app.services.carbon_estimator import CarbonEstimatorService

    svc = CarbonEstimatorService(session)
    estimate = await svc.estimate_city_emissions(city)
    return APIResponse(data=estimate)


@router.get("/carbon-estimate/enforcement", response_model=APIResponse[dict])
async def estimate_enforcement_carbon_impact(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    source_type: str = Query(default="industrial"),
    action_type: str = Query(default="shutdown"),
    duration_days: int = Query(default=30, ge=1, le=365),
) -> APIResponse[dict]:
    """Estimate CO₂ and PM2.5 reduction from an enforcement action."""
    from app.services.carbon_estimator import CarbonEstimatorService

    svc = CarbonEstimatorService(session)
    estimate = await svc.estimate_enforcement_impact(
        source_type, action_type, duration_days
    )
    return APIResponse(data=estimate)
