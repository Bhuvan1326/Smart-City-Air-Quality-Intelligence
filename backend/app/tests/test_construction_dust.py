"""Unit tests for app.services.construction_dust. No DB dependency."""

from app.services.construction_dust import DustRiskLevel, assess_construction_dust_risk


def test_low_pm10_and_valid_permit_gives_low_risk():
    result = assess_construction_dust_risk(
        source_name="Wakad Metro Construction",
        source_type="construction",
        ward_id="W06",
        permit_status="valid",
        violation_count=0,
        nearest_station_name="Wakad Station",
        nearest_station_distance_km=0.8,
        pm10=40,
    )
    assert result.risk_level == DustRiskLevel.LOW


def test_elevated_pm10_flags_as_supporting_observation():
    result = assess_construction_dust_risk(
        source_name="Site A",
        source_type="construction",
        ward_id="W06",
        permit_status="valid",
        violation_count=0,
        nearest_station_name="Station A",
        nearest_station_distance_km=1.0,
        pm10=180,
    )
    assert result.risk_level == DustRiskLevel.HIGH
    assert any("Elevated PM10" in o for o in result.supporting_observations)


def test_never_claims_confirmed_source():
    result = assess_construction_dust_risk(
        source_name="Site B",
        source_type="construction",
        ward_id="W06",
        permit_status="none",
        violation_count=5,
        nearest_station_name="Station B",
        nearest_station_distance_km=0.5,
        pm10=200,
    )
    assert result.requires_verification is True
    assert all("confirmed" not in o.lower() for o in result.supporting_observations)


def test_multiple_weak_signals_escalate_moderate_to_high():
    result = assess_construction_dust_risk(
        source_name="Site C",
        source_type="construction",
        ward_id="W06",
        permit_status="expired",
        violation_count=2,
        nearest_station_name="Station C",
        nearest_station_distance_km=1.0,
        pm10=90,  # moderate band
        construction_attribution_pct=35,
    )
    assert result.risk_level == DustRiskLevel.HIGH


def test_no_pm10_data_does_not_crash_or_fabricate():
    result = assess_construction_dust_risk(
        source_name="Site D",
        source_type="dust",
        ward_id=None,
        permit_status="valid",
        violation_count=0,
        nearest_station_name=None,
        nearest_station_distance_km=None,
        pm10=None,
    )
    assert result.pm10 is None
    assert result.risk_level == DustRiskLevel.LOW
    assert any("no recent pm10" in o.lower() for o in result.supporting_observations)


def test_far_station_flagged_as_caveat():
    result = assess_construction_dust_risk(
        source_name="Site E",
        source_type="construction",
        ward_id="W06",
        permit_status="valid",
        violation_count=0,
        nearest_station_name="Far Station",
        nearest_station_distance_km=5.5,
        pm10=60,
    )
    assert any("km away" in o for o in result.supporting_observations)
