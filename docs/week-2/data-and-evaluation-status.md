# Data Export and Forecast Evaluation — Status (Vinyak / Bhuvan)

## Result: the P0 export and the retrain/evaluation are **BLOCKED**, not complete
**No real historical data exists in this environment** (no database snapshot, no provider credentials, no provider network). Therefore:
- **No 90-day export was produced and no coverage claim is made.**
- **No model was retrained and no MAE/RMSE exists.** The metrics table below is intentionally empty.

## What was delivered instead (verified tooling)
| Item | Where | Evidence |
|---|---|---|
| Read-only hourly ward export + gap report + metadata (SHA-256, units, filters, no secrets), TimescaleDB-independent | `backend/app/ml/dataset.py` (`python -m app.ml.dataset --days 90 --out-dir ...`) | `test_week2_dataset_export.py` (5 tests, incl. a DB test that synthetic/stale/invalid rows are excluded and hours aggregate in UTC) |
| Walk-forward evaluation with persistence, seasonal-naive 24/168 h, ward x hour climatology, XGBoost, identical-sample scoring, determinism, leakage guard, M4 aligned-vs-legacy A/B | `backend/app/ml/evaluation.py` (`python -m app.ml.evaluation --csv ...`) | `test_week2_evaluation.py` (8) + A/B test in `test_week2_provenance_m4.py`. Fixtures are synthetic with known answers; they verify the harness, not model quality |
| M1-M3 present in code and covered by tests | `workers/tasks/forecast.py` | `test_week1_data_ml.py` (re-run) |
| Training and evaluation share one feature list and hyperparameter set | `FEATURE_COLUMNS`, `XGB_PARAMS` | `test_week2_provenance_m4.py` |

## New blocking finding: weather is not stored
- Live OpenAQ ingestion writes `temperature/humidity/wind_speed = NULL` (`openaq.py` builds `LiveReading(temperature=None, ...)`), and the weather provider only fetches *current* weather (no history). The product's own Transparency page states Open-Meteo is "not yet persisted into AQI readings".
- The model's 8-feature contract requires weather, and training drops rows with missing weather, so a live-only dataset yields **zero training rows**. Previously (pre-M3) training would have used the synthetic seeded rows, which do carry weather.
- Consequence (inference, unverified; the artifacts carry no metadata): the existing artifacts were plausibly trained on **synthetic** data.
- The export reports weather coverage explicitly (`weather_usable_for_training`), and the evaluation reports XGBoost as *unavailable* rather than training on invented inputs (baselines still run).
- Options (needs a decision): (a) persist weather (Open-Meteo archive/forecast) joined by hour and ward; (b) change the feature contract to drop weather; (c) impute — **not recommended**. Owner: Aryan decision; Vinyak (a); Bhuvan (b).

## Metrics table (model-evaluation-plan.md)
| model | window | horizon | n | MAE | RMSE |
|---|---|---|---|---|---|
| persistence | – | – | – | **unavailable** | **unavailable** |
| seasonal_naive_24h / 168h | – | – | – | **unavailable** | **unavailable** |
| climatology | – | – | – | **unavailable** | **unavailable** |
| xgboost (corrected pipeline) | – | 1 h | – | **unavailable** | **unavailable** |
Reason: no real hourly ward data with weather. Next action: obtain a read-only export of >= 90 days (Vinyak), resolve the weather decision (Aryan), then run `python -m app.ml.evaluation`.

## M4 (serving skew) status
Reproduced and covered by tests; the correction is behind `FORECAST_ALIGN_FEATURES_TO_ORIGIN` (**default off**). The walk-forward A/B (`xgboost` vs `xgboost_legacy_serving`) cannot be run on real data yet, so the flag stays off. Metadata sidecars (`<artifact>.meta.json`) are written for newly trained models; the 9 existing artifacts have none and report unknown metrics rather than invented ones.
