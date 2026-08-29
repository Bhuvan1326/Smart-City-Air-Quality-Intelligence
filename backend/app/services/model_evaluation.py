"""
Model performance evaluation — genuine backtests, not fabricated metrics.

For each trained model version in the registry, this walks forward through
real historical AQI observations for the city, generates the model's
1-hour-ahead prediction at each historical hour using the same feature
construction as app.ml.inference.ModelRegistry.predict, and compares it
against what was actually observed. MAE/RMSE/R²/MAPE are computed with
scikit-learn from those real (y_true, y_pred) pairs — nothing here is a
placeholder or invented number.

Training period dates are inferred as an approximate 90-day window ending at
the model's trained_at timestamp, since no separate training-run metadata
(exact date range, sample count used for fitting) is persisted alongside the
model artifact. This is a labelled approximation, not a scored metric.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
from app.core.logging import logger
from app.ml.inference import ModelRegistry, get_model_registry
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    r2_score,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TRAINING_WINDOW_DAYS = 90
BACKTEST_DAYS = 14
MIN_SERIES_POINTS = 10
MIN_TEST_SAMPLES = 5


async def _get_hourly_series(session: AsyncSession, city: str, days: int) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        text(
            """
        SELECT date_trunc('hour', r.timestamp AT TIME ZONE 'UTC') AS bucket,
               AVG(r.aqi) AS avg_aqi, AVG(r.temperature) AS avg_temp,
               AVG(r.humidity) AS avg_humidity, AVG(r.wind_speed) AS avg_wind
        FROM aqi_readings r
        JOIN monitoring_stations s ON r.station_id = s.id
        WHERE s.city = :city AND r.timestamp >= :since
          AND r.is_deleted = false AND r.quality_flag != 'invalid'
        GROUP BY bucket ORDER BY bucket
    """
        ),
        {"city": city, "since": since},
    )
    return [dict(row._mapping) for row in result if row.avg_aqi is not None]


def _backtest_model(
    registry: ModelRegistry, series: list[dict]
) -> tuple[list[float], list[float]]:
    """
    Walk forward through the hourly series, predicting each hour's AQI from
    the previous hour's observation via registry.predict (which uses the
    loaded ML model if present, else the statistical fallback).
    """
    y_true: list[float] = []
    y_pred: list[float] = []

    for i in range(len(series) - 1):
        current = series[i]
        actual_next = series[i + 1]["avg_aqi"]
        if actual_next is None or current["avg_aqi"] is None:
            continue

        bucket = current["bucket"]
        pred = registry.predict(
            current_aqi=float(current["avg_aqi"]),
            hour=bucket.hour,
            day_of_week=bucket.weekday(),
            is_industrial_ward=False,
            temperature=(
                float(current["avg_temp"]) if current["avg_temp"] is not None else 25.0
            ),
            humidity=(
                float(current["avg_humidity"])
                if current["avg_humidity"] is not None
                else 60.0
            ),
            wind_speed=(
                float(current["avg_wind"]) if current["avg_wind"] is not None else 3.0
            ),
            hours_ahead=1,
        )
        y_true.append(float(actual_next))
        y_pred.append(float(pred.aqi_forecast))

    return y_true, y_pred


def _compute_metrics(y_true: list[float], y_pred: list[float]) -> dict:
    y_true_arr = np.array(y_true)
    y_pred_arr = np.array(y_pred)
    mae = mean_absolute_error(y_true_arr, y_pred_arr)
    rmse = float(np.sqrt(mean_squared_error(y_true_arr, y_pred_arr)))
    r2 = r2_score(y_true_arr, y_pred_arr) if len(y_true_arr) > 1 else 0.0
    try:
        mape = mean_absolute_percentage_error(y_true_arr, y_pred_arr)
    except Exception:  # noqa: BLE001 -- degenerate (all-zero actuals) edge case
        mape = None
    return {
        "mae": round(float(mae), 3),
        "rmse": round(float(rmse), 3),
        "r2": round(float(r2), 4),
        "mape": round(float(mape), 4) if mape is not None else None,
    }


def _parse_trained_at(raw: str) -> datetime:
    """meta.trained_at is an xgb_forecast_<YYYYMMDD_HHMM> stem for ML
    versions, or already an ISO string for anything else."""
    try:
        return datetime.strptime(raw, "%Y%m%d_%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return datetime.now(timezone.utc)


def _statistical_only_registry() -> ModelRegistry:
    """A registry instance with no ML model loaded, so predict() always
    falls through to the statistical diurnal fallback."""
    reg = ModelRegistry.__new__(ModelRegistry)
    reg._active_model = None
    reg._active_version = "statistical-v1.0"
    return reg


async def evaluate_model_versions(
    session: AsyncSession, city: str, target: str = "aqi"
) -> list[dict]:
    """Backtest every registered model version against real historical data
    for `city` and return one performance record per version that had
    enough data to evaluate."""
    if target != "aqi":
        return []

    registry = get_model_registry()
    versions = registry.list_models()
    series = await _get_hourly_series(session, city, BACKTEST_DAYS)

    if len(series) < MIN_SERIES_POINTS:
        return []

    records = []
    for meta in versions:
        if meta.version.startswith("xgb-"):
            import joblib

            try:
                loaded_model = joblib.load(meta.path)
            except Exception as e:  # noqa: BLE001 -- corrupt/missing artifact, skip
                logger.warning(
                    "model_evaluation.load_failed", version=meta.version, error=str(e)
                )
                continue
            eval_registry = ModelRegistry.__new__(ModelRegistry)
            eval_registry._active_model = loaded_model
            eval_registry._active_version = meta.version
            model_name = "XGBoost Regressor"
        else:
            eval_registry = _statistical_only_registry()
            model_name = "Statistical Diurnal Model"

        y_true, y_pred = _backtest_model(eval_registry, series)
        if len(y_true) < MIN_TEST_SAMPLES:
            continue

        metrics = _compute_metrics(y_true, y_pred)
        trained_at = _parse_trained_at(meta.trained_at)

        records.append(
            {
                "model_version": meta.version,
                "model_name": model_name,
                "target": target,
                "city": city,
                "trained_at": trained_at.isoformat(),
                "training_period_start": (
                    trained_at - timedelta(days=TRAINING_WINDOW_DAYS)
                ).isoformat(),
                "training_period_end": trained_at.isoformat(),
                "test_sample_count": len(y_true),
                "features": meta.feature_names,
                "is_active": meta.is_active,
                **metrics,
            }
        )

    return records
