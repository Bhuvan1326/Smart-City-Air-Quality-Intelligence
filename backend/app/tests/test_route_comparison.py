from app.services.route_comparison import RouteComparisonResult


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
