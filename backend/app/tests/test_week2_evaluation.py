"""Week 2 (E1/E2): walk-forward evaluation machinery.

All series are SYNTHETIC with known answers; they verify the harness, they are
not evidence of real model performance.
"""

import numpy as np
import pandas as pd
import pytest

from app.ml import evaluation as ev

START = pd.Timestamp("2026-01-01")


def _series(days=20, wards=("W01", "W02"), weather=True, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for h in range(days * 24):
        t = START + pd.Timedelta(hours=h)
        for i, w in enumerate(wards):
            val = (
                100
                + 40 * np.sin(2 * np.pi * t.hour / 24)
                + 10 * i
                + rng.normal(0, noise)
            )
            rows.append(
                {
                    "hour": t,
                    "ward_id": w,
                    "avg_aqi": val,
                    "avg_temp": 25.0 if weather else np.nan,
                    "avg_humidity": 50.0 if weather else np.nan,
                    "avg_wind": 2.0 if weather else np.nan,
                }
            )
    return pd.DataFrame(rows)


def test_metrics_hand_computed():
    assert ev.mae([1, 2, 3], [2, 2, 5]) == pytest.approx(1.0)
    assert ev.rmse([1, 2, 3], [2, 2, 5]) == pytest.approx(np.sqrt(5 / 3))


def test_folds_are_chronological_and_never_overlap_training():
    folds = ev.walk_forward_folds(
        START, START + pd.Timedelta(hours=24 * 20 - 1), 24 * 7, 24 * 3
    )
    assert len(folds) >= 3
    for train_end, test_end in folds:
        assert train_end > START and test_end > train_end
    assert [f[0] for f in folds] == sorted(f[0] for f in folds)


def test_seasonal_naive_is_exact_on_a_perfectly_periodic_series():
    res = ev.evaluate(
        _series(), horizons=(1, 6), initial_train_hours=24 * 7, test_hours=24 * 3
    )
    rows = {(r["model"], r["horizon_hours"]): r for r in res["rows"]}
    assert rows[("seasonal_naive_24h", 1)]["mae"] == pytest.approx(0.0, abs=1e-9)
    assert rows[("climatology", 6)]["mae"] == pytest.approx(0.0, abs=1e-9)
    # persistence must be strictly worse on a sinusoid
    assert rows[("persistence", 6)]["mae"] > 1.0


def test_every_model_is_scored_on_the_identical_sample():
    res = ev.evaluate(
        _series(noise=1.0), horizons=(1,), initial_train_hours=24 * 7, test_hours=24 * 3
    )
    ns = {r["n_samples"] for r in res["rows"] if r["horizon_hours"] == 1}
    assert len(ns) == 1, "all models must share the same evaluation sample"
    assert any(r["model"] == "xgboost" for r in res["rows"])


def test_xgboost_reported_unavailable_when_weather_missing_not_invented():
    res = ev.evaluate(
        _series(weather=False),
        horizons=(1,),
        initial_train_hours=24 * 7,
        test_hours=24 * 3,
    )
    assert res["xgboost_available"] is False
    assert "weather" in res["xgboost_unavailable_reason"]
    assert all(r["model"] != "xgboost" for r in res["rows"])
    assert any(r["model"] == "persistence" for r in res["rows"])  # baselines still run


def test_evaluation_is_deterministic():
    a = ev.evaluate(
        _series(noise=2.0, seed=3),
        horizons=(1,),
        initial_train_hours=24 * 7,
        test_hours=24 * 3,
    )
    b = ev.evaluate(
        _series(noise=2.0, seed=3),
        horizons=(1,),
        initial_train_hours=24 * 7,
        test_hours=24 * 3,
    )
    assert a["rows"] == b["rows"]


def test_insufficient_data_is_reported_not_scored():
    res = ev.evaluate(_series(days=3), initial_train_hours=24 * 28, test_hours=24 * 7)
    assert res["n_folds"] == 0 and "insufficient" in res["error"]
    assert res["rows"] == []


def test_training_never_uses_rows_at_or_after_train_end():
    """Leakage guard: poison all data at/after the first train_end and confirm the
    first fold's seasonal/climatology baselines are unaffected."""
    base = _series(days=14)
    poisoned = base.copy()
    cutoff = START + pd.Timedelta(hours=24 * 7)
    poisoned.loc[
        poisoned["hour"] >= cutoff, "avg_aqi"
    ] += 1000.0  # affects targets only
    r = ev.evaluate(base, horizons=(1,), initial_train_hours=24 * 7, test_hours=24 * 7)
    # climatology is built from training rows only, so its predictions for fold 0
    # must not depend on post-train_end values: compare MAE sensitivity.
    rp = ev.evaluate(
        poisoned, horizons=(1,), initial_train_hours=24 * 7, test_hours=24 * 7
    )
    c0 = {x["model"]: x["mae"] for x in r["rows"]}["climatology"]
    c1 = {x["model"]: x["mae"] for x in rp["rows"]}["climatology"]
    assert c1 == pytest.approx(
        c0 + 1000.0, rel=1e-6
    )  # error shifts by exactly the poison
