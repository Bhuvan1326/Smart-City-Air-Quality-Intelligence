"""Unit tests for app.services.health_risk.

Deliberately has no dependency on the database fixtures in conftest.py —
`assess_health_risk` is a pure function, so these tests can run in any
environment, including one without PostgreSQL available.
"""

from app.services.health_risk import RiskLevel, assess_health_risk


def test_low_risk_when_all_pollutants_clean():
    result = assess_health_risk(aqi=30, pm25=10, pm10=20, no2=10, co=0.3, o3=20, so2=10)
    assert result.overall_risk == RiskLevel.LOW
    assert all(p.risk_level == RiskLevel.LOW for p in result.pollutant_risks)
    assert result.is_estimate is False


def test_overall_risk_takes_the_worst_pollutant():
    # PM2.5 is very high while everything else is low — overall must reflect
    # the worst individual pollutant, not an average.
    result = assess_health_risk(aqi=60, pm25=150, pm10=20, no2=10, co=0.3, o3=20, so2=10)
    assert result.overall_risk == RiskLevel.VERY_HIGH
    pm25_risk = next(p for p in result.pollutant_risks if p.pollutant == "pm25")
    assert pm25_risk.risk_level == RiskLevel.VERY_HIGH


def test_aqi_alone_can_drive_overall_risk():
    result = assess_health_risk(aqi=285)
    assert result.overall_risk == RiskLevel.VERY_HIGH
    assert result.pollutant_risks == []


def test_partial_data_is_flagged_as_estimate():
    result = assess_health_risk(aqi=100, pm25=40, pm10=None, no2=None, co=None, o3=None, so2=None)
    assert result.is_estimate is True


def test_no_data_defaults_to_low_without_crashing():
    result = assess_health_risk(aqi=None)
    assert result.overall_risk == RiskLevel.LOW
    assert result.pollutant_risks == []


def test_precautions_and_disclaimer_language_present():
    result = assess_health_risk(aqi=310)
    assert len(result.precautions) > 0
    assert "sensitive" in result.sensitive_group_note.lower()


def test_pollutant_risks_sorted_worst_first():
    result = assess_health_risk(aqi=None, pm25=10, no2=200)
    assert result.pollutant_risks[0].pollutant == "no2"
