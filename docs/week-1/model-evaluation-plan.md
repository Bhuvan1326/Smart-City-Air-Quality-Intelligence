# Model Evaluation Plan

**Status: plan only. No metrics have been computed** (no data available; see B4). Nothing here should be quoted as a result.

## Data requirements
Hourly, ward-level `avg_aqi` (+ weather), quality-filtered (`NOT IN invalid, synthetic, stale`), UTC timestamps with a documented local-time conversion, >= 90 days (>= 1 full seasonal cycle preferred), gap report per ward.

## Targets and horizons
Per-ward AQI at +1, +6, +12, +24 h. The current model is 1-step recursive, so error at long horizons compounds; evaluate each horizon separately.

## Splitting
Walk-forward (expanding window): train on days [0, T), test on [T, T+7d), advance by 7 d; >= 4 folds. Never shuffle. Features for a test hour use only information available at forecast issue time `t0` (no future weather, no future AQI). Keep a final untouched holdout (last 14 d). Because wards are spatially correlated, also report a **leave-ward-group-out** check for generalisation to new wards, clearly separated from the main metric.

## Baselines (must be beaten to justify the model)
1. Persistence: AQI(t0+h) = AQI(t0).
2. Seasonal naive: AQI(t0+h-24h) (and 168 h as a second baseline).
3. Ward-hour climatology (mean by ward x hour-of-day x weekday from training window only).
4. Current statistical fallback (to quantify what users receive today), seeded for determinism.

## Metrics
MAE and RMSE (AQI units) per horizon, per ward and city-aggregated; skill = 1 - MAE_model/MAE_baseline. Report fold-to-fold spread. **Interval coverage / calibration only after real intervals exist** (empirical residual quantiles); the current heuristic interval must not be scored as if it were a probabilistic forecast. Also report AQI-category accuracy (CPCB bands) as a secondary, operationally meaningful metric.

## Leakage checklist
Same-ward label alignment test (done: `test_target_is_same_ward_next_hour`); chronological split (done in training code); no rolling features computed across the split; weather forecast vs observed weather distinction at serving time; duplicate/overlapping hours across wards sharing stations.

## Acceptance for replacing the serving model
Beats seasonal-naive and persistence on MAE at >= 3 of 4 horizons across all folds, no horizon worse than persistence by >5%, results reproducible from a committed script and data hash.

## Owner / dependencies
Bhuvan; needs Vinyak's data export, Aryan's decision on serving-contract changes (`source` field).

## Training/inference feature contract
| # | Feature | Training value | Inference value (current) | Match? |
|---|---|---|---|---|
| 1 | avg_aqi / current_aqi | AQI at t | latest/prior-step AQI | yes (semantics) |
| 2 | hour_of_day | hour(t) | hour(target) | **No (M4)** |
| 3 | day_of_week | dow(t) | dow(now) | **No (M4)** |
| 4 | is_weekend | from dow(t) | from now | **No (M4)** |
| 5 | is_industrial | ward in {W03,W04} | same rule | yes |
| 6-8 | temp, humidity, wind | observed means | placeholders/defaults | **No** |


## Week 2 update
Harness implemented (`backend/app/ml/evaluation.py`) and verified on synthetic fixtures. **Results are still unavailable** (no real data, weather not persisted). See `docs/week-2/data-and-evaluation-status.md` for the empty metrics table and blockers.
