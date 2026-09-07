"""Unit tests for app.services.green_infrastructure. No DB dependency."""

from app.services.green_infrastructure import (
    GreenPriority,
    InterventionType,
    score_green_infrastructure,
)
from app.services.population_exposure import ExposureLevel
from app.services.traffic_provider import TrafficLevel


def test_low_pollution_low_traffic_gives_low_priority():
    result = score_green_infrastructure(
        ward_id="W01",
        aqi=35,
        pm25=15,
        traffic_level=TrafficLevel.LOW,
        exposure_level=ExposureLevel.LOW,
    )
    assert result.priority == GreenPriority.LOW


def test_high_pollution_high_exposure_low_cover_gives_high_priority():
    result = score_green_infrastructure(
        ward_id="W06",
        aqi=250,
        pm25=140,
        traffic_level=TrafficLevel.HIGH,
        exposure_level=ExposureLevel.VERY_HIGH,
        green_cover_pct=8,
    )
    assert result.priority == GreenPriority.HIGH


def test_high_traffic_recommends_roadside_buffer():
    result = score_green_infrastructure(
        ward_id="W06",
        aqi=200,
        pm25=110,
        traffic_level=TrafficLevel.HIGH,
        exposure_level=ExposureLevel.HIGH,
        green_cover_pct=10,
    )
    assert result.recommended_intervention == InterventionType.ROADSIDE_GREEN_BUFFER


def test_missing_green_cover_excluded_not_assumed_zero():
    result = score_green_infrastructure(
        ward_id="W03",
        aqi=150,
        pm25=80,
        traffic_level=TrafficLevel.MODERATE,
        exposure_level=ExposureLevel.MODERATE,
    )
    assert result.is_green_cover_configured is False
    assert result.green_cover_pct is None
    assert any("no green-cover data" in r.lower() for r in result.rationale)


def test_high_existing_cover_lowers_priority():
    low_cover = score_green_infrastructure(
        ward_id="W02",
        aqi=150,
        pm25=80,
        traffic_level=TrafficLevel.MODERATE,
        exposure_level=ExposureLevel.MODERATE,
        green_cover_pct=5,
    )
    high_cover = score_green_infrastructure(
        ward_id="W02",
        aqi=150,
        pm25=80,
        traffic_level=TrafficLevel.MODERATE,
        exposure_level=ExposureLevel.MODERATE,
        green_cover_pct=60,
    )
    assert high_cover.priority_score < low_cover.priority_score


def test_never_estimates_specific_aqi_reduction():
    result = score_green_infrastructure(ward_id="W04", aqi=180, pm25=95)
    assert "%" not in result.impact_disclaimer
    assert "no specific aqi reduction" in result.impact_disclaimer.lower()


def test_missing_traffic_excluded_not_assumed_moderate():
    """No traffic_level passed at all -> must not silently default to
    MODERATE (or any other level); it must be excluded from the score and
    flagged in the rationale, the same way missing green cover is."""
    without_traffic = score_green_infrastructure(
        ward_id="W05",
        aqi=150,
        pm25=80,
        exposure_level=ExposureLevel.MODERATE,
    )
    assert without_traffic.traffic_level is None
    assert without_traffic.is_traffic_data_configured is False
    assert any(
        "live traffic data is unavailable" in r.lower()
        for r in without_traffic.rationale
    )

    with_moderate_traffic = score_green_infrastructure(
        ward_id="W05",
        aqi=150,
        pm25=80,
        exposure_level=ExposureLevel.MODERATE,
        traffic_level=TrafficLevel.MODERATE,
    )
    # Excluding an unavailable traffic reading must not score the same as
    # a genuinely-observed MODERATE reading once other inputs shift the
    # boundary (MODERATE traffic contributes +1 to the score).
    assert without_traffic.priority_score == with_moderate_traffic.priority_score - 1


def test_high_traffic_still_configured_and_scored():
    result = score_green_infrastructure(
        ward_id="W06",
        aqi=150,
        pm25=80,
        exposure_level=ExposureLevel.MODERATE,
        traffic_level=TrafficLevel.HIGH,
    )
    assert result.is_traffic_data_configured is True
    assert result.traffic_level == TrafficLevel.HIGH
    assert any("traffic level is currently high" in r.lower() for r in result.rationale)
