# Forecasting Audit (Week 1)

Files: `backend/app/workers/tasks/forecast.py` (training, scheduled regeneration), `backend/app/ml/inference.py` (serving), `backend/ml_models/*.joblib` (9 XGBoost artifacts). **No real observations or database snapshot were available, so no model metric was computed or is claimed.**

## Contract (what the code actually does)
| Item | Value |
|---|---|
| Target | Ward-level hourly mean **AQI** (CPCB-style index, unitless, 0-500) |
| Spatial unit | `ward_id` (`W01`...), joined from station -> ward |
| Model | `XGBRegressor`, 200 estimators, 8 inputs (verified on shipped artifacts), **1-hour-ahead** |
| Horizon > 1 h | Recursive: each step's prediction becomes next step's `current_aqi` |
| Inputs (positional) | `current_aqi, hour_of_day, day_of_week, is_weekend, is_industrial(W03,W04), temperature, humidity, wind_speed` (artifact stores no feature names) |
| Time basis | Hour from DB `time_bucket` (UTC unless session TZ differs); inference uses UTC hour |
| Fallback | `_statistical_forecast` when no artifact loads |
| Metrics persisted | None; MAE/RMSE only logged at retrain time |

## Findings
| # | Sev | Finding | Evidence | Reproduced | Status |
|---|---|---|---|---|---|
| M1 | **High** | **Training target mislabelled.** `target = avg_aqi.shift(-1)` over rows `ORDER BY hour` with all wards interleaved labels each row with the *next row* (another ward, or the next hour's first ward), not the same ward's next hour. Gaps in hourly data would additionally break the 1-h horizon. | `_retrain_async` (original) | Mechanism reproduced on **synthetic** frames: with >=2 wards per hour the old construction labels the same ward's next hour correctly for 0% of rows (100% only with 1 ward). Not measured on real data; actual effect depends on within-hour row order and ward count. | **Fixed** in training code: `build_training_frame` (per-ward shift, require exactly +1 h, drop gaps). Tests: `test_target_is_same_ward_next_hour`, `test_old_global_shift_would_have_mislabelled_rows`, `test_gap_in_hours_drops_row_instead_of_bridging`. |
| M2 | **High** | **Random shuffled split.** `train_test_split` with shuffle on an autocorrelated hourly series puts adjacent hours in train and test; logged MAE/RMSE are optimistic and not comparable to forecast-time error. | `_retrain_async` (original) | By code read | **Fixed**: `chronological_split` (hour-boundary cut, no shuffling). Test: `test_chronological_split_never_leaks_future_into_train`. |
| M3 | Med | **Training included `synthetic` and `stale` readings**; inference excludes them. In dev, the seeder inserts `synthetic` rows. | training SQL (`!= 'invalid'`) vs inference query | By code read | **Fixed** in training SQL (`NOT IN ('invalid','synthetic','stale')`). Not covered by an automated test (needs Timescale). |
| M4 | **Med-High** | **Training/serving feature skew.** Training row at time *t* has `hour_of_day(t)` and predicts *t+1*. Inference passes `hour_of_day(target_time)` while `current_aqi` is the prior step's value, i.e. an off-by-one-hour mismatch; `day_of_week`/`is_weekend` also appear to be taken from "now", not the target time, which is wrong across midnight. Weather is real in training but **constant placeholders** at inference. | `ml/inference.py` | By code read; not run | **Not fixed** (changing serving alters live forecasts and must be validated by walk-forward evaluation first). |
| M5 | Med | **Existing artifacts were trained under M1-M3** and should be treated as unvalidated. They were *not* replaced or retrained. | artifacts dated 2026-08-16..09-10 | n/a | Open; retrain after data export (B4). |
| M6 | Med | **Intervals are not statistical.** `confidence = 0.92 - 0.005 h` and margins from a fixed formula; no calibration. Do not report coverage/interval metrics. | `ml/inference.py` | By code read | Open |
| M7 | Med | **Fallback forecast is non-deterministic and double-counts diurnal effect**: `np.random` noise; multipliers applied to the *current* AQI (which already reflects the current hour); peak windows (07-10, 17-20) use UTC hours although the intent is local (IST) time (5.5 h offset). | `_statistical_forecast` | By code read | Open |
| M8 | Med | `pm25_forecast = 0.55 x AQI` is an invented conversion, not a measurement. | `ml/inference.py` | By code read | Open; relabel or remove |
| M9 | Low | No artifact metadata (feature names, training window, metrics, data hash); selection by filename sort. | `ml_models` | Verified | Open |
| M10 | Low | Responses do not say whether model or fallback produced them. | endpoint | By code read | Open (contract proposal) |
| M11 | Info | Missing/outlier handling: rows with missing weather dropped in training; no outlier clipping; unseen wards are not an issue for numeric features except `is_industrial` hard-coded to W03/W04. | training | By code read | Document |

## Validation
Existing suite: all forecasting tests that ran pass (mocks and unit behaviour). Added 4 training-frame tests (synthetic fixtures; **they verify construction logic, not accuracy**).

## Prioritised actions
1. Export hourly ward-level `aqi_readings` (excl. invalid/synthetic/stale) + weather for >= 90 days (Vinyak -> Bhuvan).
2. Retrain with the fixed pipeline; walk-forward evaluate vs persistence and seasonal-naive (see `model-evaluation-plan.md`) **before** replacing any serving artifact.
3. Fix M4 skew behind a flag, A/B on the same walk-forward folds.
4. Add model metadata sidecar (JSON) with feature list/order and metrics; make serving validate it.
5. Replace heuristic intervals with empirical residual quantiles per horizon (or label as indicative); add `source` field.
