from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.gis.operations import GISService
from app.repositories.aqi import AQIReadingRepository, MonitoringStationRepository
from app.schemas.aqi import get_aqi_category
from app.schemas.base import APIResponse

router = APIRouter(prefix="/gis", tags=["GIS Operations"])

_FRESH_READING_SECONDS = 2 * 60 * 60


class StationMapReading(BaseModel):
    aqi: int | None
    aqi_category: str | None
    pm25: float | None
    pm10: float | None
    no2: float | None
    so2: float | None
    co: float | None
    o3: float | None
    timestamp: datetime | None
    quality_flag: str | None
    data_source: Literal["observed", "synthetic", "unavailable"]
    freshness: Literal["fresh", "stale", "unavailable"]


class StationMapPoint(BaseModel):
    station_id: str
    station_code: str
    name: str
    city: str
    ward_id: str | None
    latitude: float
    longitude: float
    is_active: bool
    reading: StationMapReading


@router.get("/stations/map", response_model=APIResponse[list[StationMapPoint]])
async def stations_map(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str | None = Query(None),
    include_inactive: bool = Query(False),
) -> APIResponse[list[StationMapPoint]]:
    repo = MonitoringStationRepository(session)
    if city:
        stations = await repo.get_active_by_city(city)
        if include_inactive:
            all_stations, _ = await repo.get_all(
                skip=0, limit=500, filters={"city": city}
            )
            stations = all_stations
    else:
        stations, _ = await repo.get_all(
            skip=0, limit=500, filters={} if include_inactive else {"is_active": True}
        )

    reading_repo = AQIReadingRepository(session)
    latest = await reading_repo.get_latest_by_stations([s.id for s in stations])
    now = datetime.now(UTC)
    points = []
    for s in stations:
        r = latest.get(s.id)
        if r is None or r.aqi is None and r.pm25 is None:
            reading = StationMapReading(
                aqi=None,
                aqi_category=None,
                pm25=None,
                pm10=None,
                no2=None,
                so2=None,
                co=None,
                o3=None,
                timestamp=r.timestamp if r else None,
                quality_flag=getattr(r, "quality_flag", None),
                data_source="unavailable",
                freshness="unavailable",
            )
        else:
            age = (
                (now - r.timestamp).total_seconds() if r.timestamp is not None else None
            )
            source = "synthetic" if r.quality_flag == "synthetic" else "observed"
            freshness = (
                "fresh"
                if age is not None and age <= _FRESH_READING_SECONDS
                else "stale"
            )
            reading = StationMapReading(
                aqi=r.aqi,
                aqi_category=(
                    get_aqi_category(r.aqi)[0] if r.aqi is not None else None
                ),
                pm25=r.pm25,
                pm10=r.pm10,
                no2=r.no2,
                so2=r.so2,
                co=r.co,
                o3=r.o3,
                timestamp=r.timestamp,
                quality_flag=r.quality_flag,
                data_source=source,
                freshness=freshness,
            )
        points.append(
            StationMapPoint(
                station_id=str(s.id),
                station_code=s.station_code,
                name=s.name,
                city=s.city,
                ward_id=s.ward_id,
                latitude=s.latitude,
                longitude=s.longitude,
                is_active=s.is_active,
                reading=reading,
            )
        )
    return APIResponse(data=points)


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
        text(
            """
        SELECT ea.id, ea.title, ea.ward_id, ea.action_type, ea.priority_score,
               ea.latitude, ea.longitude
        FROM enforcement_actions ea
        WHERE ea.city = :city
          AND ea.status IN ('pending', 'assigned')
          AND ea.latitude IS NOT NULL AND ea.longitude IS NOT NULL
          AND ea.is_deleted = false
        ORDER BY ea.priority_score DESC
        LIMIT 10
    """
        ),
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
    include_synthetic: bool = Query(
        False,
        description="Include synthetic/demo readings; clusters are labelled data_source=synthetic",
    ),
) -> APIResponse[list[dict]]:
    """
    Spatial clustering of monitoring stations currently reporting unhealthy
    AQI (last-hour average) into pollution hotspots.
    """
    svc = GISService(session)
    hotspots = await svc.pollution_hotspots(
        city, radius_km, include_synthetic=include_synthetic
    )
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
