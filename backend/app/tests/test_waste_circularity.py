"""Unit tests for app.services.waste_circularity. Pure calculation, no DB."""

from datetime import date, timedelta

from app.services.waste_circularity import score_circularity


def test_no_data_on_file_is_unavailable_not_fabricated():
    result = score_circularity(ward_id="W01", today=date(2026, 8, 25))
    assert result.is_data_configured is False
    assert result.circularity_score is None
    assert (
        result.circularity_unavailable_reason == "Insufficient verified waste-flow data"
    )
    assert result.recovery_rate_pct is None
    assert len(result.missing_fields) == 5


def test_score_computed_when_recovery_and_collection_present():
    result = score_circularity(
        ward_id="W01",
        today=date(2026, 8, 25),
        collection_efficiency_pct=80.0,
        recycling_pct=20.0,
        composting_pct=10.0,
        data_as_of=date(2026, 1, 1),
    )
    assert result.recovery_rate_pct == 30.0
    assert result.circularity_score == round(0.6 * 30.0 + 0.4 * 80.0, 1)
    assert result.circularity_unavailable_reason is None
    assert result.recovery_rate_includes_recycling is True
    assert result.recovery_rate_includes_composting is True


def test_recovery_rate_capped_at_100():
    result = score_circularity(
        ward_id="W01",
        today=date(2026, 8, 25),
        collection_efficiency_pct=90.0,
        recycling_pct=70.0,
        composting_pct=60.0,
    )
    assert result.recovery_rate_pct == 100.0


def test_partial_recovery_data_still_computes_score_with_collection_efficiency():
    result = score_circularity(
        ward_id="W01",
        today=date(2026, 8, 25),
        collection_efficiency_pct=75.0,
        recycling_pct=15.0,
        # composting_pct not on file
    )
    assert result.recovery_rate_pct == 15.0
    assert result.recovery_rate_includes_composting is False
    assert result.circularity_score is not None


def test_score_unavailable_without_collection_efficiency():
    result = score_circularity(
        ward_id="W01",
        today=date(2026, 8, 25),
        recycling_pct=40.0,
        composting_pct=10.0,
    )
    assert result.recovery_rate_pct == 50.0
    assert result.circularity_score is None
    assert (
        result.circularity_unavailable_reason == "Insufficient verified waste-flow data"
    )


def test_landfill_dependency_reported_as_is():
    result = score_circularity(
        ward_id="W01", today=date(2026, 8, 25), landfill_pct=65.0
    )
    assert result.landfill_dependency_pct == 65.0


def test_freshness_recent_vs_stale_municipal_report():
    recent = score_circularity(
        ward_id="W01",
        today=date(2026, 8, 25),
        recycling_pct=10.0,
        data_as_of=date(2026, 8, 1),
    )
    assert recent.freshness_label == "latest_available"

    stale = score_circularity(
        ward_id="W01",
        today=date(2026, 8, 25),
        recycling_pct=10.0,
        data_as_of=date(2026, 8, 25) - timedelta(days=500),
    )
    assert stale.freshness_label == "latest_available_possibly_outdated"


def test_freshness_unavailable_when_no_date_on_file():
    result = score_circularity(
        ward_id="W01", today=date(2026, 8, 25), recycling_pct=10.0
    )
    assert result.freshness_label == "unavailable"


def test_no_reuse_rate_field_exists_on_result():
    result = score_circularity(ward_id="W01", today=date(2026, 8, 25))
    assert not hasattr(result, "reuse_rate_pct")
