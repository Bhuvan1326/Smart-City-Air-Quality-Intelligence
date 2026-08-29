from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from app.ml.inference import ModelMetadata
from app.services import model_evaluation


def test_compute_metrics_perfect_predictions_are_all_zero_error():
    y_true = [50.0, 60.0, 70.0, 80.0]
    y_pred = [50.0, 60.0, 70.0, 80.0]

    metrics = model_evaluation._compute_metrics(y_true, y_pred)

    assert metrics["mae"] == 0.0
    assert metrics["rmse"] == 0.0
    assert metrics["r2"] == 1.0
    assert metrics["mape"] == 0.0


def test_compute_metrics_known_constant_offset():
    y_true = [100.0, 100.0, 100.0]
    y_pred = [110.0, 110.0, 110.0]

    metrics = model_evaluation._compute_metrics(y_true, y_pred)

    assert metrics["mae"] == pytest.approx(10.0)
    assert metrics["rmse"] == pytest.approx(10.0)
    assert metrics["mape"] == pytest.approx(0.1)


def test_parse_trained_at_handles_xgb_stem_format():
    dt = model_evaluation._parse_trained_at("20260816_1509")
    assert dt == datetime(2026, 8, 16, 15, 9, tzinfo=UTC)


def test_parse_trained_at_handles_iso_format():
    dt = model_evaluation._parse_trained_at("2026-06-01T00:00:00+00:00")
    assert dt == datetime(2026, 6, 1, tzinfo=UTC)


def test_parse_trained_at_falls_back_to_now_for_unparseable_input():
    before = datetime.now(UTC)
    dt = model_evaluation._parse_trained_at("not-a-real-timestamp")
    after = datetime.now(UTC)
    assert before <= dt <= after


def test_statistical_only_registry_never_uses_ml_model():
    registry = model_evaluation._statistical_only_registry()

    result = registry.predict(
        current_aqi=120.0,
        hour=8,
        day_of_week=1,
        is_industrial_ward=False,
    )

    assert result.is_ml_model is False
    assert result.model_version == "statistical-v1.0"


def _make_series(hours: int, base_aqi: float = 100.0) -> list[dict]:
    start = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    series = []
    for i in range(hours):
        series.append(
            {
                "bucket": start + timedelta(hours=i),
                "avg_aqi": base_aqi + (i % 5) * 3.0,
                "avg_temp": 26.0,
                "avg_humidity": 55.0,
                "avg_wind": 3.5,
            }
        )
    return series


def test_backtest_model_pairs_each_hour_with_the_next():
    registry = model_evaluation._statistical_only_registry()
    series = _make_series(12)

    y_true, y_pred = model_evaluation._backtest_model(registry, series)

    # one fewer pair than points, since the last hour has no "next" to compare to
    assert len(y_true) == len(series) - 1
    assert len(y_pred) == len(y_true)
    assert all(isinstance(v, float) for v in y_true)
    assert all(isinstance(v, float) for v in y_pred)


def test_backtest_model_skips_hours_with_missing_aqi():
    registry = model_evaluation._statistical_only_registry()
    series = _make_series(6)
    series[2]["avg_aqi"] = None  # a gap in the real hourly data

    y_true, y_pred = model_evaluation._backtest_model(registry, series)

    # pairs (1,2) and (2,3) are both skipped because one side is None
    assert len(y_true) == len(series) - 1 - 2


@pytest.mark.asyncio
async def test_evaluate_model_versions_returns_empty_for_non_aqi_target():
    session = AsyncMock()
    result = await model_evaluation.evaluate_model_versions(
        session, "Pune", target="pm25"
    )
    assert result == []


@pytest.mark.asyncio
async def test_evaluate_model_versions_returns_empty_when_series_too_short():
    session = AsyncMock()
    with patch.object(
        model_evaluation, "_get_hourly_series", new=AsyncMock(return_value=[])
    ):
        result = await model_evaluation.evaluate_model_versions(session, "Pune")
    assert result == []


@pytest.mark.asyncio
async def test_evaluate_model_versions_backtests_statistical_fallback_version():
    session = AsyncMock()
    series = _make_series(20)

    fake_meta = ModelMetadata(
        path="unused",
        version="statistical-v1.0",
        trained_at="2026-06-01T00:00:00+00:00",
        mae=None,
        rmse=None,
        feature_names=["avg_aqi", "hour_of_day"],
        is_active=True,
    )

    fake_registry = AsyncMock()
    fake_registry.list_models = lambda: [fake_meta]

    with (
        patch.object(
            model_evaluation, "_get_hourly_series", new=AsyncMock(return_value=series)
        ),
        patch.object(
            model_evaluation, "get_model_registry", return_value=fake_registry
        ),
    ):
        records = await model_evaluation.evaluate_model_versions(
            session, "Pune", target="aqi"
        )

    assert len(records) == 1
    record = records[0]
    assert record["model_version"] == "statistical-v1.0"
    assert record["model_name"] == "Statistical Diurnal Model"
    assert record["city"] == "Pune"
    assert record["target"] == "aqi"
    assert record["test_sample_count"] == len(series) - 1
    assert record["is_active"] is True
    assert isinstance(record["mae"], float)
    assert isinstance(record["rmse"], float)
    assert isinstance(record["r2"], float)
    assert record["training_period_end"] == "2026-06-01T00:00:00+00:00"


@pytest.mark.asyncio
async def test_evaluate_model_versions_skips_version_with_unloadable_artifact():
    session = AsyncMock()
    series = _make_series(20)

    fake_meta = ModelMetadata(
        path="/nonexistent/xgb_forecast_20260101_0000.joblib",
        version="xgb-20260101_0000",
        trained_at="20260101_0000",
        mae=None,
        rmse=None,
        feature_names=["avg_aqi"],
        is_active=True,
    )
    fake_registry = AsyncMock()
    fake_registry.list_models = lambda: [fake_meta]

    with (
        patch.object(
            model_evaluation, "_get_hourly_series", new=AsyncMock(return_value=series)
        ),
        patch.object(
            model_evaluation, "get_model_registry", return_value=fake_registry
        ),
    ):
        records = await model_evaluation.evaluate_model_versions(
            session, "Pune", target="aqi"
        )

    # the artifact file doesn't exist, so this version is skipped rather than
    # crashing the whole evaluation
    assert records == []
