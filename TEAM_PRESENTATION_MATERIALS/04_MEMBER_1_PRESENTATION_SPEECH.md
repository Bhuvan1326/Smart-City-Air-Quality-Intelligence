# Member 1 — Data Ingestion & Geographic Intelligence

## 1. Introduction
"My responsibility is the data-ingestion and geographic-intelligence layer — the foundation every other module stands on. I'm the reason the map shows *real* stations with *real* readings: I built the pipeline that discovers OpenAQ monitoring locations across India, maps them into our database, derives their state from coordinates, and continuously ingests measurements. Nothing on the dashboard exists without this data flowing in."

## 2. Overall Functionality
- **OpenAQ discovery & ingest**: scheduled jobs discover India-wide locations and pull latest measurements; a curated 1-minute job handles Pune's 8 canonical stations (SPPU, Hadapsar, etc.).
- **Station mapping**: each location gets an `openaq_location_id`, PostGIS geometry, and provenance fields — no duplicates (idempotent adoption).
- **State derivation**: OpenAQ doesn't expose state, so I built `india_state_lookup.py` — pure-Python ray-casting over 36 real state/UT polygons — giving every one of 775 stations a real state (plus a 25km coastal fallback).
- **Provenance**: every reading carries `quality_flag` (good/stale/synthetic/invalid) — the whole platform's real-vs-demo honesty comes from this one field.
- **Geographic surfaces**: India AQI map (775 stations, live state/category/source filters), heatmap with hotspot clustering, PostGIS operations (nearest-station, buffer analysis, ward boundaries).

## 3. Technical Implementation
FastAPI `aqi.py` + `gis.py` routers over SQLAlchemy async; PostGIS `ST_*` spatial queries in `gis/operations.py`; background scheduler with Redis locks and OpenAQ rate-limit handling; Mapbox GL JS 3.8 with hardened lifecycle (isStyleLoaded guards, `map.stop()` on style-fetch failure, retry).

## 4. Workflow
OpenAQ API → scheduled ingestion (locked, rate-limited, deduplicated) → validate coords+units → `aqi_readings`/`monitoring_stations` → REST endpoints → React Query → Mapbox markers/popups/filters.

## 5. Integration
Every member consumes my data: M2 forecasts on `aqi_readings`, M3 explains my stations, M4 correlates weather, M5 geo-scopes issues, M6 reports coverage stats.

## 6. Status & Limitations
Working end-to-end: 775 stations, 33 states, real readings flowing. Honest limits: real observation *density* is still accumulating (needed for historical depth + real hotspots, which currently return an honest empty rather than fabricate); `city` uses OpenAQ locality verbatim.

## 7. Demo Script
Open `/dashboard/air-quality?module=india` → show 775 markers + 33-state dropdown → filter to Maharashtra → click SPPU → real AQI, timestamp, OpenAQ provenance → switch to `heatmap` → hotspot layer + "Explain with AI".

## 8. Conclusion
"I turned a provider API into a verified, geographically-accurate national monitoring dataset — the single source of truth everything else reasons over, with honest provenance in every record."
