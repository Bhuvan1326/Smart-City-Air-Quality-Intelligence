# Week 3 — ML Evaluation Status

## What exists (verified)

`app/ml/evaluation.py` implements **expanding-window walk-forward evaluation** — no random shuffle, no temporal leakage:

- Horizons 1/6/12/24 h; configurable `initial_train_hours`, `test_hours`, folds.
- Baselines on the **identical (ward, origin) samples**: persistence, seasonal-naive-24h, seasonal-naive-168h, ward+hour climatology.
- XGBoost (M4 candidate) + legacy-serving variant scored only for h=1.
- Metrics: MAE, RMSE, per-fold mean/std, per-ward breakdown.
- Missing data: rows with null AQI excluded before scoring; a model is never scored on a different sample set than its baselines.

Feature contract (`app/ml/dataset.py::FEATURE_COLUMNS`): `avg_aqi, hour_of_day, day_of_week, is_weekend, is_industrial, avg_temp, avg_humidity, avg_wind`. `FORECAST_ALIGN_FEATURES_TO_ORIGIN=False` is the serving/training skew flag; the evaluator reports both feature variants.

## Pipeline verification run — SYNTHETIC FIXTURE (not accuracy evidence)

Dataset: `docs/week-3/ml-eval-fixture/hourly_ward_synthetic.csv` — 4,800 hourly rows, 4 wards (W01–W04), 96 deliberately-missing AQI values, deterministic seed. Purpose: prove the walk-forward pipeline executes end-to-end and emits machine-readable metrics.

Command (reproducible):
```
cd backend && .venv/Scripts/python.exe -m app.ml.evaluation \
  --csv ../docs/week-3/ml-eval-fixture/hourly_ward_synthetic.csv \
  --out ../docs/week-3/ml-eval-fixture/out
```

Artifact: `docs/week-3/ml-eval-fixture/out/walk_forward_results.json` (machine-readable) + `.md`.

Results — h=1 (n=1862): climatology MAE 5.58, XGBoost MAE 5.79, legacy-serving MAE 6.42. h=6/12/24 climatology MAE ≈5.55–5.57. On this fixture climatology "wins" because the synthetic signal is built as ward/hour means + noise — **this says nothing about real accuracy**.

## Real-world evaluation — BLOCKED

| Blocker | Needed to unblock |
|---|---|
| No populated `aqi_measurements`/`weather_measurements` export exists in this repo — DB is empty locally and Postgres is unavailable (`:5434` refused) | Provision Postgres+TimescaleDB (docker-compose `db` service), run Alembic + ingestion for ≥ initial_train_hours(672)+test(168) ≈ 35 days of observations, export to the eval CSV contract |
| No sidecar `.meta.json` on the 9 existing `xgb_forecast_*.joblib` artifacts | New trainings now write sidecars; backfill or retrain to get version/feature provenance |
| `FORECAST_ALIGN_FEATURES_TO_ORIGIN=False` (documented skew) | Enable in staging eval to measure the aligned variant; keep flag documented |

**No production-accuracy claim is made.** The pipeline is ready; the data is not.
