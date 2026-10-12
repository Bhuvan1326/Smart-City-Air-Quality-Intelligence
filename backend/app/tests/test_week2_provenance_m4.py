"""Week 2 (F1/F2): M4 serving-skew flag, prediction `source`, model metadata."""

import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.core.config import settings
from app.ml import evaluation as ev
from app.ml import provenance as pv
from app.ml.inference import ModelRegistry
from app.schemas.enforcement import ForecastResponse
from app.workers.tasks import forecast as fw


# ------------------------------------------------------------ provenance --
@pytest.mark.parametrize(
    "h,expected_weight", [(1, 1.0), (13, 0.5), (25, 0.0), (72, 0.0)]
)
def test_model_weight_matches_documented_decay(h, expected_weight):
    assert pv.model_weight_for_horizon(h) == pytest.approx(expected_weight)


def test_source_labels_follow_the_blend_and_never_overclaim():
    assert pv.forecast_source("xgb-v1.0-recursive", 1) == pv.SOURCE_TRAINED
    assert pv.forecast_source("xgb-v1.0-recursive", 6) == pv.SOURCE_BLEND
    assert pv.forecast_source("xgb-v1.0-recursive", 40) == pv.SOURCE_STATISTICAL
    assert pv.forecast_source("xgb-x", None) == pv.SOURCE_BLEND  # unknown horizon
    for v in ("statistical-v1.0", "", None, "receptor-model-v1.2"):
        assert pv.forecast_source(v, 1) == pv.SOURCE_STATISTICAL
    assert pv.forecast_source("xgb-1", 3) in pv.ALLOWED_SOURCES


def _resp(version, hours):
    now = datetime(2026, 9, 1, 10, tzinfo=UTC)
    return ForecastResponse(
        id="00000000-0000-0000-0000-000000000001",
        city="Pune",
        ward_id="W01",
        forecast_timestamp=now + timedelta(hours=hours),
        generated_at=now,
        aqi_forecast=100,
        pm25_forecast=55.0,
        confidence_score=0.9,
        confidence_lower=90,
        confidence_upper=110,
        model_version=version,
        contributing_factors=None,
        feature_importance=None,
        aqi_category="moderate",
    )


def test_response_exposes_source_in_json():
    assert (
        _resp("xgb-v1.0-recursive", 1).model_dump(mode="json")["source"]
        == "trained_model"
    )
    assert _resp("xgb-v1.0-recursive", 12).source == "model_statistical_blend"
    assert _resp("xgb-v1.0-recursive", 30).source == "statistical_fallback"
    assert _resp("statistical-v1.0", 1).source == "statistical_fallback"
    assert _resp("xgb-v1.0-recursive", 1).model_artifact is None  # DB rows: unknown


# ------------------------------------------------- M4 reproduction + flag --
def test_m4_mismatch_reproduced_and_flag_aligns_features():
    # origin 22:00 Saturday(5), forecasting 3 h ahead.
    legacy = pv.feature_time_parts(22, 5, 3, aligned=False)
    aligned = pv.feature_time_parts(22, 5, 3, aligned=True)
    assert legacy == (1, 5)  # target hour 01:00, day NOT advanced (bug)
    assert aligned == (0, 6)  # observation at t0+2h = 00:00 on Sunday
    # h=1 aligned equals the observation's own hour (training semantics)
    assert pv.feature_time_parts(9, 2, 1, aligned=True) == (9, 2)
    assert pv.feature_time_parts(9, 2, 1, aligned=False) == (10, 2)
    # week wrap
    assert pv.feature_time_parts(23, 6, 2, aligned=True) == (0, 0)


class _Stub:
    """Records the feature rows the model receives."""

    def __init__(self):
        self.rows = []

    def predict(self, X):
        self.rows.append(np.array(X)[0].tolist())
        return np.array([123.0])

    def get_booster(self):
        raise RuntimeError("no booster in stub")  # exercised: importance is optional


def test_registry_flag_default_is_off_and_changes_only_time_features(
    tmp_path, monkeypatch
):
    assert settings.FORECAST_ALIGN_FEATURES_TO_ORIGIN is False  # safe default
    reg = ModelRegistry(str(tmp_path))
    reg._active_model = _Stub()
    reg._active_version = "xgb-test"
    monkeypatch.setattr(settings, "FORECAST_ALIGN_FEATURES_TO_ORIGIN", False)
    reg.predict(100.0, hour=9, day_of_week=2, is_industrial_ward=False, hours_ahead=1)
    monkeypatch.setattr(settings, "FORECAST_ALIGN_FEATURES_TO_ORIGIN", True)
    reg.predict(100.0, hour=9, day_of_week=2, is_industrial_ward=False, hours_ahead=1)
    off, on = reg._active_model.rows
    assert off[1] == 10 and on[1] == 9  # hour_of_day only differs
    assert off[0] == on[0] and off[2] == on[2] and off[5:] == on[5:]


def test_worker_recursion_uses_observation_time_when_aligned(monkeypatch):
    stub = _Stub()
    monkeypatch.setattr(settings, "FORECAST_ALIGN_FEATURES_TO_ORIGIN", True)
    out = fw._statistical_forecast(100.0, 3, "W01", model=stub)
    assert len(out) == 3 and len(stub.rows) == 3
    hours = [r[1] for r in stub.rows]
    now_h = datetime.now(UTC).hour
    # tolerate a clock tick across the hour boundary during the test
    assert hours[0] in (now_h, (now_h + 1) % 24)
    assert hours[1] == (hours[0] + 1) % 24 and hours[2] == (hours[0] + 2) % 24
    stub.rows.clear()
    monkeypatch.setattr(settings, "FORECAST_ALIGN_FEATURES_TO_ORIGIN", False)
    fw._statistical_forecast(100.0, 1, "W01", model=stub)
    assert stub.rows[0][1] in (
        (datetime.now(UTC).hour + 1) % 24,
        (datetime.now(UTC).hour + 2) % 24,
    )


# ------------------------------------------------- source on prediction path --
def test_prediction_source_reflects_actual_execution_path(tmp_path):
    reg = ModelRegistry(str(tmp_path))
    assert reg.load_latest() is False  # unavailable artifact
    r = reg.predict(100.0, 9, 2, False)
    assert r.source == pv.SOURCE_STATISTICAL and r.is_ml_model is False
    assert r.model_metadata is None

    reg._active_model = _Stub()
    reg._active_version = "xgb-test"
    r = reg.predict(100.0, 9, 2, False)
    assert r.source == pv.SOURCE_TRAINED and r.is_ml_model is True

    class Broken:
        def predict(self, X):
            raise ValueError("boom")

    reg._active_model = Broken()
    r = reg.predict(100.0, 9, 2, False)
    assert r.source == pv.SOURCE_STATISTICAL and r.is_ml_model is False


# ------------------------------------------------------------ metadata --
def test_sidecar_metadata_is_written_loaded_and_linked_to_the_artifact(
    tmp_path, monkeypatch
):
    import joblib
    from sklearn.dummy import DummyRegressor

    model_path = str(tmp_path / "xgb_forecast_20260101_0000.joblib")
    joblib.dump(DummyRegressor().fit([[0] * 8], [1.0]), model_path)
    train = pd.DataFrame({"hour": pd.to_datetime(["2026-01-01", "2026-01-10"])})
    test = pd.DataFrame({"hour": pd.to_datetime(["2026-01-11", "2026-01-12"])})
    meta = fw.build_model_metadata(
        model_path=model_path,
        train_df=train,
        test_df=test,
        mae=4.2,
        rmse=6.1,
        created_at=datetime(2026, 1, 13, tzinfo=UTC),
    )
    assert (
        meta["feature_names"] == fw.FEATURE_COLUMNS and len(meta["feature_names"]) == 8
    )
    assert meta["model_version"] == "xgb_forecast_20260101_0000"
    assert meta["horizon_hours"] == 1 and meta["evaluation_reference"] is None
    assert "not walk-forward" in meta["chronological_holdout"]["note"]
    (tmp_path / "xgb_forecast_20260101_0000.meta.json").write_text(json.dumps(meta))

    reg = ModelRegistry(str(tmp_path))
    assert reg.load_latest() is True
    assert reg._active_metadata["model_version"] == "xgb_forecast_20260101_0000"
    listed = reg.list_models()[0]
    assert listed.mae == 4.2 and listed.feature_names == fw.FEATURE_COLUMNS

    monkeypatch.setattr(settings, "MODEL_REGISTRY_PATH", str(tmp_path))
    assert fw._latest_model_artifact_name() == "xgb_forecast_20260101_0000"


def test_artifact_without_sidecar_reports_unknown_not_invented(tmp_path):
    import joblib
    from sklearn.dummy import DummyRegressor

    joblib.dump(
        DummyRegressor().fit([[0] * 8], [1.0]),
        str(tmp_path / "xgb_forecast_20250101_0000.joblib"),
    )
    reg = ModelRegistry(str(tmp_path))
    assert reg.load_latest() is True and reg._active_metadata is None
    m = reg.list_models()[0]
    assert m.mae is None and m.rmse is None


# ---------------------------------------------- A/B harness for the flag --
def test_evaluation_reports_aligned_vs_legacy_serving_on_identical_sample():
    rng = np.random.default_rng(1)
    start = pd.Timestamp("2026-01-01")
    rows = []
    for h in range(24 * 16):
        t = start + pd.Timedelta(hours=h)
        for w in ("W01", "W02"):
            rows.append(
                {
                    "hour": t,
                    "ward_id": w,
                    "avg_aqi": 100
                    + 60 * np.sin(2 * np.pi * t.hour / 24)
                    + rng.normal(0, 1),
                    "avg_temp": 25.0,
                    "avg_humidity": 50.0,
                    "avg_wind": 2.0,
                }
            )
    res = ev.evaluate(
        pd.DataFrame(rows), horizons=(1,), initial_train_hours=24 * 8, test_hours=24 * 4
    )
    rows_ = {r["model"]: r for r in res["rows"]}
    assert rows_["xgboost"]["n_samples"] == rows_["xgboost_legacy_serving"]["n_samples"]
    # On a strongly hour-dependent series, feeding the wrong hour must hurt.
    assert rows_["xgboost_legacy_serving"]["mae"] > rows_["xgboost"]["mae"]
