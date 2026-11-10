# Member 4 — Environmental & Sustainability Intelligence

## 1. Introduction
"I own the environmental context layer — the factors that *cause* and *interact with* air pollution: weather, heat, energy, water, waste, construction dust, industrial emissions, traffic, and satellite fire observations. AQI alone tells you air is bad; my module helps explain why and from where."

## 2. Overall Functionality
- **Weather pipeline**: Open-Meteo ingestion every 15 minutes into `weather_measurements` — temperature, humidity, wind feeding dispersion logic.
- **Heat monitoring**: `heat_readings` + the `/dashboard/heat` page — urban heat-island tracking.
- **Energy & water**: energy intelligence and city water resources dashboards.
- **Waste**: burning incidents + circularity metrics.
- **Construction dust & industrial pollution**: site/source registries feeding the emission-source hotspot layer.
- **Traffic & mobility**: traffic-pollution, mobility and smart-mobility pages.
- **Satellite**: NASA FIRMS fire observations (verified working) into `satellite_observations`; Sentinel Hub configured but its credentials are currently invalid — reported honestly.
- **Green infrastructure & sustainability**: recommendation + metrics surfaces.

## 3. Technical Implementation
Each domain has its own FastAPI router (`heat.py`, `energy.py`, `water.py`, `waste_burning.py`, `waste_circularity.py`, `construction_dust.py`, `industrial_pollution.py`, `traffic.py`, `green_infrastructure.py`, `sustainability.py`) over dedicated tables, plus a `fetch-satellite-features` background job. Frontend pages share the dashboard design system.

## 4. Workflow
Provider data (Open-Meteo/FIRMS) or registries → ingestion/persistence → domain endpoints → environmental dashboards → cross-linked into AQI context.

## 5. Integration
My weather data feeds M1's freshness context and M2's dispersion features; emission sources feed M1's hotspot clusters; my dashboards reuse M6's auth.

## 6. Status & Limitations
PARTIAL overall — weather + FIRMS pipelines verified; several domains have varied data depth (some estimated/seeded). Sentinel Hub credentials are **invalid** (OAuth 401) — satellite imagery path is config-broken, stated openly rather than hidden.

## 7. Demo Script
`/dashboard/environmental` → weather indicators → `heat` → ward heat readings → `sources`/industrial → emission sources → `green-infrastructure` recommendations.

## 8. Conclusion
"I give the platform its environmental situational awareness — the 'why' behind the AQI number, honest about which feeds are live and which need real credentials."
