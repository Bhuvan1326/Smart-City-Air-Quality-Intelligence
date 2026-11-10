# Complete Presentation Guidelines

## Recommended order (data flows top→down, so present upstream→downstream)

1. **Member 6** (2–3 min intro): platform purpose, roles, auth — *who uses it and how it's secured*.
2. **Member 1**: where the data comes from — OpenAQ → stations → map.
3. **Member 2**: what we compute — forecast + source attribution + analytics.
4. **Member 3**: how the AI explains it safely — Nugen + validation + assistant.
5. **Member 4**: environmental context — weather/heat/waste/satellite.
6. **Member 5**: closing the loop — civic issues → enforcement → notifications.
7. **Member 6** (optional close): admin monitoring + audit evidence.

## Handover lines
- M6→M1: "Now that you know who's on the platform, here's where the data comes from."
- M1→M2: "Those measurements only matter once we model them — Member 2."
- M2→M3: "Numbers are half the story — here's the AI that explains them."
- M3→M4: "Explanations need context — the environmental factors."
- M4→M5: "Understanding leads to action — the civic enforcement loop."
- M5→M6: "All of it runs on the admin platform Member 6 secured."

## Avoid duplication — single-owner rules
- OpenAQ/stations/map → **only M1**.
- XGBoost/attribution/analytics → **only M2**.
- Nugen/Gemini/agents → **only M3**.
- Weather/heat/environmental pages → **only M4**.
- Civic/enforcement/notifications → **only M5**.
- Auth/roles/admin/audit/infra → **only M6**.
- Shared items (`aqi_readings`, quality_flag, audit middleware): credit once, don't re-explain.

## Demo flow (single continuous walkthrough)
1. Login (`admin@pune.gov.in`) → dashboard lands.
2. `air-quality?module=india` → 775 stations, 33-state filter, click SPPU → real reading+provenance.
3. `air-quality?module=heatmap` → hotspots layer + station "Explain with AI".
4. `forecast` → XGBoost city forecast + model version.
5. `sources` → real ward attribution %s.
6. `ai` → Nugen status + insight.
7. `environmental`/`heat` → context modules.
8. `citizen`→issue → `officer`/`enforcement` (role-switch login).
9. `administration?module=admin` → health, errors, user stats, audit status.

**Timing:** ~35–45 min total (6×~7 min + demo + Q&A).

## Facts everyone should know
- Stack: Next.js 15 + FastAPI + Postgres/Timescale/PostGIS + Redis + Docker.
- 121 endpoints, 29 tables, 4 roles, 775 stations/33 states.
- Real vs synthetic `quality_flag` separation is a *feature* — be ready to explain it.
- Deployed Nugen model `model_01m6xbrq3n8fa8kk` + frozen validation.
- XGBoost `xgb-20260910_0348`; station forecast BLOCKED (honest).
- Broken configs to own if asked: Sentinel creds, Firebase path, SMTP host.
- Never claim a feature works unless it's in the audit's COMPLETE list.
