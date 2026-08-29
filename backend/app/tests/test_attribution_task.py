"""
Unit tests for app.workers.tasks.attribution's pure rule-based/statistical
attribution model (_attribute_sources). Doesn't touch the database --
_attribution_async (the DB-backed orchestration) is integration-tested
separately in test_attribution_integration.py.
"""

import pytest

from app.workers.tasks.attribution import PUNE_WARDS, _attribute_sources

# ─── Percentage splits always sum to ~100 ──────────────────────────────────


@pytest.mark.parametrize("ward", PUNE_WARDS)
@pytest.mark.parametrize("hour", [3, 8, 14, 19])
def test_source_percentages_sum_to_100(ward, hour):
    result = _attribute_sources(ward=ward, avg_aqi=120.0, hour=hour, dow=2)
    total = (
        result["vehicular_pct"]
        + result["industrial_pct"]
        + result["construction_pct"]
        + result["biomass_pct"]
        + result["dust_pct"]
        + result["domestic_pct"]
    )
    assert total == pytest.approx(100.0, abs=0.5)


# ─── Industrial vs. residential ward behaviour ─────────────────────────────


def test_industrial_ward_has_higher_industrial_share_than_residential():
    industrial = _attribute_sources(ward="W03", avg_aqi=100.0, hour=12, dow=2)
    residential = _attribute_sources(ward="W01", avg_aqi=100.0, hour=12, dow=2)
    assert industrial["industrial_pct"] > residential["industrial_pct"]


def test_peak_hour_increases_vehicular_share():
    peak = _attribute_sources(ward="W01", avg_aqi=100.0, hour=8, dow=2)
    off_peak = _attribute_sources(ward="W01", avg_aqi=100.0, hour=2, dow=2)
    assert peak["vehicular_pct"] > off_peak["vehicular_pct"]


# ─── Confidence: regression tests for the fixed collapse-to-two-values bug ─
# Previously `confidence = 0.78 if avg_aqi > 100 else 0.65` -- a coarse
# binary step wholly determined by one side of a single AQI threshold, so
# nearly every ward showed one of only two confidence values regardless of
# its actual data. These tests pin down the fix: confidence must vary
# continuously with AQI and be sensitive to ward/time context, not just to
# which side of AQI=100 the reading falls on.


def test_confidence_is_not_binary_across_aqi_range():
    confidences = {
        aqi: _attribute_sources(ward="W01", avg_aqi=aqi, hour=12, dow=2)[
            "overall_confidence"
        ]
        for aqi in (40, 70, 90, 110, 140, 180, 220)
    }
    # At least 4 distinct values across 7 AQI levels -- not collapsed to
    # {0.65, 0.78}.
    assert len(set(confidences.values())) >= 4


def test_confidence_increases_monotonically_with_aqi():
    prev = 0.0
    for aqi in (30, 60, 90, 120, 150, 200, 250):
        conf = _attribute_sources(ward="W01", avg_aqi=aqi, hour=12, dow=2)[
            "overall_confidence"
        ]
        assert conf >= prev
        prev = conf


def test_confidence_varies_between_wards_at_same_aqi_and_time():
    # Same AQI, same hour, same day -- confidence should still differ
    # between an industrial ward and a residential one (previously it was
    # identical for every ward not crossing the AQI=100 threshold).
    industrial_conf = _attribute_sources(ward="W03", avg_aqi=80.0, hour=12, dow=2)[
        "overall_confidence"
    ]
    residential_conf = _attribute_sources(ward="W01", avg_aqi=80.0, hour=12, dow=2)[
        "overall_confidence"
    ]
    assert industrial_conf != residential_conf


def test_confidence_lower_on_weekends_than_weekdays():
    weekday = _attribute_sources(ward="W01", avg_aqi=100.0, hour=12, dow=2)[
        "overall_confidence"
    ]
    weekend = _attribute_sources(ward="W01", avg_aqi=100.0, hour=12, dow=6)[
        "overall_confidence"
    ]
    assert weekend < weekday


def test_confidence_always_within_bounds():
    for ward in PUNE_WARDS:
        for aqi in (0, 50, 100, 200, 500):
            for hour in (0, 8, 12, 19, 23):
                for dow in (0, 6):
                    conf = _attribute_sources(
                        ward=ward, avg_aqi=aqi, hour=hour, dow=dow
                    )["overall_confidence"]
                    assert 0.55 <= conf <= 0.90


# ─── Satellite evidence boost ──────────────────────────────────────────────


def test_satellite_agreement_boosts_confidence():
    baseline = _attribute_sources(ward="W01", avg_aqi=100.0, hour=12, dow=2)
    boosted = _attribute_sources(
        ward="W01",
        avg_aqi=100.0,
        hour=12,
        dow=2,
        satellite_evidence={
            "category_scores": {"construction_dust": 0.8},
            "confidence": 0.9,
        },
    )
    assert boosted["overall_confidence"] > baseline["overall_confidence"]
    assert boosted["construction_pct"] > baseline["construction_pct"]


def test_satellite_confidence_boost_is_capped_at_095():
    boosted = _attribute_sources(
        ward="W03",
        avg_aqi=250.0,
        hour=8,
        dow=2,
        satellite_evidence={
            "category_scores": {
                "construction_dust": 1.0,
                "biomass_burning": 1.0,
                "industrial_hotspot": 1.0,
            },
            "confidence": 1.0,
        },
    )
    assert boosted["overall_confidence"] <= 0.95
