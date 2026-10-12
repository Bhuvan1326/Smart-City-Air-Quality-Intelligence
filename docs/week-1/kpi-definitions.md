# Candidate KPI Definitions (Week 1)

These are **definitions only**; no KPI value has been computed. Table/field names are from the ORM; confirm column names against `backend/app/models/*` before implementing. Time basis: UTC stored, report in IST.

| KPI | Formula | Required fields | Unit | Window | Limitations |
|---|---|---|---|---|---|
| **K1 Data freshness** | % of active stations with latest *observed* reading age <= 120 min; also median age | `monitoring_stations.id`, latest `aqi_readings.timestamp` (observation time), `quality_flag` | % / minutes | rolling 1 h, daily | Invalid until D1 fixed on the legacy path (timestamp = ingestion time). Excludes `synthetic`. |
| **K2 Station coverage** | stations reporting >= 1 valid reading in window / stations expected | stations table `is_active` | % | 24 h | "Expected" list quality. |
| **K3 Forecast error** | MAE and RMSE of forecast vs later observed ward AQI, per horizon (1, 6, 12, 24 h) | `forecast_grids` (issue time, target time, ward, predicted), observed hourly mean | AQI points | rolling 7 d, 30 d | Requires storing forecasts at issue time and matching to observations; vs baselines (see evaluation plan). Do not mix fallback and model forecasts. |
| **K4 Forecast skill** | 1 - MAE_model / MAE_persistence | as K3 | ratio | 30 d | Needs persistence computed on same set. |
| **K5 Alert response time** | median/p90 of (time first staff action - alert created) | `citizen_alerts.created_at`, enforcement/ack timestamps (exact acknowledgement field to be confirmed) | minutes | 30 d | No explicit "acknowledged" timestamp confirmed; may need a schema addition. |
| **K6 Alert delivery rate** | delivered / attempted notifications | `notifications` status, Twilio callbacks | % | 30 d | Depends on Twilio callback configuration. |
| **K7 Civic report processing** | time-to-triage, time-to-resolve (median, p90), % resolved within SLA, % citizen-verified | `civic_issue_status_events.created_at`, `civic_issues.created_at`, statuses | hours, % | 30 d | SLA thresholds not defined in code; need product input. Excludes duplicates/cluster members (`civic_issue_clusters`). |
| **K8 Enforcement outcome** | share of actions reaching `completed`; mean AQI change at nearest station pre/post (descriptive only) | `enforcement_actions`, `intervention_outcomes`, `aqi_readings` | %, AQI points | 90 d | **Not causal** (see below). |
| **K9 Energy efficiency** | kWh per unit service (or per ward/building) after normalising for weather/degree-days; carbon via grid intensity | metered consumption series, weather, area/occupancy, grid-intensity provider | kWh/m2, gCO2/kWh | >= 12 months for seasonality | No metered consumption source found in the repo; provider gives grid intensity only. |
| **K10 Waste-burning -> collection** | detection (satellite/citizen) -> dispatched -> collected: counts and median lag per stage | FIRMS detections / civic issues of type waste, enforcement action, collection/resolution event | counts, hours | 30 d | Collection event may not exist as data; detections have false positives and ~km-scale footprint. |

## Evidence needed for outcome claims (no causal claims from before/after)
- **Traffic interventions:** a counterfactual design (difference-in-differences with comparable control wards or synthetic control), traffic volume/speed series, weather adjustment, >= 8-12 pre-intervention weeks, pre-registered metric and window, sensitivity to station placement.
- **Energy efficiency:** weather-normalised baseline model (degree days), metered data, intervention dates, rebound/occupancy controls.
- **Waste-burning workflow:** audited event log linking detection -> action -> resolution, detection validation sample, repeated-event rate.
Simple before/after AQI deltas confound weather, season, and regional episodes and **must not** be reported as impact.

## Data validation tests added
`test_freshness_future_timestamp_is_not_live` (D2). Recommended next: unit-conversion and "no valid pollutant" tests when D3/D4 are fixed.
