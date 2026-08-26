"""Unit tests for app.services.water_climate. Pure calculation, no DB/network."""

from datetime import UTC, date, datetime

from app.services.water_climate import RiskBand, assess_water_climate


def _now():
    return datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


def test_no_data_at_all_is_fully_unavailable():
    result = assess_water_climate(city="Pune", latitude=18.52, longitude=73.85)
    assert result.weather_available is False
    assert result.municipal_data_available is False
    assert result.flood_conducive_risk is None
    assert result.drought_risk is None
    assert result.water_stress is None


def test_flood_conducive_risk_scales_with_precipitation():
    low = assess_water_climate(
        city="Pune",
        latitude=18.52,
        longitude=73.85,
        precipitation_mm=0.0,
        weather_observed_at=_now(),
        weather_provider="Open-Meteo",
    )
    assert low.flood_conducive_risk == RiskBand.LOW

    moderate = assess_water_climate(
        city="Pune",
        latitude=18.52,
        longitude=73.85,
        precipitation_mm=3.0,
        weather_observed_at=_now(),
        weather_provider="Open-Meteo",
    )
    assert moderate.flood_conducive_risk == RiskBand.MODERATE

    high = assess_water_climate(
        city="Pune",
        latitude=18.52,
        longitude=73.85,
        precipitation_mm=8.0,
        weather_observed_at=_now(),
        weather_provider="Open-Meteo",
    )
    assert high.flood_conducive_risk == RiskBand.HIGH

    severe = assess_water_climate(
        city="Pune",
        latitude=18.52,
        longitude=73.85,
        precipitation_mm=20.0,
        weather_observed_at=_now(),
        weather_provider="Open-Meteo",
    )
    assert severe.flood_conducive_risk == RiskBand.SEVERE


def test_drought_risk_and_water_stress_require_reservoir_data():
    without_reservoir = assess_water_climate(
        city="Pune",
        latitude=18.52,
        longitude=73.85,
        precipitation_mm=0.0,
        weather_observed_at=_now(),
        weather_provider="Open-Meteo",
    )
    assert without_reservoir.drought_risk is None
    assert without_reservoir.water_stress is None

    with_low_reservoir = assess_water_climate(
        city="Pune",
        latitude=18.52,
        longitude=73.85,
        reservoir_level_pct=15.0,
        municipal_data_as_of=date(2026, 6, 1),
    )
    assert with_low_reservoir.drought_risk == RiskBand.SEVERE
    assert with_low_reservoir.water_stress == RiskBand.SEVERE


def test_reservoir_bands_scale_correctly():
    moderate = assess_water_climate(
        city="Pune", latitude=18.52, longitude=73.85, reservoir_level_pct=50.0
    )
    assert moderate.drought_risk == RiskBand.MODERATE

    adequate = assess_water_climate(
        city="Pune", latitude=18.52, longitude=73.85, reservoir_level_pct=80.0
    )
    assert adequate.drought_risk == RiskBand.LOW


def test_no_rainfall_anomaly_field_exists():
    result = assess_water_climate(city="Pune", latitude=18.52, longitude=73.85)
    assert not hasattr(result, "rainfall_anomaly")


def test_rationale_and_methodology_always_present():
    result = assess_water_climate(city="Pune", latitude=18.52, longitude=73.85)
    assert len(result.rationale) >= 1
    assert "no historical climatological normal" in result.methodology.lower()
