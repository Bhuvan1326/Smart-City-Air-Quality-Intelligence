# Historical Geographic Data Audit — 2026-11-08 (verified counts)

## Real vs synthetic observations

| Flag | Count | Stations | Time span |
|---|---|---|---|
| `good` (real, fresh) | 13 | 11 | 2026-11-08 10:15–11:30 UTC |
| `stale` (real, old) | 6 | 6 | one 2018 outlier + today 10:15 |
| `synthetic` (demo) | 2,028 | 12 | 2026-11-01 → 11-08 (seeded 7d) |
| **Real total** | **19** | ~12 | ~90 min of coverage |

## Per-station real readings

PUNE_LIVE_*: 1–2 readings each (SPPU 2, Dhankawadi 2, Hadapsar 2, Katraj 2, Nigdi 2, Park St Wakad 2, Gavalinagar 1, Bhumkar 1). OPENAQ_IN_* discovered stations: 0–1 each. **775 stations mapped to OpenAQ IDs**; only ~12 have real readings so far.

## Pollutant coverage (real)

pm25=19, pm10=19, no2=19, co=18, o3=18, so2=11, aqi=19. AQI range 57–391, mean 143.2.

## Findings

- **Real data exists and is honestly labeled** — `good`/`stale` flags distinguish it from `synthetic` end-to-end.
- **Coverage is thin**: ~90 minutes of real observations, 1–2 per station. Ingestion is appending (counts grew 9→19 during the session) but needs days to build history.
- **Station-level XGBoost: BLOCKED — insufficient data.** 1–2 observations/station vs. the hundreds needed for lag/rolling features + train/test split. No defensible model can be trained; city-level model preserved untouched.
- **Real hotspots: honest empty.** Min spatial+temporal supporting stations not met (≤2 obs/station, scattered times).
- **Historical analysis: works but shallow** — `/aqi/history` returns the real window; multi-day trends not yet possible on real data (demo mode covers 7d synthetic, clearly labeled).
- One `stale` real reading is dated **2018** — an upstream OpenAQ artifact, correctly excluded from live surfaces by freshness.
