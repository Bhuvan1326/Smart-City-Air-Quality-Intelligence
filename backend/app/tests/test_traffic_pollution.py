"""Unit tests for app.services.traffic_pollution. No DB dependency."""

from datetime import datetime

from app.services.traffic_pollution import analyze_traffic_pollution
from app.services.traffic_provider import TrafficDataSource


def _rows():
    # Peak hours (8am, 18pm) get elevated AQI; night hours (2-4am) get low AQI.
    return [
        {"bucket": datetime(2026, 1, 1, 8, 0), "aqi": 220, "pm25": 130, "pm10": 200, "no2": 90},
        {"bucket": datetime(2026, 1, 1, 8, 0).replace(day=2), "aqi": 210, "pm25": 125, "pm10": 195, "no2": 85},
        {"bucket": datetime(2026, 1, 1, 18, 0), "aqi": 230, "pm25": 140, "pm10": 210, "no2": 95},
        {"bucket": datetime(2026, 1, 1, 2, 0), "aqi": 45, "pm25": 20, "pm10": 35, "no2": 15},
        {"bucket": datetime(2026, 1, 1, 3, 0), "aqi": 40, "pm25": 18, "pm10": 30, "no2": 12},
        {"bucket": datetime(2026, 1, 1, 4, 0), "aqi": 42, "pm25": 19, "pm10": 32, "no2": 13},
    ]


def test_high_traffic_periods_show_higher_aqi():
    result = analyze_traffic_pollution(hourly_readings=_rows())
    assert result.high_vs_low_aqi_ratio is not None
    assert result.high_vs_low_aqi_ratio > 1.1
    assert "associated with" in result.observation.lower()


def test_never_claims_causation():
    result = analyze_traffic_pollution(hourly_readings=_rows())
    assert "cause" not in result.observation.lower().replace("causal", "")


def test_demo_source_labeled_not_live():
    result = analyze_traffic_pollution(hourly_readings=_rows())
    assert result.traffic_data_source == TrafficDataSource.DEMO
    assert "demo data" in result.observation.lower()


def test_insufficient_data_gives_honest_message():
    result = analyze_traffic_pollution(hourly_readings=_rows()[:2])
    assert "not enough" in result.observation.lower()


def test_empty_input_does_not_crash():
    result = analyze_traffic_pollution(hourly_readings=[])
    assert result.sample_size == 0
    assert result.high_vs_low_aqi_ratio is None
