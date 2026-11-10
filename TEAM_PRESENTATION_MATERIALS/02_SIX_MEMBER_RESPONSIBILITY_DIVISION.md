# Six-Member Responsibility Division

Functional ownership — each member owns a vertical slice (UI + API + data + integration).

## Member 1 — Data Ingestion & Geographic Intelligence
**Scope:** everything that gets real measurements into the platform and puts them on the map.
- Features: OpenAQ discovery/ingest (Pune + India), station mapping (`openaq_location_id`), state derivation (`india_state_lookup.py`), real-vs-synthetic provenance, freshness classification, India AQI map, heatmap, GIS endpoints (stations/map, pollution-hotspots, hotspot-clusters, ward-boundaries, nearest-stations, buffer-analysis), ward boundaries, emission-source clusters, Mapbox layer lifecycle.
- Routes: india-aqi, heatmap, exposure, air-quality(module=india/heatmap)
- Routers: `aqi.py`, `gis.py`, `data_sources.py`; jobs: discover-india, ingest-india, fetch-live-aqi*, fetch-weather
- Tables: monitoring_stations, aqi_readings, weather_measurements, ward_boundaries, emission_sources
- Status: COMPLETE (verified live); real hotspots PARTIAL (data-sparse)

## Member 2 — Forecasting, Analytics & Source Attribution
**Scope:** turning measurements into predictions and pollutant-source breakdowns.
- Features: XGBoost city AQI forecast + registry + statistical fallback, station-forecast feasibility (BLOCKED — insufficient data), attribution live/history + live-fallback, analytics (comparison, trends, dispersion, KPI, metrics, model-performance), exposure (demo), simulator, replay.
- Routes: forecast, analytics, sources, intelligence, exposure, simulator, replay, model-performance
- Routers: `forecast.py`, `analytics.py`, `kpi.py`, `metrics.py`, `model_performance.py`, `simulator.py`, `replay.py`, `exposure.py`, alerts' `attribution_router`
- Tables: forecast_grids, pollution_attributions, policy_snapshots
- Jobs: run-attribution (30m)
- Status: COMPLETE city forecast + attribution; PARTIAL analytics; BLOCKED station forecast

## Member 3 — AI & Intelligent Assistance
**Scope:** all LLM/agent capabilities and their safety guarantees.
- Features: Nugen aligned Qwen2.5-0.5B (`model_01m6xbrq3n8fa8kk`) inference, `/ai/air-quality-insights`, `/ai/nugen-status`, frozen `insight_validation.py` (numeric provenance, pollutant identity, units, CPCB band, exercise safety, surgical correction), geographic station/hotspot explanations, Gemini `/assistant/chat`, LangGraph agents, Anthropic (configured-unverified), 3B challenger (BLOCKED by provider).
- Routes: ai, assistant, agents, dashboard/ai, insights card (heatmap)
- Routers: `nugen_insights.py`, `assistant.py`, `agents.py`
- Status: COMPLETE Nugen + validation + assistant; PARTIAL agents; CONFIGURED Anthropic; BLOCKED 3B

## Member 4 — Environmental & Sustainability Intelligence
**Scope:** environmental context beyond AQI measurements.
- Features: weather pipeline + readings, heat monitoring, energy intelligence, water resources, waste burning/circularity, construction dust, industrial pollution, traffic/mobility/smart-mobility, satellite observations (NASA FIRMS working, Sentinel invalid), green infrastructure, sustainability metrics.
- Routes: heat, energy, water, waste-burning, waste-circularity, construction-dust, industrial-pollution, traffic-pollution, mobility, smart-mobility, green-infrastructure, environmental, sustainability
- Routers: same-named routers + `sensors.py`
- Tables: heat_readings, weather_measurements, emission_sources, satellite_observations, city_water_resources, sensor_health_assessments
- Jobs: fetch-weather, fetch-satellite-features
- Status: PARTIAL (varied data depth; several estimated)

## Member 5 — Civic Engagement, Enforcement & Field Operations
**Scope:** citizen→government action loop.
- Features: civic issues (submit/track/cluster/escalate, role+city scoping), evidence upload, enforcement actions, officer routes/inspections, drone flight planning, citizen alerts, alert thresholds (admin-shared w/ M6), mitigation recommendations, notifications dispatch, officer/citizen dashboards.
- Routes: civic, citizen, officer, enforcement, alert-thresholds, drone/ops, notifications surfaces
- Routers: `civic.py`, `enforcement.py`, `alerts.py` (alerts/thresholds/mitigation), `notifications.py`, `drone.py`, `media_links.py`, `websocket.py`
- Tables: civic_issues(+status_events,clusters), enforcement_actions, officer_routes, drone_flight_plans, citizen_alerts, alert_thresholds, notifications, intervention_outcomes, audit_logs, media files
- Jobs: dispatch-pending-alerts (1m), escalate-overdue-civic-issues (15m), detect-drone-hotspots
- Status: PARTIAL (real flows; field workflows less exercised)

## Member 6 — Identity, Administration & Platform Reliability
**Scope:** who can do what, and whether the system is healthy.
- Features: JWT auth (access+refresh, bcrypt, throttle, rate limit, audit middleware), 4-role RBAC (backend deps + frontend role-policy), seeded users, NEW admin router (`/admin/errors`, `/admin/errors/summary`, `/admin/users/statistics`, `/admin/system/statistics`, `/admin/system/health`, `/admin/audits`), security + API-reliability audits (persisted real findings), reports, transparency, dashboard, settings, data-source status, Docker/CI health.
- Routes: login, admin, administration, reports, transparency, settings, dashboard
- Routers: `auth.py`, `admin.py`, `dashboard.py`, `data_sources.py`, `reports.py`, `kpi.py`/`metrics.py` (shared w/ M2)
- Tables: users, audit_logs, municipalities, ward_demographics/offices/representatives
- Status: COMPLETE auth+admin monitoring; PARTIAL admin UI wiring

## Shared-ownership notes
- `aqi_readings`/`monitoring_stations`: M1 owns write path; M2/M4 read.
- `alerts.py` router file contains attribution (M2) + alerts/thresholds (M5) + live-attribution logic.
- City selector/auth context (`lib/store`): M6 platform; consumed by all.
- `audit_logs`: written by middleware (M6); error surface consumed by M6 admin.
