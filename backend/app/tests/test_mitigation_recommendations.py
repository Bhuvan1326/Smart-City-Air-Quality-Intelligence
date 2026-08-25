"""Unit tests for app.services.mitigation_recommendations. Pure logic, no DB."""

from app.services.health_risk import RiskLevel
from app.services.mitigation_recommendations import generate_recommendation


def test_vehicular_dominant_source_recommends_traffic_actions():
    rec = generate_recommendation(aqi=182, pm25=95, vehicular_pct=55, construction_pct=10)
    targets = {a.target_source for a in rec.recommended_actions}
    assert "vehicular" in targets
    assert "construction" not in targets  # below threshold, correctly excluded


def test_construction_dominant_source_recommends_dust_suppression():
    rec = generate_recommendation(aqi=170, pm10=220, construction_pct=45)
    labels = [a.action for a in rec.recommended_actions]
    assert any("dust" in label.lower() for label in labels)


def test_multiple_sources_ranked_by_contribution_share():
    rec = generate_recommendation(aqi=200, pm25=110, vehicular_pct=25, industrial_pct=50)
    # Industrial (50%) contributes more than vehicular (25%) — its action should come first.
    assert rec.recommended_actions[0].target_source == "industrial"


def test_low_wind_speed_flagged_as_contributing_factor():
    rec = generate_recommendation(aqi=150, pm25=80, wind_speed_mps=1.2)
    assert any("wind" in f.lower() for f in rec.contributing_factors)


def test_no_dominant_source_but_high_risk_gives_advisory_not_empty_list():
    rec = generate_recommendation(aqi=310, pm25=200)
    assert rec.overall_risk == RiskLevel.VERY_HIGH
    assert len(rec.recommended_actions) >= 1
    assert rec.recommended_actions[0].target_source == "unknown"


def test_never_states_a_reduction_percentage_in_disclaimer():
    rec = generate_recommendation(aqi=180, pm25=90, vehicular_pct=60)
    assert "%" not in rec.impact_disclaimer
    assert "simulator" in rec.impact_disclaimer.lower()


def test_actions_carry_real_simulation_scenario_keys_where_applicable():
    rec = generate_recommendation(aqi=180, pm25=90, vehicular_pct=60)
    scenario_keys = {a.simulation_scenario_key for a in rec.recommended_actions}
    assert "restrict_truck_traffic" in scenario_keys or "odd_even_vehicles" in scenario_keys


def test_low_attribution_share_not_treated_as_contributing_factor():
    rec = generate_recommendation(aqi=90, pm25=40, vehicular_pct=5, industrial_pct=5)
    assert rec.contributing_factors == [] or all("wind" in f.lower() for f in rec.contributing_factors)
    assert rec.recommended_actions == []
