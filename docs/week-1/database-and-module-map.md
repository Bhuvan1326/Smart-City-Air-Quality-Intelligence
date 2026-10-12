# Database and Module Map

## ORM tables (28, from `Base.metadata` at runtime) and foreign keys
| Table | FK -> | Domain |
|---|---|---|
| users | – | auth, roles |
| audit_logs | users | security |
| monitoring_stations | – | AQ sources |
| aqi_readings | monitoring_stations | AQ time series (`quality_flag`, hypertable-style queries) |
| anomaly_events | monitoring_stations | AQ |
| sensor_health_assessments | monitoring_stations | AQ |
| forecast_grids | – | forecasts (ward-level) |
| emission_sources | – | enforcement |
| enforcement_actions | emission_sources, users | enforcement |
| intervention_outcomes | enforcement_actions | outcomes (KPI source) |
| drone_flight_plans | users | enforcement |
| civic_issues | civic_issue_clusters, users | civic |
| civic_issue_clusters | – | civic |
| civic_issue_status_events | civic_issues, users | civic workflow audit trail |
| citizen_alerts | – | alerts |
| notifications | citizen_alerts, users | alerts |
| alert_thresholds | – | config |
| officer_routes | users | field ops |
| municipalities, ward_boundaries, ward_offices, ward_representatives, ward_demographics | – | geography / governance |
| pollution_attributions, policy_snapshots | – | analysis |
| satellite_observations | – | external data |
| heat_readings, city_water_resources | – | environmental |

Notes: `citizen_alerts` and `forecast_grids` hold `ward_id` as a string rather than an FK to `ward_boundaries`; `ward_id` consistency is therefore by convention (`W01`...), a shared-schema risk.

## Migrations
25 files in `backend/db_migrations/versions` (`001_initial` ... latest numbered). Practice observed: sequential numeric prefixes. Tests build schema with `Base.metadata.create_all`, **not** by running migrations, so migration/ORM drift is not caught by the suite (open risk, Aryan).

## Ownership (proposed)
| Domain | Tables | Owner |
|---|---|---|
| Auth / RBAC | users, audit_logs | Rohan |
| Ingestion / AQ | monitoring_stations, aqi_readings, anomaly_events, sensor_health_assessments, satellite_observations | Vinyak |
| Forecast | forecast_grids (+ model artifacts) | Bhuvan |
| Civic / alerts / enforcement UI contracts | civic_*, citizen_alerts, notifications, enforcement_*, drone_* | Adwait (UI) / Rohan (access) |
| Shared schema changes, migration numbering | all | Aryan |

## Module map (backend `app/`)
`api/v1/endpoints/*` (routers) -> `services/*` (providers, evidence storage, freshness, planners) -> `models/*` / `schemas/*`; `workers/*` (scheduler, tasks); `ml/*` (inference); `agents/*` (LangGraph); `core/*` (config, security, middleware, seeder, websocket); `tests/*`.
