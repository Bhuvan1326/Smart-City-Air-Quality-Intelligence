# Impact Ledger and City Action Brief — Interface Design

**Status: DESIGN ONLY. Nothing in this document is implemented.** It is prepared so Week 3 can start from agreed contracts. It must not be presented as an evidence-backed feature: its dependencies (a validated forecast, reliable freshness, weather data) are not yet met.

## What already exists (inspected, not assumed)
| Existing | Fields / role | Gap for the ledger |
|---|---|---|
| `enforcement_actions` | action, ward, officer, status, source | No link to the forecast that motivated it |
| `intervention_outcomes` | `aqi_before`, `aqi_after`, `delta_score`, `pm25_*`, `measurement_period_hours`, `verified_by`, `verification_method`, `carbon_saved_kg`, `confidence_score` (**default 0.8**) | **Nothing in the app writes to it**; `/analytics` reads it as an "improvement" figure. No window timestamps, no data provenance, no forecast link, an unjustified default confidence, and a "delta" that is an uncontrolled before/after difference |
| `forecast_grids` | ward forecasts | Does not record the artifact/`source` that produced a value; no immutable "forecast at issue" snapshot |

**Immediate risk:** the existing analytics figure can present a descriptive before/after difference as an "improvement". Until the ledger exists, treat `avg_aqi_improvement` as descriptive only, and remove the default `confidence_score` of 0.8 in Week 3.

## Impact Ledger (proposed contract)
One immutable ledger entry per intervention measurement:

| Field | Meaning |
|---|---|
| `action_id` (FK `enforcement_actions`) | the intervention |
| `forecast_snapshot` (JSON, frozen at issue time) | `{ward_id, issued_at, horizon_h, predicted_aqi, source, model_artifact, feature_alignment}` |
| `baseline_window` / `outcome_window` | `[start, end)` UTC, equal length, same hour-of-day coverage; windows must not overlap or double count readings used in another entry |
| `metric` + `unit` | e.g. `ward_mean_aqi` / `AQI index`; pollutant metrics in ug/m3 |
| `before_value`, `after_value`, `n_readings_before/after` | descriptive observations from non-synthetic, non-stale data only |
| `data_provenance` | `{source, quality_filter, freshness_at_measurement}` |
| `claim_level` | enum **`descriptive`** (default) \| `quasi_experimental` — only the latter may be shown as an effect estimate and only when a control/counterfactual design is recorded (`design`: DiD / synthetic control, control wards, weather adjustment). **No causal field is populated by simple before/after.** |
| `created_by`, `created_at`, `approved_by` | audit; approval restricted to ADM/OFF |

Invariants: no benefit numbers without both windows meeting a minimum sample; units stored with every value; entries are append-only.

## City Action Brief (proposed contract)
Ranked suggestions for the next 6 hours, each with:
`rank`, `ward_id`, `suggested_action` (rules-based), `inputs[]`, `basis` (one of **`observed`**, **`model_forecast`**, **`rule`**, **`human_decision`** per input), `forecast_source`, `data_freshness`, `uncertainty_note`, `status` (`suggested` -> `assigned` -> `approved`/`rejected` by a human), `decided_by`.
Rules: stale or unavailable inputs downgrade a suggestion and say so; a statistical-fallback forecast is labelled as such; **only ADM/OFF may create/assign/approve** (server-side `RequireAnalyst`); inspectors may view assigned items.

## Prerequisites before implementation
1. Retrained, walk-forward-evaluated model (blocked on data/weather — see `data-and-evaluation-status.md`).
2. D1 observation-time fix deployed and re-ingested data.
3. Product decisions: window lengths, minimum samples, who approves.
Owner: Aryan (contract, migration) with Bhuvan (forecast snapshot), Vinyak (windows/provenance), Rohan (authorization), Adwait (UI labels).
