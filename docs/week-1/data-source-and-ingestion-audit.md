# Data Source and Ingestion Audit (Week 1)

Method: read `core/config.py`, `workers/scheduler.py`, `workers/tasks/aqi_ingestion.py`, `services/aqi_providers/openaq.py`, `services/data_freshness.py`, `core/seeder.py`. **No external API was called** (no credentials, restricted network), so "live" below means "the code path fetches from a live provider when configured", not that live coverage was observed.

## Source inventory
| Source | Role | Live / delayed / static | Credentials | Evidence |
|---|---|---|---|---|
| OpenAQ v3 (`OPENAQ_BASE_URL`) | Station AQI/pollutants | Provider-delayed; code classifies readings older than 2 h as stale | `OPENAQ_API_KEY` | `services/aqi_providers/openaq.py`, `data_freshness.py` |
| Pune station ingestion (`OPENAQ_INDIA_INGEST_INTERVAL_SECONDS`=300, discovery 21600 s) | Pune/India live path | Uses provider `observed_at` as the reading timestamp | same | `aqi_ingestion.py` |
| Legacy 10-minute job (other cities / fixed station list) | Non-Pune | Stamps **ingestion time**, not observation time (D1) | same | `_fetch_aqi_async` |
| Open-Meteo (`OPEN_METEO_BASE_URL`; `OPENWEATHER_API_KEY` optional) | Weather | Provider forecast/current | none for Open-Meteo | `services/weather_provider.py` |
| Traffic (`TRAFFIC_PROVIDER`, empty by default) | Traffic index | Not live unless a provider is configured; fallback behaviour not verified | provider-specific | `services/traffic_provider.py` |
| Electricity (`ENERGY_PROVIDER=auto`, `ENERGY_API_KEY`) | Energy/carbon | Live lookup attempted in `auto`; config comment describes demo mode as explicit opt-in (not verified at runtime) | key | `services/energy_provider.py` |
| NASA FIRMS, Sentinel Hub | Satellite / fires | External, tokens required; not exercised | tokens | `services/satellite/*` |
| **Seeder** (`core/seeder.py`) | Dev data | **Synthetic**: readings flagged `quality_flag='synthetic'` (7-day history), stations, wards, demo users | n/a | seeder |
| `ml_models/*.joblib` | Models | Static artifacts | n/a | repo |

**Sample vs live distinguishability:** readings carry `quality_flag` (`good/stale/invalid/synthetic` observed in code). Serving queries exclude `synthetic` for non-Pune; *training* did not (fixed). The UI uses `FreshnessStatus` (LIVE/STALE/UNAVAILABLE). Not verified: that every UI surface labels synthetic data as such.

## Scheduled tasks (from `scheduler.py`)
Live AQI fetch (10 min), India ingest (5 min) + discovery (6 h), forecast regeneration (code comment says hourly; the interval constant read as 30 min, reconciliation needed), nightly retrain (00:30 IST), escalation and other jobs. Runs **in-process** per API worker; distributed locks via Redis **fail open**, so multiple workers/Redis outage can duplicate jobs.

## Findings
| # | Sev | Finding | Where | Reproduced | Status |
|---|---|---|---|---|---|
| D1 | **Med-High** | Legacy ingestion path writes `timestamp=now`, `quality_flag="good"` regardless of provider `observed_at` / `is_stale` (raw JSON keeps `observed_at`). A stale upstream value looks fresh and is re-inserted every cycle. | `_fetch_aqi_async`, `_build_reading_for_station` | Code read | **Open** (touches ingestion semantics + unique keys; needs live-data test). Owner Vinyak. |
| D2 | Med | `classify_freshness` labelled **future** timestamps LIVE (e.g. a timezone parsing error of +5.5 h). | `services/data_freshness.py` | Yes (test) | **Fixed**: > 5 min in the future -> UNAVAILABLE. Test: `test_freshness_future_timestamp_is_not_live`. |
| D3 | Med | **No unit handling** when parsing OpenAQ parameters. CPCB breakpoints in code treat CO as mg/m3; if the provider returns ug/m3 or ppm, the sub-index clamps to the maximum (500). Gas unit conventions unverified. | `openaq.py` (no unit reference), `aqi_ingestion.py` breakpoints | Not reproduced (no live data) | **Open**; add unit check/convert + rejection of unknown units. |
| D4 | Med | `calculate_overall_aqi` returns 500 (worst) when no pollutant is usable; "no data" is encoded as hazardous. | `aqi_ingestion.py` | Code read | Open (return None/invalid). |
| D5 | Low-Med | AQI uses instantaneous values; CPCB specifies 24 h averages (PM) and 8 h (CO, O3). Label as "instantaneous/NowCast-style" or implement averaging. | `aqi_ingestion.py` | Code read | Open (documentation + KPI caveat). |
| D6 | Low | Duplicate handling relies on DB uniqueness; not verified for the legacy path. | models/ingestion | Not verified | Open |
| D7 | Low | Time zones: DB stores timezone-aware timestamps; schedule uses IST for retrain; UTC hours used by forecast fallback. Convention not documented in code. | various | Code read | Open (documented here). |

## Dependencies between components
ingestion (`aqi_readings`) -> training/inference (`forecast.py`, `inference.py`) -> forecast endpoints -> forecast UI; ingestion -> live AQI endpoints -> maps/cards; ingestion/enforcement -> KPIs (`kpi-definitions.md`).

## Prerequisites for Week 2
Provider credentials and a read-only data export (B4/B5); decision on D1 semantics; unit-contract confirmation with OpenAQ docs/sample payloads; Timescale-enabled CI database to exercise history queries.
