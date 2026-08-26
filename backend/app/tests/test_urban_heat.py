"""Unit tests for app.services.urban_heat. Pure calculation, no DB/network."""

from datetime import UTC, date, datetime

from app.services.urban_heat import HeatRiskLevel, assess_heat_risk


def _now():
    return datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


def test_low_temperature_is_low_risk_without_vegetation_data():
    result = assess_heat_risk(
        latitude=18.52,
        longitude=73.85,
        air_temperature_c=24.0,
        air_temperature_observed_at=_now(),
    )
    assert result.heat_risk == HeatRiskLevel.LOW
    assert result.base_risk_from_temperature == HeatRiskLevel.LOW
    assert result.vegetation_data_available is False
    assert result.escalated_for_low_vegetation is False
    assert result.cooling_priority is False


def test_high_temperature_is_high_risk():
    result = assess_heat_risk(
        latitude=18.52,
        longitude=73.85,
        air_temperature_c=38.0,
        air_temperature_observed_at=_now(),
    )
    assert result.heat_risk == HeatRiskLevel.HIGH
    assert result.cooling_priority is True


def test_severe_temperature_is_severe_risk():
    result = assess_heat_risk(
        latitude=18.52,
        longitude=73.85,
        air_temperature_c=42.0,
        air_temperature_observed_at=_now(),
    )
    assert result.heat_risk == HeatRiskLevel.SEVERE


def test_low_ndvi_escalates_risk_one_band():
    without_veg = assess_heat_risk(
        latitude=18.52,
        longitude=73.85,
        air_temperature_c=32.0,
        air_temperature_observed_at=_now(),
    )
    assert without_veg.heat_risk == HeatRiskLevel.MODERATE

    with_low_veg = assess_heat_risk(
        latitude=18.52,
        longitude=73.85,
        air_temperature_c=32.0,
        air_temperature_observed_at=_now(),
        mean_ndvi=0.05,
        ndvi_observed_date=date(2026, 8, 10),
    )
    assert with_low_veg.heat_risk == HeatRiskLevel.HIGH
    assert with_low_veg.escalated_for_low_vegetation is True
    assert with_low_veg.vegetation_data_available is True


def test_healthy_ndvi_does_not_escalate():
    result = assess_heat_risk(
        latitude=18.52,
        longitude=73.85,
        air_temperature_c=32.0,
        air_temperature_observed_at=_now(),
        mean_ndvi=0.55,
        ndvi_observed_date=date(2026, 8, 10),
    )
    assert result.heat_risk == HeatRiskLevel.MODERATE
    assert result.escalated_for_low_vegetation is False


def test_severe_risk_does_not_escalate_beyond_severe():
    result = assess_heat_risk(
        latitude=18.52,
        longitude=73.85,
        air_temperature_c=44.0,
        air_temperature_observed_at=_now(),
        mean_ndvi=0.05,
        ndvi_observed_date=date(2026, 8, 10),
    )
    assert result.heat_risk == HeatRiskLevel.SEVERE


def test_rationale_and_methodology_always_present():
    result = assess_heat_risk(
        latitude=18.52,
        longitude=73.85,
        air_temperature_c=28.0,
        air_temperature_observed_at=_now(),
    )
    assert len(result.rationale) >= 1
    assert "not measured" in result.methodology.lower()
