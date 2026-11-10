# Project Features & User Roles — Summary

A quick-reference companion to `PROJECT_COMPLETE_FEATURE_AND_ACCOUNT_AUDIT.md`.

## What the platform does

Real-time air-quality intelligence for Indian cities: OpenAQ station ingestion → PostGIS storage → role-gated dashboards with maps, forecasts, source attribution, AI explanations and civic/enforcement workflows.

## Headline numbers

| | |
|---|---|
| Frontend routes | 47 |
| Backend endpoints | 121 across 36 routers |
| Database tables | 29 |
| User roles | 4 |
| Seeded accounts | 4 |
| Background jobs | 12+ |
| External providers | 8 verified working |

## The 4 roles — what actually differs

| | Admin | Officer | Inspector | Citizen |
|---|---|---|---|---|
| AQI/maps/insights | ✓ | ✓ | ✓ | ✓ |
| Analytics + simulator + agents | ✓ | ✓ | — | — |
| Enforcement | manage | create/manage | evidence only | — |
| Civic issues | all | all | assigned | own city + own |
| Admin config (users/wards/thresholds) | ✓ | — | — | — |

- **Admin** (city_administrator): everything + system config.
- **Officer** (pollution_control_officer): analyst suite + enforcement, no admin config.
- **Inspector** (field_inspector): field evidence/inspections, ward-scoped, no analyst suite.
- **Citizen**: public dashboards, own-city civic issues, notifications.

## Seeded demo accounts

`admin@pune.gov.in` · `officer@mpcb.gov.in` · `inspector@pune.gov.in` · `citizen@pune.in` — all Pune, password via `DEMO_USER_PASSWORD`.

## Feature status at a glance

- **Working end-to-end:** auth, India AQI map (775 stations, 33 states), heatmap, sources/attribution, Nugen insights, XGBoost city forecast, OpenAQ ingestion.
- **Working but thin real data:** historical analysis, analytics, exposure, real hotspots — enforced real-vs-synthetic separation means they run demo until OpenAQ history builds.
- **Configured, unverified:** Anthropic, energy provider, LangGraph agents.
- **Broken config:** Sentinel Hub (bad creds), Firebase (missing file), SMTP (host unresolvable).

## One-line status

Infrastructure is solid and honestly labeled; the limiting factor is real-data density, which the running scheduler accumulates daily.
