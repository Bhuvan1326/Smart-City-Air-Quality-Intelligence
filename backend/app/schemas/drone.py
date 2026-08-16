from uuid import UUID

from app.schemas.base import BaseSchema


class NoFlyZoneInput(BaseSchema):
    center_latitude: float
    center_longitude: float
    radius_meters: float


class DroneFlightPlanRequest(BaseSchema):
    hotspot_id: str
    city: str
    ward_id: str | None = None
    min_latitude: float
    min_longitude: float
    max_latitude: float
    max_longitude: float
    launch_latitude: float | None = None
    launch_longitude: float | None = None
    no_fly_zones: list[NoFlyZoneInput] = []
    swath_meters: float | None = None
    max_flight_minutes: float | None = None
    cruise_speed_mps: float | None = None


class DroneFlightPlanResponse(BaseSchema):
    id: UUID
    hotspot_id: str
    city: str
    ward_id: str | None
    launch_latitude: float
    launch_longitude: float
    total_sorties: int
    total_waypoints: int
    total_distance_meters: float
    coverage_area_sq_meters: float
    excluded_no_fly_zones: int
    reasoning: list[str] | None
    status: str
