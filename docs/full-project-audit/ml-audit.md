# ML & Forecasting Audit

## Training pipeline (inspected)

- Dataset builder `app/ml/dataset.py` — `FEATURE_COLUMNS` fixed order: `avg_aqi, hour_of_day, day_of_week, is_weekend, is_industrial, avg_temp, avg_humidity, avg_wind`.
- Chronological handling in the evaluator (expanding window) — **no random shuffle, no future leakage** in the eval path.
- Missing values: rows with null AQI excluded before scoring; insufficient-history wards get no per-ward claim.
- Artifacts: `ml_models/xgb_forecast_*.joblib` ×9 (pre-sidecar era); new trainings write `.meta.json` (version, feature order, timestamp).

## Serving/inference path

- `FORECAST_ALIGN_FEATURES_TO_ORIGIN=False` — documented training/serving skew flag; evaluator measures both variants on identical samples → skew is *quantifiable*, not hidden.
- Missing model file → forecast API reports model-unavailable; frontend has an explicit state (verified page code); **never fabricates a forecast**.
- Feature-importance/explainability failure does not discard predictions (migration 004 stores explainability separately).

## Evaluation — `walk_forward_results.json` provenance

**SYNTHETIC FIXTURE** — `docs/week-3/ml-eval-fixture/hourly_ward_synthetic.csv`: deterministic seed, 4,800 hourly rows × 4 wards, 96 injected nulls. Provenance verified by generation method, not filename.

| Method check | Result |
|---|---|
| Expanding-window walk-forward | ✅ `initial_train_hours=672, test_hours=168, folds=3` |
| Baselines on identical samples | ✅ persistence, seasonal-24h, seasonal-168h, climatology |
| MAE+RMSE + fold stats + per-ward | ✅ machine-readable JSON |
| Interval calibration | n/a — model emits no intervals; correctly absent (not faked) |
| Leakage | none — chronological splits only |

Fixture h=1 (n=1862): climatology MAE 5.58 < XGB 5.79 < legacy-serving 6.42 — *expected*: the synthetic signal is ward/hour means+noise. **Pipeline-verification only.**

## Verdict

- Evaluator correctness: **VERIFIED** (tests + executed run + artifact).
- Production accuracy: **BLOCKED** — no populated observation DB; needs ≥35 days ingested data → export → rerun. Zero real-world accuracy claims exist in code or docs.
- Serving skew: documented + measurable; enable `FORECAST_ALIGN_FEATURES_TO_ORIGIN` in staging eval before enabling in prod.
