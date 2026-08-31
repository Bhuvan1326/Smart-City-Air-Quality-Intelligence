from app.services.route_comparison import RouteComparisonResult


def test_route_comparison_result_does_not_require_traffic_disclaimer():
    """The result contract must not require a non-existent disclaimer field.

    ``traffic_disclaimer`` is not a field on ``RouteComparisonResult``.
    Provenance should be represented by the fields exposed by the result
    model rather than by accessing an undeclared attribute.
    """
    fields = getattr(RouteComparisonResult, "model_fields", {})

    assert "traffic_disclaimer" not in fields


def test_traffic_level_is_not_labeled_live_by_a_disclaimer_field():
    """A route result must not expose a fake ``traffic_disclaimer`` field."""
    result = RouteComparisonResult.model_construct()

    assert not hasattr(result, "traffic_disclaimer")
