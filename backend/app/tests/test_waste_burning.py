"""Unit tests for app.services.waste_burning. No DB dependency."""

from app.services.waste_burning import (WasteBurningConfidence,
                                        assess_waste_burning_risk)


def test_no_signals_gives_none_confidence():
    result = assess_waste_burning_risk(ward_id="W07", current_pm25=30, baseline_pm25=28)
    assert result.confidence == WasteBurningConfidence.NONE
    assert result.circular_economy_recommendations == []


def test_pm25_spike_alone_gives_low_confidence():
    result = assess_waste_burning_risk(
        ward_id="W07", current_pm25=180, baseline_pm25=60
    )
    assert result.confidence == WasteBurningConfidence.LOW
    assert any("sudden pm2.5" in o.lower() for o in result.supporting_observations)


def test_multiple_signals_escalate_confidence():
    result = assess_waste_burning_risk(
        ward_id="W07",
        current_pm25=180,
        baseline_pm25=60,
        nearest_biomass_source_name="Kothrud Residential Burning",
        nearest_biomass_source_distance_km=0.9,
        biomass_attribution_pct=35,
    )
    assert result.confidence == WasteBurningConfidence.HIGH
    assert len(result.supporting_observations) >= 3


def test_status_always_requires_verification():
    result = assess_waste_burning_risk(
        ward_id="W07",
        current_pm25=200,
        baseline_pm25=50,
        satellite_hotspot_nearby=True,
        satellite_configured=True,
    )
    assert result.status == "requires_verification"
    assert "confirmed" not in result.detected.lower()


def test_unconfigured_satellite_labeled_unavailable_not_skipped():
    result = assess_waste_burning_risk(
        ward_id="W07",
        current_pm25=30,
        baseline_pm25=28,
        satellite_hotspot_nearby=False,
        satellite_configured=False,
    )
    assert any("unavailable" in o.lower() for o in result.supporting_observations)


def test_circular_economy_recommendations_present_when_flagged():
    result = assess_waste_burning_risk(
        ward_id="W07", current_pm25=180, baseline_pm25=60
    )
    assert len(result.circular_economy_recommendations) > 0
    assert any("compost" in r.lower() for r in result.circular_economy_recommendations)


def test_no_data_does_not_crash():
    result = assess_waste_burning_risk(
        ward_id=None, current_pm25=None, baseline_pm25=None
    )
    assert result.confidence == WasteBurningConfidence.NONE
