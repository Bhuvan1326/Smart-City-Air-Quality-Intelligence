"""Reproducible walk-forward evaluation of the AQI forecaster vs baselines.

Input : hourly ward CSV produced by `app.ml.dataset` (hour UTC, ward_id,
        avg_aqi, avg_temp, avg_humidity, avg_wind, ...).
Method: expanding-window walk-forward. For each fold the model is trained ONLY
        on rows whose target hour is <= train_end; forecasts are issued at every
        origin t0 in [train_end, test_end) and scored at t0 + h.
Fair comparison: every model is scored on the IDENTICAL set of (ward, origin)
        pairs (the intersection where all required inputs exist).
Models: persistence, seasonal-naive-24h, seasonal-naive-168h, ward x hour-of-day
        climatology (training window only), xgboost (horizon 1 only; the serving
        model is a 1-step model, multi-horizon recursion is NOT evaluated here).
Nothing is tuned on the evaluation windows (hyperparameters are the fixed
training constants). If weather is missing the xgboost model is reported as
unavailable instead of being trained on invented inputs.

CLI: python -m app.ml.evaluation --csv hourly_ward_dataset.csv --out-dir eval_out
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_HORIZONS = (1, 6, 12, 24)
BASELINES = ("persistence", "seasonal_naive_24h", "seasonal_naive_168h", "climatology")


def mae(y, p) -> float:
    return float(np.mean(np.abs(np.asarray(y) - np.asarray(p))))


def rmse(y, p) -> float:
    return float(np.sqrt(np.mean((np.asarray(y) - np.asarray(p)) ** 2)))


def walk_forward_folds(
    first_hour: pd.Timestamp,
    last_hour: pd.Timestamp,
    initial_train_hours: int,
    test_hours: int,
    step_hours: int | None = None,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """List of (train_end, test_end): train on < train_end, score origins in
    [train_end, test_end). Windows never overlap the training period."""
    step = step_hours or test_hours
    folds, train_end = [], first_hour + pd.Timedelta(hours=initial_train_hours)
    while train_end + pd.Timedelta(hours=test_hours) <= last_hour + pd.Timedelta(
        hours=1
    ):
        folds.append((train_end, train_end + pd.Timedelta(hours=test_hours)))
        train_end += pd.Timedelta(hours=step)
    return folds


def _wide(df: pd.DataFrame, col: str) -> pd.DataFrame:
    w = df.pivot_table(index="hour", columns="ward_id", values=col, aggfunc="mean")
    full = pd.date_range(w.index.min(), w.index.max(), freq="h")
    return w.reindex(full)


def _baseline_predictions(
    aqi: pd.DataFrame, origins: pd.DatetimeIndex, h: int, climo: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    """Each value: DataFrame indexed by origin, columns = ward."""
    hd = pd.Timedelta(hours=h)
    out = {}
    out["persistence"] = aqi.reindex(origins)
    for name, lag in (("seasonal_naive_24h", 24), ("seasonal_naive_168h", 168)):
        src = origins + hd - pd.Timedelta(hours=lag)
        # input must be known at the origin (src <= origin)
        frame = aqi.reindex(src)
        frame.index = origins
        if (src > origins).any():
            frame[:] = np.nan
        out[name] = frame
    target_hours = (origins + hd).hour
    cl = climo.reindex(target_hours)
    cl.index = origins
    out["climatology"] = cl
    return out


def evaluate(
    df: pd.DataFrame,
    horizons=DEFAULT_HORIZONS,
    initial_train_hours: int = 24 * 28,
    test_hours: int = 24 * 7,
    step_hours: int | None = None,
    min_ward_samples: int = 30,
) -> dict:
    from app.workers.tasks.forecast import (
        FEATURE_COLUMNS,
        XGB_PARAMS,
        build_training_frame,
    )

    df = df.copy()
    df["hour"] = pd.to_datetime(df["hour"])
    df = df.sort_values(["hour", "ward_id"])
    aqi = _wide(df, "avg_aqi")
    folds = walk_forward_folds(
        aqi.index.min(), aqi.index.max(), initial_train_hours, test_hours, step_hours
    )
    weather_ok = all(
        df[c].notna().any() for c in ("avg_temp", "avg_humidity", "avg_wind")
    )
    result: dict = {
        "method": "expanding-window walk-forward; identical (ward, origin) sample for all models",
        "initial_train_hours": initial_train_hours,
        "test_hours": test_hours,
        "n_folds": len(folds),
        "horizons": list(horizons),
        "xgboost_available": False,
        "xgboost_unavailable_reason": None,
        "rows": [],
        "limitations": [
            "xgboost is a 1-step model: only horizon 1 is evaluated for it.",
            "xgboost = training-consistent features (M4 aligned); xgboost_legacy_serving "
            "= same trained model fed the legacy serving features (target hour).",
            "Intervals are not evaluated (the serving intervals are not statistical).",
            "No hyperparameter tuning was performed on any evaluation window.",
        ],
    }
    if not folds:
        result["error"] = "insufficient data for even one walk-forward fold"
        return result
    if not weather_ok:
        result["xgboost_unavailable_reason"] = (
            "weather columns are entirely NULL; the model's feature contract requires "
            "temperature/humidity/wind"
        )

    per_model: dict = {}  # (model, h) -> lists
    for fold_i, (train_end, test_end) in enumerate(folds):
        train = df[df["hour"] < train_end]
        if train.empty:
            continue
        climo = train.assign(hod=train["hour"].dt.hour).pivot_table(
            index="hod", columns="ward_id", values="avg_aqi", aggfunc="mean"
        )
        model = None
        if weather_ok:
            import xgboost as xgb

            frame = build_training_frame(train)
            frame = frame[frame["hour"] + pd.Timedelta(hours=1) <= train_end]
            if len(frame) >= 50:
                model = xgb.XGBRegressor(**XGB_PARAMS).fit(
                    frame[FEATURE_COLUMNS].values, frame["target_aqi"].values
                )
                result["xgboost_available"] = True
        origins = pd.date_range(train_end, test_end, freq="h", inclusive="left")
        origins = origins.intersection(aqi.index)
        for h in horizons:
            tgt = aqi.reindex(origins + pd.Timedelta(hours=h))
            tgt.index = origins
            preds = _baseline_predictions(aqi, origins, h, climo)
            xgb_pred = None
            xgb_legacy_pred = None
            if model is not None and h == 1:
                cols, cols_legacy = {}, {}
                wt = {
                    c: _wide(df, c).reindex(origins)
                    for c in ("avg_temp", "avg_humidity", "avg_wind")
                }
                for ward in aqi.columns:
                    X = pd.DataFrame(
                        {
                            "avg_aqi": aqi[ward].reindex(origins).values,
                            "hour_of_day": origins.hour,
                            "day_of_week": origins.dayofweek,
                            "is_weekend": (origins.dayofweek >= 5).astype(int),
                            "is_industrial": int(ward in ("W03", "W04")),
                            "avg_temp": wt["avg_temp"]
                            .get(ward, pd.Series(np.nan, index=origins))
                            .values,
                            "avg_humidity": wt["avg_humidity"]
                            .get(ward, pd.Series(np.nan, index=origins))
                            .values,
                            "avg_wind": wt["avg_wind"]
                            .get(ward, pd.Series(np.nan, index=origins))
                            .values,
                        },
                        index=origins,
                    )
                    ok = X.notna().all(axis=1)
                    col = pd.Series(np.nan, index=origins)
                    if ok.any():
                        col[ok] = model.predict(X[ok][FEATURE_COLUMNS].values)
                    cols[ward] = col
                    # Legacy serving (M4): the TARGET hour is fed instead of the
                    # observation's own hour; day_of_week is not advanced.
                    XL = X.copy()
                    XL["hour_of_day"] = (origins.hour + 1) % 24
                    col_l = pd.Series(np.nan, index=origins)
                    if ok.any():
                        col_l[ok] = model.predict(XL[ok][FEATURE_COLUMNS].values)
                    cols_legacy[ward] = col_l
                xgb_pred = pd.DataFrame(cols)
                xgb_legacy_pred = pd.DataFrame(cols_legacy)
            models = dict(preds)
            if xgb_pred is not None:
                models["xgboost"] = xgb_pred  # training-consistent (aligned) serving
                models["xgboost_legacy_serving"] = xgb_legacy_pred
            # identical sample: target and every model's prediction present
            mask = tgt.notna()
            for m in models.values():
                mask &= m.notna()
            for name, pred in models.items():
                for ward in aqi.columns:
                    sel = mask[ward]
                    if sel.any():
                        key = (name, h)
                        d = per_model.setdefault(
                            key, {"fold": [], "ward": [], "y": [], "p": []}
                        )
                        n = int(sel.sum())
                        d["fold"] += [fold_i] * n
                        d["ward"] += [ward] * n
                        d["y"] += tgt[ward][sel].tolist()
                        d["p"] += pred[ward][sel].tolist()

    # The identical-sample guarantee is per (horizon): confirm below via counts.
    for (name, h), d in sorted(per_model.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        y, p = np.array(d["y"]), np.array(d["p"])
        fold_arr, ward_arr = np.array(d["fold"]), np.array(d["ward"])
        fold_mae = [
            mae(y[fold_arr == f], p[fold_arr == f]) for f in sorted(set(d["fold"]))
        ]
        by_ward = {
            w: {
                "n": int((ward_arr == w).sum()),
                "mae": round(mae(y[ward_arr == w], p[ward_arr == w]), 4),
                "rmse": round(rmse(y[ward_arr == w], p[ward_arr == w]), 4),
            }
            for w in sorted(set(d["ward"]))
            if (ward_arr == w).sum() >= min_ward_samples
        }
        result["rows"].append(
            {
                "model": name,
                "horizon_hours": h,
                "n_samples": int(len(y)),
                "mae": round(mae(y, p), 4),
                "rmse": round(rmse(y, p), 4),
                "fold_mae_mean": round(float(np.mean(fold_mae)), 4),
                "fold_mae_std": (
                    round(float(np.std(fold_mae)), 4) if len(fold_mae) > 1 else None
                ),
                "n_folds_scored": len(fold_mae),
                "by_ward": by_ward,
            }
        )
    return result


def to_markdown(result: dict) -> str:
    lines = [
        "| model | horizon (h) | n | MAE | RMSE | fold MAE mean ± std |",
        "|---|---|---|---|---|---|",
    ]
    for r in result.get("rows", []):
        std = f" ± {r['fold_mae_std']}" if r["fold_mae_std"] is not None else ""
        lines.append(
            f"| {r['model']} | {r['horizon_hours']} | {r['n_samples']} | {r['mae']} | "
            f"{r['rmse']} | {r['fold_mae_mean']}{std} |"
        )
    if not result.get("xgboost_available"):
        lines.append(
            f"\nxgboost: UNAVAILABLE — {result.get('xgboost_unavailable_reason') or 'not enough training rows'}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:  # pragma: no cover
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, default=Path("eval_out"))
    p.add_argument("--initial-train-days", type=int, default=28)
    p.add_argument("--test-days", type=int, default=7)
    a = p.parse_args()
    res = evaluate(
        pd.read_csv(a.csv),
        initial_train_hours=24 * a.initial_train_days,
        test_hours=24 * a.test_days,
    )
    a.out_dir.mkdir(parents=True, exist_ok=True)
    (a.out_dir / "walk_forward_results.json").write_text(json.dumps(res, indent=2))
    (a.out_dir / "walk_forward_results.md").write_text(to_markdown(res))
    print(to_markdown(res))


if __name__ == "__main__":  # pragma: no cover
    main()
