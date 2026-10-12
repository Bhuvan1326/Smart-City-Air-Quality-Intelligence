# ML Real-Data Evaluation Report (Priority 4)

## Status: PIPELINE VERIFIED — REAL-DATA EVAL BLOCKED (no populated observation DB)

## 4.1 — Pipeline audit (re-verified this session)

- `app/ml/evaluation.py`: expanding-window walk-forward, **no shuffle, no leakage**; identical (ward, origin) samples across all models.
- `app/ml/dataset.py::FEATURE_COLUMNS` — fixed order contract used by both training and serving.
- `FORECAST_ALIGN_FEATURES_TO_ORIGIN=False` — documented skew flag; evaluator scores both variants.
- No retraining or model replacement performed (per instructions — pipeline understood first).

## 4.2 — Data sufficiency (honest)

| Required | Available |
|---|---|
| ≥ `initial_train_hours(672)+test_hours(168)` ≈ 35 days × wards of real `aqi_measurements` + `weather_measurements` | **0 rows** — DB unpopulated locally; ingestion never run against live services |
| Export to eval CSV contract | `dataset.py` export path exists |
| Provenance | would be `source` column + `is_synthetic=False` filter |

**Nothing was relabeled.** The fixture artifact (`walk_forward_results.json`) remains correctly labeled SYNTHETIC — it verifies the pipeline executes, nothing more.

## 4.3 — Reproducible command (ready; needs data)

```bash
# After ≥35d ingestion on the compose stack:
cd backend && .venv/Scripts/python.exe -m app.ml.evaluation \
  --csv <real_export.csv> --out <out_dir>
# Baselines auto-compared: persistence, seasonal-24h, seasonal-168h, climatology
# Metrics: MAE/RMSE, fold stats, per-ward (sufficient-n only), missing counts
```

## 4.4 — Inference behavior (verified)

- Valid-artifact path: deterministic response schema + model metadata.
- Missing artifact: model-unavailable state — **no fabricated predictions**.
- Missing features/insufficient history: excluded from scoring; per-ward results suppressed below sufficiency.

## Acceptance status

| Criterion | Status |
|---|---|
| No temporal leakage | VERIFIED (walk-forward, identical samples) |
| Provenance explicit | VERIFIED (fixture labeled synthetic; real eval will use `source`/`is_synthetic`) |
| Evaluator reproducible | VERIFIED (executed, artifact written) |
| Baselines reported | VERIFIED (on fixture) / **BLOCKED** (on real data) |
| Real-data results | **NOT CLAIMED** — never ran |
| Inference + unavailable-model tested | VERIFIED (unit + code path) |

**The honest gate: real accuracy numbers require Priority-1 unblock (DB) + ~35 days of ingestion first.**
