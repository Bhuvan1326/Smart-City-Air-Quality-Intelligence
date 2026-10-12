# Data Ingestion & Provider Audit

## Provider inventory

| Provider | Purpose | Auth | Rate budget | Timestamp/unit handling | Persist → | Failure behavior |
|---|---|---|---|---|---|---|
| OpenAQ | AQI obs | API key (env) | 45 rpm / 1700 rph + margin | obs_ts vs created distinct; unit conversion in provider layer; UTC | `aqi_measurements` | cycle skipped + logged, no partial write |
| Open-Meteo | hourly weather fc | none | per-task (900s cadence) | `observed_at` provider UTC vs `fetched_at` ingest; fields mapped °C/%/kmh/hPa/mm/WMO | `weather_measurements` upsert | provider failure → 0 rows logged, not guessed |
| Twilio | IVR calls/SMS | env creds (disabled by default) | n/a | HMAC-SHA1 sig verify, external callback URL | notifications | signature fail-closed |
| FCM | push | env | n/a | — | notifications | dispatcher error path |
| MODIS/FIRMS + Sentinel | satellite evidence | env | n/a | — | evidence records | provider try/except |
| Energy/water/traffic providers | module feeds | env/config | per-provider | per-module units | module tables | per-provider |

## Ingestion-quality guarantees (verified)

| Property | Mechanism |
|---|---|
| Provenance | `source` column on AQI + weather rows |
| Obs vs ingest time | `observed_at` vs `fetched_at`/`created_at` distinct |
| TZ | UTC normalization at mapper/provider layer |
| Units | provider-specific conversion before persistence; unsupported units skipped not guessed |
| Dedup/idempotency | weather unique-key upsert; AQI source+ts keys |
| Invalid/missing | mapper skip-rules; nulls stored as null, never fabricated |
| Stale | `is_stale`/`stale_since` flags (migration 024); freshness badge degrades to "Stale"/"Unavailable" — **stale never renders as "Live"** |
| Out-of-order | keyed on `observed_at` not arrival order |
| Synthetic | `is_synthetic` flag end-to-end → "Demo data" label |

## Honest-state verification

`DataFreshnessIndicator` shares thresholds with `data_freshness.py` (live ≤10m, recent ≤2h, stale >2h) — labels match API semantics. No path found that re-labels fixture data as live.

## Live-call caveat

**No live provider call was executed** (policy + no credentials/network for paid endpoints). All "implemented" claims are code-path-verified; live ingestion remains BLOCKED-INFRA.
