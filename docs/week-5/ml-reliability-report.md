# Week 5 — ML Reliability Report

## Versioned inference interface (as implemented)

| Property | Value |
|---|---|
| Model file | `backend/ml_models/xgb_forecast_<UTC-stamp>.joblib` |
| Sidecar | `<file>.meta.json` written for **new** trainings: feature order, version, trained-at |
| Feature contract | `FEATURE_COLUMNS` in `dataset.py`: `avg_aqi, hour_of_day, day_of_week, is_weekend, is_industrial, avg_temp, avg_humidity, avg_wind` — fixed order |
| Input rules | hourly ward rows; UTC timestamps; missing AQI excluded from scoring |
| Output | per-horizon AQI prediction; horizons 1/6/12/24 h |
| Skew flag | `FORECAST_ALIGN_FEATURES_TO_ORIGIN` (default False) — documented, measurable in evaluator |
| Failure behavior | missing model file → forecast endpoint reports model-unavailable (UI state exists), never fabricates |

## Evaluation method (verified)

`app/ml/evaluation.py`: expanding-window walk-forward (chronological, no shuffle, no leakage); identical (ward, origin) samples across all compared models; baselines = persistence, seasonal-naive-24h, seasonal-naive-168h, ward+hour climatology; XGBoost + legacy-serving variant on h=1; metrics MAE/RMSE + per-fold stats + per-ward (only wards with sufficient n).

## Reproducible artifact

`docs/week-3/ml-eval-fixture/out/walk_forward_results.json` — deterministic synthetic fixture (4800 rows, 4 wards, 96 missing, fixed seed). **Pipeline-verification data only.** Quoting the h=1 numbers (climatology MAE 5.58 / XGB 5.79 / legacy 6.42) is valid only as "the machinery ran correctly" — the synthetic signal was *built* as ward/hour means so climatology trivially wins.

## Skew monitoring

The evaluator scores both feature variants (`FORECAST_ALIGN_FEATURES_TO_ORIGIN` on/off) on the same samples → the skew is *measurable and reported*, not silent. Enabling alignment in a staging eval is the remediation path; default stays documented-off pending a retrain decision.

## BLOCKED for real accuracy

Needs ≥ `initial_train_hours(672) + test_hours(168)` ≈ 35 days of *populated* AQI+weather observations → export to the eval CSV contract → run. No such export exists (DB unprovisioned). **No production accuracy claim is made anywhere in this project.**

## Integrity rules kept

No random temporal split; no favorable-window selection; baselines scored on identical samples; missing values excluded before metrics; fixture output labeled synthetic at the file level and in every doc that cites it.
