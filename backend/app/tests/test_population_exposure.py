"""Unit tests for app.services.population_exposure. No DB dependency."""

from app.services.population_exposure import (
    ExposureLevel,
    PopulationBand,
    score_exposure,
)


def test_no_population_data_returns_unavailable_not_a_guess():
    result = score_exposure(ward_id="W06", aqi=250, pm25=140)
    assert result.exposure_level == ExposureLevel.UNAVAILABLE
    assert result.population is None
    assert result.is_population_data_configured is False


def test_high_pollution_high_population_gives_very_high_exposure():
    result = score_exposure(
        ward_id="W06",
        aqi=280,
        pm25=150,
        population=500_000,
        all_city_populations=[50_000, 120_000, 500_000],
    )
    assert result.exposure_level in (ExposureLevel.HIGH, ExposureLevel.VERY_HIGH)
    assert result.population_band == PopulationBand.HIGH


def test_low_pollution_low_population_gives_low_exposure():
    result = score_exposure(
        ward_id="W01",
        aqi=30,
        pm25=10,
        population=10_000,
        all_city_populations=[10_000, 120_000, 500_000],
    )
    assert result.exposure_level == ExposureLevel.LOW


def test_sensitive_sites_nudge_exposure_up():
    base = score_exposure(
        ward_id="W03",
        aqi=180,
        pm25=95,
        population=200_000,
        all_city_populations=[50_000, 120_000, 200_000],
    )
    with_sites = score_exposure(
        ward_id="W03",
        aqi=180,
        pm25=95,
        population=200_000,
        sensitive_sites_count=5,
        all_city_populations=[50_000, 120_000, 200_000],
    )
    ordering = [
        ExposureLevel.LOW,
        ExposureLevel.MODERATE,
        ExposureLevel.HIGH,
        ExposureLevel.VERY_HIGH,
    ]
    assert ordering.index(with_sites.exposure_level) >= ordering.index(
        base.exposure_level
    )


def test_never_labeled_as_medical_measurement():
    result = score_exposure(ward_id="W02", aqi=200, pm25=110, population=80_000)
    assert (
        "medical" not in result.methodology.lower()
        or "not" in result.methodology.lower()
    )
    assert (
        "estimate" in result.methodology.lower()
        or "estimated" in result.methodology.lower()
    )


def test_single_ward_dataset_uses_fallback_thresholds_not_relative_only():
    result = score_exposure(ward_id="W01", aqi=100, pm25=50, population=150_000)
    assert result.population_band == PopulationBand.HIGH
