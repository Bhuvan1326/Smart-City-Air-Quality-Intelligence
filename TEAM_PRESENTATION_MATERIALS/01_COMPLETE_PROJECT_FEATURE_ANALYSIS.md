# Complete Project Feature Analysis — Evidence-Based

Smart City Air Quality Intelligence Platform · Next.js 15.5.27 + FastAPI + PostgreSQL/TimescaleDB/PostGIS + Redis + Docker Compose.

## Verified scale
47 frontend routes · 121 endpoints / 36 routers · 29 DB tables · 4 roles · 4 seeded accounts · 12+ background jobs · 8 verified-working providers.

## A. AQI Data & Monitoring (VERIFIED)
- OpenAQ v3 integration: discovery (`discover-india` job), measurement ingest (`ingest-india`), Pune curated ingest (1m), live-aqi (10m). 775 stations, 33 states (coordinate-derived state via `india_state_lookup.py` + embedded `india_states.geojson`), 19+ real readings, `quality_flag` real/synthetic/stale/invalid separation enforced.
- Routers: `aqi.py` (live, history, stations, india/{heatmap,states,observations}, health-risk), `sensors.py`, `data_sources.py`.
- Weather: Open-Meteo ingest job (15m) → `weather_measurements`.
- Tables: `monitoring_stations` (openaq_location_id, PostGIS geometry), `aqi_readings`, `weather_measurements`.

## B. Maps & Geospatial (VERIFIED core, PARTIAL analytics)
- India AQI map (markers, popups, state/category/source filters, retry-on-network-fail), heatmap (station markers, hotspots, anomalies, Nugen "Explain with AI" panel), GIS router (`stations/map`, `pollution-hotspots`, `hotspot-clusters`, `ward-boundaries`, `nearest-stations`, `buffer-analysis`, exposure map).
- PostGIS spatial ops (`gis/operations.py`), Pune ward GeoJSON, emission-source clusters.
- Mapbox GL JS 3.8 — hardened lifecycle (isStyleLoaded guards, map.stop on error, retry).

## C. Forecasting, Analytics & Attribution
- XGBoost city-level AQI forecast (registry `xgb-20260910_0348`, chronological split, statistical fallback). **Station-level BLOCKED** (1–2 real obs/station).
- Attribution router (`/attribution/live`, `/history`) — receptor model v1.2, ward %s, case-insensitive city, live-fallback labeled estimate.
- Analytics: comparison, trends, dispersion, KPI, metrics, model-performance, exposure, simulator, replay.
- Status: COMPLETE city forecast + attribution; PARTIAL analytics depth; DEMO-ONLY exposure.

## D. AI & Agents
- Nugen aligned Qwen2.5-0.5B (`model_01m6xbrq3n8fa8kk`) — DEPLOYED, real inference through `/ai/air-quality-insights` + `/ai/nugen-status`; frozen validation (`insight_validation.py`: numeric provenance, pollutant identity, units, CPCB band, exercise safety, surgical correction); 8-scenario eval evidence.
- Gemini assistant (`/assistant/chat`) — real inference, graceful 503.
- LangGraph agents — framework exists, analyst-gated, PARTIAL.
- Anthropic — key configured, unverified usage.

## E. Environmental & Sustainability
- Routers: heat, energy, water, waste_burning, waste_circularity, construction_dust, industrial_pollution, traffic, green_infrastructure, sustainability, mobility/smart-mobility, environmental.
- Satellite: NASA FIRMS (working), satellite_features job, `satellite_observations` table; Sentinel Hub INVALID creds.
- Status: PARTIAL — pages + endpoints exist; data depth varies (heat readings seeded; energy CSV; some estimated).

## F. Civic, Enforcement & Field Ops
- Routers: civic (issues, clusters, escalation, evidence, status events — role/city-scoped), enforcement (actions, evidence, officers), alerts (thresholds admin, citizen alerts, mitigation), notifications, drone, media_links.
- Tables: civic_issues(+events,clusters), enforcement_actions, officer_routes, drone_flight_plans, citizen_alerts, alert_thresholds, notifications, intervention_outcomes, audit_logs.
- Status: PARTIAL — real role-scoped flows + media storage verified; field workflows less exercised.

## G. Admin, Auth & Platform
- Auth: JWT access+refresh rotation, bcrypt, role deps (CurrentUser, RequireAdmin/Staff/Analyst/InspectorOnly), login throttle, rate-limit + audit middleware.
- Roles: city_administrator, pollution_control_officer, field_inspector, citizen. Seeded: admin@pune.gov.in, officer@mpcb.gov.in, inspector@pune.gov.in, citizen@pune.in.
- NEW admin router (`/admin/*`): errors list/summary (from audit_logs), users/statistics, system/statistics, system/health, audits — RequireAdmin, verified live.
- Reports, transparency, dashboard, kpi, metrics, data_sources, settings.
- Audit evidence: security_audit.json + api_reliability_audit.json persisted (real findings: 0 critical, 1 high, 3 medium, 2 low).

## Cross-cutting data truth
Real (19+ OpenAQ, growing), synthetic (2,028 flagged), model-derived (attribution/forecast). Separation enforced at query + UI layers.
