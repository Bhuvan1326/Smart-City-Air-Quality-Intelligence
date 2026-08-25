"""Unit tests for app.services.route_comparison. No DB dependency."""

from datetime import UTC, datetime, timedelta

from app.models.monitoring import AQIReading, MonitoringStation, QualityFlag
from app.services.route_comparison import RouteCandidate, Waypoint, compare_routes


def _station(name: str, lat: float, lon: float) -> MonitoringStation:
    return MonitoringStation(
        name=name, station_code=name.upper(), city="Pune", ward_id="W01",
        operator="Test", latitude=lat, longitude=lon,
    )


def _reading(aqi: int) -> AQIReading:
    return AQIReading(aqi=aqi, timestamp=datetime.now(UTC) - timedelta(minutes=5), quality_flag=QualityFlag.GOOD)


def test_recommends_lower_exposure_route():
    stations = [
        (_station("Clean Station", 18.55, 73.90), _reading(40)),
        (_station("Dirty Station", 18.50, 73.80), _reading(250)),
    ]
    route_a = RouteCandidate(name="Route A", waypoints=[Waypoint(18.50, 73.80), Waypoint(18.505, 73.805)])
    route_b = RouteCandidate(name="Route B", waypoints=[Waypoint(18.55, 73.90), Waypoint(18.555, 73.905)])

    result = compare_routes([route_a, route_b], stations)
    assert result.recommended_route_name == "Route B"
    assert "Route B" in result.recommendation_text
    assert "lowest estimated" in result.recommendation_text.lower()


def test_distance_is_real_geometric_calculation():
    stations = [(_station("S", 18.50, 73.80), _reading(50))]
    route = RouteCandidate(name="R", waypoints=[Waypoint(18.50, 73.80), Waypoint(18.51, 73.81)])
    result = compare_routes([route], stations)
    assert result.routes[0].total_distance_km > 0


def test_duration_only_present_when_caller_supplies_it():
    stations = [(_station("S", 18.50, 73.80), _reading(50))]
    with_duration = RouteCandidate(name="R1", waypoints=[Waypoint(18.50, 73.80), Waypoint(18.51, 73.81)], duration_minutes=22.0)
    without_duration = RouteCandidate(name="R2", waypoints=[Waypoint(18.50, 73.80), Waypoint(18.51, 73.81)])
    result = compare_routes([with_duration, without_duration], stations)
    assert result.routes[0].duration_minutes == 22.0
    assert result.routes[1].duration_minutes is None


def test_no_aqi_data_gives_honest_no_recommendation():
    route = RouteCandidate(name="R", waypoints=[Waypoint(0, 0), Waypoint(1, 1)])
    result = compare_routes([route], stations_with_readings=[])
    assert result.recommended_route_name is None
    assert "no aqi data" in result.recommendation_text.lower()


def test_single_route_with_data_still_reports_result():
    stations = [(_station("S", 18.50, 73.80), _reading(60))]
    route = RouteCandidate(name="Only Route", waypoints=[Waypoint(18.50, 73.80), Waypoint(18.51, 73.81)])
    result = compare_routes([route], stations)
    assert result.recommended_route_name == "Only Route"
    assert "only route" in result.recommendation_text.lower()


def test_never_fabricates_route_geometry_beyond_supplied_waypoints():
    # A 3-waypoint path (via-point) should route sampling strictly along
    # those segments, not invent a shortcut between endpoints.
    stations = [(_station("S", 18.52, 73.85), _reading(70))]
    route = RouteCandidate(
        name="Via Route",
        waypoints=[Waypoint(18.50, 73.80), Waypoint(18.55, 73.90), Waypoint(18.60, 73.95)],
    )
    result = compare_routes([route], stations)
    # Distance should be sum of both segments, not the direct endpoint-to-endpoint distance.
    from app.utils.geo import haversine_km
    direct = haversine_km(18.50, 73.80, 18.60, 73.95)
    assert result.routes[0].total_distance_km > direct
