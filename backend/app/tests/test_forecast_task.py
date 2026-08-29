"""
Unit tests for app.workers.tasks.forecast's pure logic (feature building,
the statistical/model-blended forecast, and model-registry loading). These
don't touch the database -- _forecast_async/_retrain_async (the DB-backed
orchestration around this logic) are integration-tested separately.
"""

import numpy as np
from app.workers.tasks.forecast import (
    _build_forecast_features,
    _load_latest_model,
    _statistical_forecast,
)

# ─── _build_forecast_features ──────────────────────────────────────────────


def test_build_forecast_features_shape_and_order():
    features = _build_forecast_features(
        current_aqi=120.0, hour=8, day_of_week=2, ward="W03"
    )
    assert features.shape == (1, 8)
    # [avg_aqi, hour_of_day, day_of_week, is_weekend, is_industrial,
    #  avg_temp, avg_humidity, avg_wind]
    row = features[0]
    assert row[0] == 120.0
    assert row[1] == 8
    assert row[2] == 2
    assert row[3] == 0  # Tuesday, not weekend
    assert row[4] == 1  # W03 is industrial


def test_build_forecast_features_weekend_and_non_industrial_flags():
    features = _build_forecast_features(
        current_aqi=80.0, hour=14, day_of_week=6, ward="W01"
    )
    row = features[0]
    assert row[3] == 1  # Sunday is weekend
    assert row[4] == 0  # W01 is not industrial


def test_build_forecast_features_uses_documented_climatology_placeholders():
    features = _build_forecast_features(
        current_aqi=100.0, hour=10, day_of_week=1, ward="W02"
    )
    row = features[0]
    assert row[5] == 26.0  # placeholder_temp
    assert row[6] == 55.0  # placeholder_humidity
    assert row[7] == 3.0  # placeholder_wind


# ─── _statistical_forecast (no trained model) ──────────────────────────────


def test_statistical_forecast_returns_one_entry_per_hour():
    forecasts = _statistical_forecast(current_aqi=100.0, hours_ahead=6, ward="W01")
    assert len(forecasts) == 6
    assert [f["hours_ahead"] for f in forecasts] == [1, 2, 3, 4, 5, 6]


def test_statistical_forecast_entries_have_required_explainability_fields():
    forecasts = _statistical_forecast(current_aqi=90.0, hours_ahead=3, ward="W05")
    for entry in forecasts:
        assert "aqi_forecast" in entry
        assert "confidence_score" in entry
        assert "confidence_lower" in entry
        assert "confidence_upper" in entry
        assert "contributing_factors" in entry
        assert "feature_importance" in entry
        assert (
            entry["confidence_lower"]
            <= entry["aqi_forecast"]
            <= entry["confidence_upper"]
        )


def test_statistical_forecast_aqi_never_below_floor():
    # Even with a very low current AQI + negative noise, forecasts are
    # floored at 10 (never zero/negative, which wouldn't be a valid AQI).
    forecasts = _statistical_forecast(current_aqi=5.0, hours_ahead=24, ward="W06")
    assert all(f["aqi_forecast"] >= 10 for f in forecasts)


def test_statistical_forecast_confidence_degrades_with_lookahead():
    forecasts = _statistical_forecast(current_aqi=100.0, hours_ahead=48, ward="W01")
    # Confidence should be non-increasing as lookahead grows (allowing for
    # the dispersion path being unused here, this is a pure hour-based decay).
    confidences = [f["confidence_score"] for f in forecasts]
    assert confidences[0] >= confidences[-1]
    assert confidences[-1] >= 0.55  # floor from `max(0.55, 0.92 - h * 0.005)`


def test_statistical_forecast_industrial_ward_has_higher_industrial_contribution():
    industrial = _statistical_forecast(current_aqi=100.0, hours_ahead=1, ward="W04")
    residential = _statistical_forecast(current_aqi=100.0, hours_ahead=1, ward="W01")
    assert (
        industrial[0]["contributing_factors"]["industrial"]
        > residential[0]["contributing_factors"]["industrial"]
    )


# ─── _statistical_forecast with a fake trained model ───────────────────────


class _FakeModel:
    """Always predicts a fixed AQI, regardless of input features."""

    def __init__(self, prediction: float):
        self.prediction = prediction

    def predict(self, features):
        return np.array([self.prediction])


def test_statistical_forecast_blends_model_prediction_at_h1():
    # At h=1 the model gets full weight (model_weight = 1.0), so the
    # forecast should equal the model's prediction almost exactly (up to
    # int() truncation and any dispersion, which is None here).
    model = _FakeModel(prediction=250.0)
    forecasts = _statistical_forecast(
        current_aqi=100.0, hours_ahead=1, ward="W02", model=model
    )
    assert forecasts[0]["aqi_forecast"] == 250
    assert forecasts[0]["feature_importance"]["trained_model_weight"] == 1.0


def test_statistical_forecast_model_weight_decays_toward_zero_by_h24():
    model = _FakeModel(prediction=400.0)
    forecasts = _statistical_forecast(
        current_aqi=100.0, hours_ahead=30, ward="W02", model=model
    )
    # By hour 25+, model_weight = max(0, 1 - (h-1)/24) is 0 -- the forecast
    # should have fully decayed away from the model's constant 400 toward
    # the bounded statistical estimate (nowhere near 400 with current_aqi=100).
    late_entry = forecasts[-1]
    assert late_entry["feature_importance"]["trained_model_weight"] == 0.0
    assert late_entry["aqi_forecast"] < 200


def test_statistical_forecast_model_prediction_is_clipped_to_valid_aqi_range():
    # A runaway model prediction shouldn't be able to produce an
    # out-of-range AQI in the blend.
    model = _FakeModel(prediction=99999.0)
    forecasts = _statistical_forecast(
        current_aqi=100.0, hours_ahead=1, ward="W01", model=model
    )
    assert forecasts[0]["aqi_forecast"] <= 500


def test_statistical_forecast_survives_a_model_that_raises():
    class _BrokenModel:
        def predict(self, features):
            raise RuntimeError("corrupt model")

    # Should not raise -- falls back to the statistical estimate for that hour.
    forecasts = _statistical_forecast(
        current_aqi=100.0, hours_ahead=2, ward="W01", model=_BrokenModel()
    )
    assert len(forecasts) == 2
    assert all(f["aqi_forecast"] >= 10 for f in forecasts)


# ─── _load_latest_model ─────────────────────────────────────────────────────


def test_load_latest_model_returns_none_when_registry_empty(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MODEL_REGISTRY_PATH", str(tmp_path))
    assert _load_latest_model() is None


def test_load_latest_model_returns_none_on_corrupt_file(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MODEL_REGISTRY_PATH", str(tmp_path))
    bad_file = tmp_path / "xgb_forecast_20260101.joblib"
    bad_file.write_bytes(b"not a real joblib file")

    # Should degrade gracefully (return None), not raise, so a corrupt
    # registry entry can't take down forecasting for the whole city.
    assert _load_latest_model() is None


def test_load_latest_model_loads_most_recent_file_by_sorted_name(tmp_path, monkeypatch):
    import joblib
    from app.core.config import settings

    monkeypatch.setattr(settings, "MODEL_REGISTRY_PATH", str(tmp_path))
    (tmp_path / "xgb_forecast_20260101.joblib").write_text("placeholder")
    joblib.dump(_FakeModel(prediction=42.0), tmp_path / "xgb_forecast_20260201.joblib")

    loaded = _load_latest_model()
    assert loaded is not None
    assert loaded.predict(None)[0] == 42.0
