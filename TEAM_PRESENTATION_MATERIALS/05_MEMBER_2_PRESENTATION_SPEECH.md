# Member 2 — Forecasting, Analytics & Source Attribution

## 1. Introduction
"I own the *predict-and-explain-numbers* module: XGBoost AQI forecasting, the pollution source-attribution model, and the analytics surfaces. If Member 1 brings the measurements, I turn them into 'what will it be tomorrow' and 'where is it coming from'."

## 2. Overall Functionality
- **XGBoost city forecast**: versioned registry (`xgb-20260910_0348`), chronological train/test split (no leakage), statistical fallback when the model is unavailable, forecast horizon with metrics.
- **Source attribution**: receptor model v1.2 — per-ward percentage breakdown (vehicular/industrial/construction/biomass/dust/domestic), `/attribution/live` + `/history`, case-insensitive city matching, and a labeled `model-derived estimate` fallback when records are absent.
- **Analytics**: city/ward comparison, trends, dispersion, KPI, model-performance, exposure analysis, simulator + replay.

## 3. Technical Implementation
`ml/inference.py` registry loads the latest `xgb_forecast_*.joblib` + sidecar metadata; `forecast.py` endpoints; `alerts.py` attribution router; 30-minute `run-attribution` job; React charts (Recharts) on the forecast/sources/analytics pages.

## 4. Workflow
`aqi_readings` (Member 1) → feature build → XGBoost → forecast response → chart; ward AQI → receptor model → per-source % → Sources page cards/pie/ward-table.

## 5. Integration
Depends on M1's real data. M3 explains my forecasts/attributions via Nugen; M6 reports my model's health and audit stats.

## 6. Status & Limitations
City forecast + attribution COMPLETE (verified). **Station-level forecast: BLOCKED** — 1–2 real observations per station vs. the hundreds needed; I documented this honestly rather than train a meaningless model. Exposure is demo-only; deeper analytics need more real history.

## 7. Demo Script
`/dashboard/forecast` → city AQI forecast + model version + confidence → `/dashboard/air-quality?module=sources` → real ward %s (W01: 25.2% vehicular, 41% industrial) → ward table + confidence → `analytics` → trends/comparison.

## 8. Conclusion
"I give the platform its brain for numbers — honest forecasts and defensible source attribution, with the discipline to say 'insufficient data' rather than fabricate."
