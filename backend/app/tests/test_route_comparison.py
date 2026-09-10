from app.core.config import settings
from app.services.route_comparison import (
    RouteCandidate,
    RouteComparisonResult,
    Waypoint,
    compare_routes,
)


def test_route_comparison_result_does_not_require_traffic_disclaimer():
    fields = getattr(RouteComparisonResult, "__dataclass_fields__", {})

    assert "traffic_disclaimer" not in fields


def test_route_comparison_result_has_no_traffic_disclaimer_attribute():
    """A constructed route-comparison result must not expose a fake
    ``traffic_disclaimer`` attribute.
    """
    result = RouteComparisonResult(
        routes=[],
        recommended_route_name=None,
        recommendation_text="No AQI data available along any route to make a recommendation.",
    )

    assert not hasattr(result, "traffic_disclaimer")


def test_compare_routes_does_not_crash_when_traffic_unavailable():
    original = settings.TRAFFIC_PROVIDER
    settings.TRAFFIC_PROVIDER = ""
    try:
        routes = [
            RouteCandidate(
                name="Route A",
                waypoints=[
                    Waypoint(latitude=18.52, longitude=73.85),
                    Waypoint(latitude=18.53, longitude=73.86),
                ],
            )
        ]
        result = compare_routes(routes, stations_with_readings=[])
        assert result.routes[0].traffic_level is None
        assert result.routes[0].traffic_data_source == "unavailable"
        assert result.routes[0].estimated_co2_kg is not None
    finally:
        settings.TRAFFIC_PROVIDER = original


def test_compare_routes_uses_demo_traffic_when_explicitly_configured():
    original = settings.TRAFFIC_PROVIDER
    settings.TRAFFIC_PROVIDER = "demo"
    try:
        routes = [
            RouteCandidate(
                name="Route A",
                waypoints=[
                    Waypoint(latitude=18.52, longitude=73.85),
                    Waypoint(latitude=18.53, longitude=73.86),
                ],
            )
        ]
        result = compare_routes(routes, stations_with_readings=[])
        assert result.routes[0].traffic_level is not None
        assert result.routes[0].traffic_data_source == "demo"
    finally:
        settings.TRAFFIC_PROVIDER = original
