# Geographic Intelligence Baseline (verified 2026-11-08)

## Verified data state

| Entity | Count | Notes |
|---|---|---|
| monitoring_stations | 12 | all `is_active`, all valid `geometry` + lat/lon columns |
| — Pune | 8 | PUNE_001–008, fixture wards W01–W08 |
| — Mumbai | 4 | MUM_001–004 |
| aqi_readings | 2028 | **ALL `quality_flag='synthetic'`** — seeder-generated, last 7 days hourly per station |
| emission_sources | 8 | seeded, real coords, violation counts |
| ward_demographics | 8 | seeded (populations, sensitive sites, green cover) |
| pollution_hotspots table | 0 | table exists, never populated — hotspots computed on demand |
| ward_boundaries / ward_offices | 0 | tables exist, never seeded |
| users | 4 | demo accounts |
| openaq_location_id | NULL on all stations | live ingestion `stations_selected=0`; OpenAQ key also returns 401 |

## Seed failure root cause (fixed)

1. `ensure_demo_users()` ran before `seed_all()`; `seed_all`'s gate was `users > 0 → return` → **everything after users never seeded**.
2. `enforcement_actions.officer_id` NotNullViolation: when no `field_inspector`/`pollution_control_officer` user existed, actions were built with `officer_id=None`. Now guards and skips instead.

Fix (in `seed_all`): gate checks `aqi_readings` instead of `users` (deepest artifact), `_seed_users` skips existing emails, `_seed_enforcement` guards missing officers. Full reseed verified: users/stations preserved (`skipped`), readings/forecasts/attributions/wards/emissions populated.

## Existing surface

- `GET /api/v1/aqi/stations` — paginated station metadata (no readings).
- `GET /api/v1/aqi/live` — provider-station registry (PUNE_LIVE_*), `unresolved` without real ingestion.
- `GET /api/v1/aqi/history` — historical readings.
- `GET /api/v1/gis/pollution-hotspots` — PostGIS clustering of stations with last-hour avg AQI over threshold; **filters out `synthetic`** → empty on demo data (by design).
- `GET /api/v1/gis/hotspot-clusters` — emission-source spatial clusters; **returns real data now** (8 seeded sources).
- `GET /api/v1/exposure/map` — ward exposure scores; **filters out `synthetic`** → empty on demo data (by design).
- `get_latest_by_stations` — bulk latest-reading repo query (no N+1).
- Frontend `/dashboard/exposure` — working Mapbox map (token configured).

## Data quality policy

Existing endpoints deliberately exclude `quality_flag='synthetic'` so demo data is never presented as real. New geographic surfaces expose `data_source`/`quality_flag` provenance explicitly; the UI labels synthetic readings "Demo data". Features requiring real readings are BLOCKED until a valid OpenAQ key + station `openaq_location_id` mapping exist.
