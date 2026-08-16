# Changes made this session

Full unified diff against the uploaded `urban-air-quality-updated.zip` is in
`changes.diff` at the root of this zip. Summary below.

## Bug fixes

### 1. Ward W07 centroid/bbox was a copy-paste of W01's coordinates (6 files)
`W07` (Kothrud) shared the exact same lat/lon (and, in one file, the exact
same bounding box) as `W01` (Karve Road) in six independent per-file
coordinate tables. `app/core/seeder.py` and `app/gis/operations.py` already
had the correct, distinct value for W07 (`18.4968, 73.8126`), so that was
used as the source of truth to fix the rest:

- `backend/app/agents/langgraph_agents.py` — `_WARD_COORDS["W07"]`
- `backend/app/workers/tasks/attribution.py` — local `WARD_COORDS["W07"]`
- `backend/app/workers/tasks/forecast.py` — local `WARD_COORDS["W07"]`
- `backend/app/workers/tasks/aqi_ingestion.py` — `PUNE_STATIONS` "PUNE_007" entry
- `backend/app/workers/tasks/satellite.py` — `WARD_BBOXES["W07"]` (bounding box, derived from the same wrong centroid)

Regression coverage: `backend/app/tests/test_ward_coordinates_regression.py`
checks every one of these tables for internal duplicate values and for
cross-file agreement on W07's coordinates, so this bug class can't silently
reappear in any of them.

### 2. AttributionAgent confidence score collapsed to ~2 values regardless of ward
Root cause in `backend/app/workers/tasks/attribution.py`:
`confidence = 0.78 if avg_aqi > 100 else 0.65` — a binary step function of
AQI alone. Since most wards sit on the same side of AQI 100 most of the
time, and no other factor fed into it, confidence was effectively constant
across wards.

Replaced with a continuous, multi-signal estimate that scales with AQI
level, and adjusts for industrial-ward stability, peak-hour traffic
clarity, and weekend unpredictability — bounded to `[0.55, 0.90]` before
the (unchanged) satellite-evidence boost, which can still push it up to
`0.95`.

The exact same bug, independently, was in `backend/app/core/seeder.py`'s
demo-data generator (`overall_confidence=0.78 if is_ind else 0.65`), which
is what actually populates the dashboard in a fresh demo environment — this
was likely the proximate cause of the reported symptom. Fixed the same way,
reusing the ward AQI baselines already defined for forecast-grid seeding so
confidence tracks each ward's actual pollution level.

Regression coverage: `backend/app/tests/test_attribution_task.py` pins down
that confidence now (a) takes on more than 2 distinct values across an AQI
range, (b) increases monotonically with AQI, (c) differs between an
industrial and residential ward at identical AQI/time, (d) is lower on
weekends than weekdays, and (e) always stays in bounds.

## New test coverage (previously 0% on Celery worker task modules)

- `backend/app/tests/test_forecast_task.py` — `_build_forecast_features`,
  `_statistical_forecast` (including model-blending, weight decay, clipping,
  and graceful fallback when a loaded model raises), and `_load_latest_model`
  (empty registry, corrupt file, most-recent-file selection).
- `backend/app/tests/test_attribution_task.py` — `_attribute_sources`
  (percentage splits, industrial/peak-hour behavior, the confidence fix
  above, satellite-evidence boost and its cap).
- `backend/app/tests/test_ward_coordinates_regression.py` — see bug #1.

All new pure-logic assertions were dry-run against the actual fixed
function bodies in this sandbox (no DB/network available here) and pass.
**Not yet done:** DB-integration tests for the async, database-backed halves
of these tasks, and for `anomaly_detection.py`, `drone.py`,
`notifications.py`, `satellite.py` — these need a live Postgres/TimescaleDB
instance to run, which this sandbox doesn't have. Frontend Jest/Vitest setup
and DATABASE.md/API.md/TESTING.md are also still outstanding.
