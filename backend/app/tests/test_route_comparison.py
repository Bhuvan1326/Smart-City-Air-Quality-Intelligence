"""Unit tests for app.services.route_comparison. No DB dependency."""

from datetime import UTC, datetime, timedelta

from app.models.monitoring import AQIReading, MonitoringStation, QualityFlag
from app.services.route_comparison import (RouteCandidate, Waypoint,
                                           compare_routes)


def _station(name: str, lat: float, lon: float) -> MonitoringStation:
    return MonitoringStation(
        name=name,
        station_code=name.upper(),
        city="Pune",
        ward_id="W01",
        operator="Test",
        latitude=lat,
        longitude=lon,
    )


def _reading(aqi: int) -> AQIReading:
    return AQIReading(
        aqi=aqi,
        timestamp=datetime.now(UTC) - timedelta(minutes=5),
        quality_flag=QualityFlag.GOOD,
    )


def test_recommends_lower_exposure_route():
    stations = [
        (_station("Clean Station", 18.55, 73.90), _reading(40)),
        (_station("Dirty Station", 18.50, 73.80), _reading(250)),
    ]
    route_a = RouteCandidate(
        name="Route A", waypoints=[Waypoint(18.50, 73.80), Waypoint(18.505, 73.805)]
    )
    route_b = RouteCandidate(
        name="Route B", waypoints=[Waypoint(18.55, 73.90), Waypoint(18.555, 73.905)]
    )

    result = compare_routes([route_a, route_b], stations)
    assert result.recommended_route_name == "Route B"
    assert "Route B" in result.recommendation_text
    assert "lowest estimated" in result.recommendation_text.lower()


def test_distance_is_real_geometric_calculation():
    stations = [(_station("S", 18.50, 73.80), _reading(50))]
    route = RouteCandidate(
        name="R", waypoints=[Waypoint(18.50, 73.80), Waypoint(18.51, 73.81)]
    )
    result = compare_routes([route], stations)
    assert result.routes[0].total_distance_km > 0


def test_duration_only_present_when_caller_supplies_it():
    stations = [(_station("S", 18.50, 73.80), _reading(50))]
    with_duration = RouteCandidate(
        name="R1",
        waypoints=[Waypoint(18.50, 73.80), Waypoint(18.51, 73.81)],
        duration_minutes=22.0,
    )
    without_duration = RouteCandidate(
        name="R2", waypoints=[Waypoint(18.50, 73.80), Waypoint(18.51, 73.81)]
    )
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
    route = RouteCandidate(
        name="Only Route", waypoints=[Waypoint(18.50, 73.80), Waypoint(18.51, 73.81)]
    )
    result = compare_routes([route], stations)
    assert result.recommended_route_name == "Only Route"
    assert "only route" in result.recommendation_text.lower()


def test_never_fabricates_route_geometry_beyond_supplied_waypoints():
    # A 3-waypoint path (via-point) should route sampling strictly along
    # those segments, not invent a shortcut between endpoints.
    stations = [(_station("S", 18.52, 73.85), _reading(70))]
    route = RouteCandidate(
        name="Via Route",
        waypoints=[
            Waypoint(18.50, 73.80),
            Waypoint(18.55, 73.90),
            Waypoint(18.60, 73.95),
        ],
    )
    result = compare_routes([route], stations)
    # Distance should be sum of both segments, not the direct endpoint-to-endpoint distance.
    from app.utils.geo import haversine_km

    direct = haversine_km(18.50, 73.80, 18.60, 73.95)
    assert result.routes[0].total_distance_km > direct


def test_co2_estimate_scales_with_distance_and_is_never_negative():
    stations = [(_station("S", 18.50, 73.80), _reading(50))]
    short_route = RouteCandidate(
        name="Short", waypoints=[Waypoint(18.50, 73.80), Waypoint(18.505, 73.805)]
    )
    long_route = RouteCandidate(
        name="Long", waypoints=[Waypoint(18.50, 73.80), Waypoint(18.70, 74.00)]
    )
    result = compare_routes([short_route, long_route], stations)
    short_co2 = next(r for r in result.routes if r.name == "Short").estimated_co2_kg
    long_co2 = next(r for r in result.routes if r.name == "Long").estimated_co2_kg
    assert short_co2 is not None and short_co2 >= 0
    assert long_co2 > short_co2


def test_traffic_level_is_never_labeled_live():
    stations = [(_station("S", 18.50, 73.80), _reading(50))]
    route = RouteCandidate(
        name="R", waypoints=[Waypoint(18.50, 73.80), Waypoint(18.51, 73.81)]
    )
    result = compare_routes([route], stations)
    assert result.routes[0].traffic_data_source in ("demo", "csv")
    assert result.traffic_disclaimer  # discloses no live provider


def test_lowest_co2_route_name_picks_shorter_route():
    stations = [(_station("S", 18.50, 73.80), _reading(50))]
    short_route = RouteCandidate(
        name="Short", waypoints=[Waypoint(18.50, 73.80), Waypoint(18.505, 73.805)]
    )
    long_route = RouteCandidate(
        name="Long", waypoints=[Waypoint(18.50, 73.80), Waypoint(18.70, 74.00)]
    )
    result = compare_routes([short_route, long_route], stations)
    assert result.lowest_co2_route_name == "Short"


def test_fastest_route_only_reported_when_all_routes_have_duration():
    stations = [(_station("S", 18.50, 73.80), _reading(50))]
    with_duration = RouteCandidate(
        name="R1",
        waypoints=[Waypoint(18.50, 73.80), Waypoint(18.51, 73.81)],
        duration_minutes=10.0,
    )
    without_duration = RouteCandidate(
        name="R2", waypoints=[Waypoint(18.50, 73.80), Waypoint(18.51, 73.81)]
    )
    mixed_result = compare_routes([with_duration, without_duration], stations)
    assert mixed_result.fastest_route_name is None

    faster = RouteCandidate(
        name="Faster",
        waypoints=[Waypoint(18.50, 73.80), Waypoint(18.51, 73.81)],
        duration_minutes=8.0,
    )
    slower = RouteCandidate(
        name="Slower",
        waypoints=[Waypoint(18.50, 73.80), Waypoint(18.51, 73.81)],
        duration_minutes=20.0,
    )
    full_result = compare_routes([faster, slower], stations)
    assert full_result.fastest_route_name == "Faster"


def test_balanced_route_requires_all_criteria_present():
    stations = [(_station("S", 18.50, 73.80), _reading(50))]
    r1 = RouteCandidate(
        name="R1",
        waypoints=[Waypoint(18.50, 73.80), Waypoint(18.505, 73.805)],
        duration_minutes=10.0,
    )
    r2 = RouteCandidate(
        name="R2",
        waypoints=[Waypoint(18.50, 73.80), Waypoint(18.70, 74.00)],
        duration_minutes=25.0,
    )
    result = compare_routes([r1, r2], stations)
    assert result.balanced_route_name in ("R1", "R2")

    # Without duration on every route, balanced falls back to exposure+CO2 only
    # but never crashes or fabricates a winner from missing data.
    r3 = RouteCandidate(
        name="R3", waypoints=[Waypoint(18.50, 73.80), Waypoint(18.505, 73.805)]
    )
    partial_result = compare_routes([r1, r3], stations)
    assert partial_result.balanced_route_name in ("R1", "R3")
