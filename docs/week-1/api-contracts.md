# API Contracts (as implemented)

Generated from the running app on 2026-10-09 and cross-checked against `frontend/lib/api/services.ts`. Field-level request/response schemas are the Pydantic models in `backend/app/schemas/*` and the live `/openapi.json`; they are not duplicated here to avoid drift. Success envelope: `APIResponse[T]`; HTTP errors use FastAPI's default `{"detail": ...}`.

**Auth:** `Authorization: Bearer <access_token>` from `POST /api/v1/auth/login`; refresh via `/auth/refresh`. Absent token -> 403 (`HTTPBearer`), invalid token -> 401, wrong role -> 403 `Access requires one of: [...]`.

**Count:** 115 HTTP route/method pairs under `/api/v1`.

## Endpoint inventory

| Method | Path | Handler | Auth |
|---|---|---|---|
| GET | `/agents/carbon-estimate` | `estimate_carbon` | ADM/OFF |
| GET | `/agents/carbon-estimate/enforcement` | `estimate_enforcement_carbon_impact` | ADM/OFF |
| GET | `/agents/model-registry` | `list_model_versions` | ADM/OFF |
| POST | `/agents/run` | `run_agent_pipeline` | ADM/OFF |
| POST | `/agents/run-graph` | `run_agent_pipeline_langgraph` | ADM/OFF |
| GET | `/agents/status` | `get_agent_status` | ADM/OFF |
| GET | `/alerts` | `list_alerts` | any user |
| POST | `/alerts` | `create_alert` | any user |
| GET | `/alerts/thresholds` | `list_thresholds` | any user |
| POST | `/alerts/thresholds` | `create_threshold` | ADM |
| DELETE | `/alerts/thresholds/{threshold_id}` | `delete_threshold` | ADM |
| PATCH | `/alerts/thresholds/{threshold_id}` | `update_threshold` | ADM |
| GET | `/analytics` | `get_city_analytics` | ADM/OFF |
| GET | `/analytics/comparison` | `get_city_comparison` | ADM/OFF |
| POST | `/aqi/compare-routes` | `compare_routes_endpoint` | any user |
| GET | `/aqi/health-risk` | `get_health_risk` | any user |
| GET | `/aqi/history` | `get_aqi_history` | any user |
| GET | `/aqi/india` | `get_india_aqi` | any user |
| GET | `/aqi/india/heatmap` | `get_india_aqi_heatmap` | any user |
| GET | `/aqi/india/states` | `get_india_states_list` | any user |
| GET | `/aqi/live` | `get_live_aqi` | any user |
| GET | `/aqi/recommend-locations` | `recommend_locations` | any user |
| GET | `/aqi/route-analysis` | `route_analysis` | any user |
| GET | `/aqi/stations` | `list_stations` | any user |
| GET | `/aqi/traffic-pollution` | `traffic_pollution_analysis` | any user |
| POST | `/assistant/chat` | `chat_with_assistant` | any user |
| GET | `/attribution/history` | `get_attribution_history` | any user |
| GET | `/attribution/live` | `get_live_attribution` | any user |
| POST | `/auth/login` | `login` | public |
| POST | `/auth/logout` | `logout` | any user |
| GET | `/auth/me` | `get_me` | any user |
| POST | `/auth/refresh` | `refresh_token` | public |
| POST | `/auth/register` | `register` | public |
| POST | `/civic/escalation/run` | `run_escalation_check` | ADM |
| GET | `/civic/issues` | `list_civic_issues` | any user |
| POST | `/civic/issues` | `submit_civic_issue` | any user |
| GET | `/civic/issues/{issue_id}` | `get_civic_issue` | any user |
| POST | `/civic/issues/{issue_id}/citizen-verify` | `citizen_verify_civic_issue` | any user |
| POST | `/civic/issues/{issue_id}/resolve` | `resolve_civic_issue` | ADM/INS/OFF |
| PATCH | `/civic/issues/{issue_id}/status` | `update_civic_issue_status` | ADM/INS/OFF |
| GET | `/civic/municipalities` | `list_municipalities` | any user |
| POST | `/civic/municipalities` | `create_municipality` | ADM |
| GET | `/civic/representatives` | `list_ward_representatives` | any user |
| POST | `/civic/representatives` | `create_ward_representative` | ADM |
| POST | `/civic/ward-boundaries` | `create_ward_boundary` | ADM |
| GET | `/civic/ward-offices` | `list_ward_offices` | any user |
| POST | `/civic/ward-offices` | `create_ward_office` | ADM |
| GET | `/dashboard/overview` | `get_dashboard_overview` | any user |
| POST | `/drone/plan` | `create_flight_plan` | ADM/INS/OFF |
| GET | `/drone/plans` | `list_flight_plans` | ADM/INS/OFF |
| GET | `/drone/plans/{plan_id}/geojson` | `get_flight_plan_geojson` | ADM/INS/OFF |
| GET | `/energy/fuel-mix` | `get_fuel_mix_endpoint` | any user |
| GET | `/energy/grid-carbon-intensity` | `get_grid_carbon_intensity_endpoint` | any user |
| GET | `/energy/renewable-trend` | `get_renewable_trend_endpoint` | any user |
| GET | `/enforcement` | `list_enforcement_actions` | ADM/INS/OFF |
| POST | `/enforcement` | `create_enforcement_action` | any user |
| GET | `/enforcement/{action_id}` | `get_enforcement_action` | ADM/INS/OFF |
| PATCH | `/enforcement/{action_id}` | `update_enforcement_action` | ADM/INS/OFF |
| POST | `/enforcement/{action_id}/evidence` | `submit_inspection_evidence` | ADM/INS/OFF |
| GET | `/exposure/demographics` | `list_demographics` | any user |
| POST | `/exposure/demographics` | `create_demographics` | ADM |
| PATCH | `/exposure/demographics/{demographics_id}` | `update_demographics` | ADM |
| GET | `/exposure/map` | `get_exposure_map` | any user |
| GET | `/forecast` | `get_city_forecast` | any user |
| GET | `/forecast/{ward_id}` | `get_ward_forecast` | any user |
| GET | `/gis/buffer-analysis` | `buffer_analysis` | any user |
| GET | `/gis/geofence-check` | `geofence_check` | any user |
| GET | `/gis/hotspot-clusters` | `hotspot_clusters` | any user |
| GET | `/gis/nearest-stations` | `nearest_stations` | any user |
| GET | `/gis/pollution-hotspots` | `pollution_hotspots` | any user |
| GET | `/gis/route-optimise` | `optimise_route` | any user |
| GET | `/gis/ward-boundaries` | `get_ward_boundaries` | any user |
| GET | `/green-infrastructure/priority` | `get_green_infrastructure_priority` | any user |
| GET | `/heat/current` | `get_current_heat_assessment` | any user |
| GET | `/heat/forecast` | `get_daily_forecast` | any user |
| GET | `/heat/history` | `get_heat_history` | any user |
| GET | `/heat/hourly` | `get_hourly_forecast` | any user |
| GET | `/heat/wards` | `get_ward_heat_assessment` | any user |
| GET | `/kpi/data-freshness` | `data_freshness_kpi` | any user |
| POST | `/media/signed-url` | `create_signed_url` | any user |
| GET | `/metrics` | `prometheus_metrics` | public |
| GET | `/mitigation/recommendations` | `get_mitigation_recommendations` | any user |
| GET | `/model-performance/active` | `get_active_model_performance` | any user |
| GET | `/model-performance/history` | `get_model_performance_history` | any user |
| GET | `/notifications` | `list_notifications` | any user |
| GET | `/notifications/ivr/{alert_id}` | `ivr_twiml_webhook` | public |
| POST | `/notifications/ivr/{alert_id}` | `ivr_twiml_webhook` | public |
| POST | `/notifications/push-token` | `register_push_token` | any user |
| POST | `/notifications/read-all` | `mark_all_notifications_read` | any user |
| GET | `/notifications/unread-count` | `get_unread_notification_count` | any user |
| DELETE | `/notifications/{notification_id}` | `dismiss_notification` | any user |
| POST | `/notifications/{notification_id}/read` | `mark_notification_read` | any user |
| GET | `/replay/anomalies` | `list_anomalies` | any user |
| GET | `/replay/aqi-history` | `get_aqi_replay_data` | any user |
| GET | `/replay/root-cause-timeline/{anomaly_id}` | `get_root_cause_timeline` | any user |
| GET | `/reports` | `list_reports` | ADM/OFF |
| POST | `/reports/export` | `export_report` | ADM/OFF |
| GET | `/sensors/health` | `list_station_health` | any user |
| GET | `/sensors/{station_id}/health/history` | `station_health_history` | any user |
| GET | `/simulator/scenarios` | `list_scenarios` | any user |
| GET | `/simulator/twin/dispersion` | `digital_twin_dispersion` | any user |
| POST | `/simulator/whatif` | `run_whatif` | ADM/OFF |
| GET | `/sources/construction-dust-risk` | `get_construction_dust_risk` | any user |
| GET | `/sources/industrial-risk` | `get_industrial_pollution_risk` | any user |
| GET | `/sustainability/score` | `get_sustainability_score` | any user |
| GET | `/system/data-sources` | `get_data_sources_status` | any user |
| GET | `/traffic/correlation` | `get_traffic_correlation` | any user |
| GET | `/traffic/current` | `get_current_traffic` | any user |
| GET | `/waste-burning/events` | `get_waste_burning_events` | any user |
| GET | `/waste/circularity` | `get_waste_circularity` | any user |
| GET | `/water/current` | `get_current_water_climate` | any user |
| GET | `/water/history` | `get_water_history` | any user |
| GET | `/water/resource` | `get_water_resource` | any user |
| POST | `/water/resource` | `create_water_resource` | ADM |
| PATCH | `/water/resource/{resource_id}` | `update_water_resource` | ADM |

## Frontend <-> backend consistency check (mechanical)

Method: regex-extracted every helper call (`get/post/patch/del/...`) in `frontend/lib/api/services.ts` (84 distinct calls), normalised path parameters, and compared with the runtime route table. **Result: all 84 match an existing backend path and HTTP method.** (One apparent miss, `POST /civic/escalation/run${city ...}`, is a regex artefact of a template literal containing an inline query; the backend route exists.) This verifies **paths and methods only**. Field-level shapes were not diffed (open item).

Backend routes with no caller in `services.ts` (informational): `/agents/run-graph`, `/aqi/india`, `/aqi/stations`, `/auth/refresh` (axios interceptor), `/civic/{escalation/run,municipalities,representatives,ward-boundaries,ward-offices}`, `/drone/*`, `/enforcement/{id}/evidence`, `/gis/*`, `/metrics`, `/notifications` (list), `/notifications/ivr/{id}`, `/notifications/push-token`, `/reports/export`, `/sensors/health*`, `/ws/live/{city}`. Some are called from components outside `services.ts`; not individually verified.

## Contract changes made in Week 1

| Endpoint | Change | Compatibility |
|---|---|---|
| `GET /civic/issues` | Citizens always receive only their own reports; `only_mine` ignored for citizens | Schema unchanged. Behavioural change for citizens only; the UI toggle was removed accordingly. |
| `/drone/plan`, `/drone/plans`, `/drone/plans/{id}/geojson` | 403 for citizens (previously any authenticated user) | No frontend caller exists. |
| `GET /metrics` | Requires `Authorization: Bearer $METRICS_TOKEN` if set; 404 in production if unset | Dev unchanged. A production Prometheus scraper must be given the token. |
| App startup | Demo users no longer seeded in production unless `SEED_DEMO_USERS=true` | Dev/staging unchanged. |

## Forecast contract (defects in `forecasting-audit.md`)

- Served by `app/ml/inference.py` from the newest `ml_models/xgb_forecast_*.joblib`; **statistical fallback** if no artifact loads.
- Target: ward-level **AQI** (CPCB-style index, unitless, 0-500), 1-hour model applied **recursively** to reach horizon *h*. Spatial unit: ward id (`W01`...).
- Model input, 8 features, positional (artifacts store no feature names; `n_features_in_ = 8` verified on the shipped files): `[current_aqi, hour_of_day, day_of_week, is_weekend, is_industrial, temperature, humidity, wind_speed]`. Training (`workers/tasks/forecast.py`) and inference use the same order.
- Response includes `predicted_aqi`, a **heuristic** confidence and interval (not calibrated) and `pm25_forecast` (= 0.55 x AQI; not a measured conversion).
- Unavailable model: statistical fallback, with random noise (non-deterministic). Responses do not say which path produced the value.

## Unresolved contract decisions

1. A privacy-preserving public community issue feed for citizens (no reporter id or photo), since the old All Reports view was removed.
2. Add `source: model|statistical_fallback` and `generated_at` to forecast responses.
3. Standard error envelope.
4. Field-level contract tests (schema diff between `schemas/*.py` and `services.ts`).
