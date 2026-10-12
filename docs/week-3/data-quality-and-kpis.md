# Week 3 — Data Quality & KPI Evidence

## Weather persistence — FIXED (was a dead fetch)

**Defect:** `aqi_ingestion._fetch_weather_async` fetched Open-Meteo hourly data for Pune+Mumbai every 900 s and **discarded it**. `weather_measurements` (migration 007) had no ORM model and no writer — every weather read was a live proxy call with zero history for ML training.

**Fix (W3-1):**
- `app/models/weather.py::WeatherMeasurement` — ORM model matching migration 007 column-for-column (city, lat/lng, temp_c, humidity_pct, wind_kmh, wind_dir, pressure_hpa, precip_mm, weather_code, source, is_forecast, observed_at, fetched_at).
- `app/services/weather_persistence.py` — `persist_hourly_forecast()` maps Open-Meteo hourly fields → columns and **upserts on `(city, observed_at, source)`**; a repeated fetch refreshes readings + `fetched_at` instead of inserting duplicates. Invalid unit/missing-timestamp rows are skipped, not guessed.
- `aqi_ingestion` task now persists the payload it already fetched.

**Provenance:** `source="open-meteo"` stored per row; `observed_at` (provider timestamp, UTC) distinct from `fetched_at` (ingestion time).

**Tests:** 8 mapper unit tests pass (field mapping, unit validation, skip rules). 1 persistence test written, `integration`-marked, **errored — Postgres `:5434` unreachable**; runs in CI with the `db` service.

## AQI ingestion (verified, unchanged)

- Source attribution on every row (`source` column); `observed_at` vs `created_at` distinct; timestamps normalized to UTC; pollutant units converted in the provider layer before persistence; stale readings flagged rather than discarded; OpenAQ client respects 45 rpm / 1700 rph budget with margin.

## KPI formulas (evidence status)

| KPI | Formula (as implemented) | Evidence |
|---|---|---|
| AQI improvement per action | `mean(aqi_before − aqi_after)` over recorded `InterventionOutcome`s — descriptive delta only | `analytics.intervention_outcomes.avg_aqi_improvement`; now writable via API, readable via `/enforcement/outcomes` + `ImpactLedgerCard` |
| Carbon saved | Sum of `carbon_saved_kg` recorded on outcomes — self-reported estimate field | surfacing in outcome schema; **no causal design** — labeled accordingly |
| Data freshness | observed_at age → live ≤10 min, recent ≤2 h, stale >2 h | `data_freshness.py` + `DataFreshnessIndicator` share thresholds |
| Waste-burning → collection | state machine in enforcement actions (status transitions + timestamps + actor) | transitions verified in Week-2 audit; outcome recording now closes the loop on `completed` actions |

## Missing/stale/duplicate policy

| Case | Handling |
|---|---|
| Missing AQI | excluded from ML eval scoring; freshness badge → "Unavailable" |
| Duplicate (city, observed_at, source) weather | upsert refresh, no dup rows (`uq_weather_city_time_source`) |
| Out-of-order weather timestamps | keyed by `observed_at`, not arrival order |
| Invalid units | skipped at mapper, logged; never unit-guessed |
| Stale provider read | flagged `is_stale` on AQI rows; freshness UI degrades label |

**Blocked:** live end-to-end persistence proof needs Postgres; ingest→query round-trip is CI-only today.
