from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.gis.operations import GISService
from app.schemas.base import APIResponse

router = APIRouter(prefix="/gis", tags=["GIS Operations"])


@router.get("/ward-boundaries", response_model=APIResponse[dict])
async def get_ward_boundaries(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[dict]:
    """Return GeoJSON FeatureCollection of ward boundaries for a city."""
    svc = GISService(session)
    geojson = await svc.get_ward_boundaries(city)
    return APIResponse(data=geojson)


@router.get("/buffer-analysis", response_model=APIResponse[dict])
async def buffer_analysis(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(default=2.0, ge=0.1, le=50.0),
) -> APIResponse[dict]:
    """Find all emission sources and stations within radius_km of a point."""
    svc = GISService(session)
    result = await svc.buffer_analysis(latitude, longitude, radius_km)
    return APIResponse(data=result)


@router.get("/nearest-stations", response_model=APIResponse[list[dict]])
async def nearest_stations(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    latitude: float = Query(...),
    longitude: float = Query(...),
    limit: int = Query(default=5, ge=1, le=20),
) -> APIResponse[list[dict]]:
    """Find nearest monitoring stations to a point."""
    svc = GISService(session)
    stations = await svc.nearest_stations(latitude, longitude, limit)
    return APIResponse(data=stations)


@router.get("/route-optimise", response_model=APIResponse[dict])
async def optimise_route(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    officer_lat: float = Query(...),
    officer_lon: float = Query(...),
    city: str = Query(default="Pune"),
) -> APIResponse[dict]:
    """
    Generate optimised inspection route for an officer based on active
    high-priority enforcement actions in the city.
    """
    from sqlalchemy import text

    # Build waypoints from pending high-priority actions
    result = await session.execute(
        text("""
        SELECT ea.id, ea.title, ea.ward_id, ea.action_type, ea.priority_score,
               ea.latitude, ea.longitude
        FROM enforcement_actions ea
        WHERE ea.city = :city
          AND ea.status IN ('pending', 'assigned')
          AND ea.latitude IS NOT NULL AND ea.longitude IS NOT NULL
          AND ea.is_deleted = false
        ORDER BY ea.priority_score DESC
        LIMIT 10
    """),
        {"city": city},
    )
    actions = [dict(row._mapping) for row in result]

    if not actions:
        return APIResponse(
            data={
                "waypoints": [],
                "total_distance_km": 0,
                "estimated_duration_min": 0,
                "message": "No pending actions with coordinates to route.",
            },
        )

    waypoints = [
        {
            "id": str(a["id"]),
            "name": a["title"],
            "ward_id": a["ward_id"],
            "latitude": float(a["latitude"]),
            "longitude": float(a["longitude"]),
            "priority": float(a["priority_score"] or 0),
            "action_type": a["action_type"],
        }
        for a in actions
    ]

    svc = GISService(session)
    route = await svc.optimise_officer_route(officer_lat, officer_lon, waypoints, city)
    return APIResponse(data=route)


@router.get("/hotspot-clusters", response_model=APIResponse[list[dict]])
async def hotspot_clusters(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
    radius_km: float = Query(default=2.0, ge=0.5, le=10.0),
) -> APIResponse[list[dict]]:
    """Spatial clustering of high-violation emission sources."""
    svc = GISService(session)
    clusters = await svc.spatial_cluster_hotspots(city, radius_km)
    return APIResponse(data=clusters)


@router.get("/pollution-hotspots", response_model=APIResponse[list[dict]])
async def pollution_hotspots(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
    radius_km: float = Query(default=1.5, ge=0.2, le=10.0),
) -> APIResponse[list[dict]]:
    """
    Spatial clustering of monitoring stations currently reporting unhealthy
    AQI (last-hour average) into pollution hotspots.
    """
    svc = GISService(session)
    hotspots = await svc.pollution_hotspots(city, radius_km)
    return APIResponse(data=hotspots)


@router.get("/geofence-check", response_model=APIResponse[dict])
async def geofence_check(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    latitude: float = Query(...),
    longitude: float = Query(...),
    ward_id: str = Query(...),
    city: str = Query(default="Pune"),
) -> APIResponse[dict]:
    """Check whether a GPS coordinate falls within a specific ward boundary."""
    svc = GISService(session)
    result = await svc.geofence_check(latitude, longitude, ward_id, city)
    return APIResponse(data=result)
