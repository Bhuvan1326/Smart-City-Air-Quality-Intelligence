"""Unit tests for app.services.industrial_pollution. No DB dependency."""

from app.services.industrial_pollution import DeviationLevel, assess_industrial_zone


def test_no_deviation_when_current_matches_baseline():
    result = assess_industrial_zone(
        source_name="Site A",
        ward_id="W08",
        permit_status="valid",
        violation_count=0,
        current_aqi=100,
        historical_baseline_aqi=95,
    )
    assert result.deviation_level == DeviationLevel.NORMAL
    assert result.status == "normal"


def test_significant_deviation_flagged():
    result = assess_industrial_zone(
        source_name="Yerawada Brick Kiln",
        ward_id="W08",
        permit_status="suspended",
        violation_count=7,
        current_aqi=250,
        historical_baseline_aqi=100,
    )
    assert result.deviation_level == DeviationLevel.SIGNIFICANT
    assert result.status == "environmental_anomaly_detected"


def test_never_confirms_source_only_possible():
    result = assess_industrial_zone(
        source_name="Site B",
        ward_id="W08",
        permit_status="suspended",
        violation_count=5,
        current_aqi=280,
        historical_baseline_aqi=100,
    )
    assert result.possible_contributing_source is True
    assert all("confirmed" not in o.lower() for o in result.supporting_observations)


def test_deviation_without_regulatory_signal_not_flagged_as_source():
    # Elevated AQI relative to baseline, but the site is fully compliant and
    # attribution isn't elevated — should NOT flag as a possible contributing source.
    result = assess_industrial_zone(
        source_name="Compliant Site",
        ward_id="W08",
        permit_status="valid",
        violation_count=0,
        current_aqi=200,
        historical_baseline_aqi=100,
    )
    assert result.deviation_level != DeviationLevel.NORMAL
    assert result.possible_contributing_source is False


def test_no_baseline_data_does_not_crash():
    result = assess_industrial_zone(
        source_name="Site C",
        ward_id=None,
        permit_status="valid",
        violation_count=0,
        current_aqi=120,
        historical_baseline_aqi=None,
    )
    assert result.deviation_level == DeviationLevel.NORMAL
    assert any(
        "no historical baseline" in o.lower() for o in result.supporting_observations
    )


def test_attribution_alone_can_trigger_contributing_source_flag():
    result = assess_industrial_zone(
        source_name="Site D",
        ward_id="W08",
        permit_status="valid",
        violation_count=0,
        current_aqi=200,
        historical_baseline_aqi=100,
        industrial_attribution_pct=45,
    )
    assert result.possible_contributing_source is True
