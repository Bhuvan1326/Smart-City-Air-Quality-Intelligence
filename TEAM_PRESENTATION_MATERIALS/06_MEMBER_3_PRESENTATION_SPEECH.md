# Member 3 — AI & Intelligent Assistance

## 1. Introduction
"I own every language-model capability and — critically — its safety guarantees. My headline is a *production-aligned* Nugen model with a frozen multi-layer validation pipeline that won't let the AI state an AQI that wasn't actually measured."

## 2. Overall Functionality
- **Nugen aligned model**: `model_01m6xbrq3n8fa8kk` (Qwen2.5-0.5B, alignment READY + DEPLOYED) generates air-quality explanations at `/ai/air-quality-insights`.
- **Validation pipeline** (`insight_validation.py`): numeric provenance, pollutant-identity (catches PM2.5↔PM10 swaps), unit checks, deterministic CPCB band, exercise-safety review, missing-data handling, **surgical in-place correction** — invalid claims are fixed or removed, never left beside a correction.
- **Geographic AI**: click a map station → real measurements only → aligned explanation (heatmap "Explain with AI").
- **Gemini assistant**: `/assistant/chat` conversational help, graceful 503 on provider failure.
- **LangGraph agents**: analyst-gated agent framework. Anthropic configured (unverified).

## 3. Technical Implementation
Backend-only `nugen.py` client (key never leaves server); `nugen_insights.py` endpoint runs prompt→inference→validators→validated response with `validation_notes`; 8-scenario eval evidence in `docs/nugen/`.

## 4. Workflow
Select station → real measurements → endpoint → deterministic CPCB band → aligned model → validators → (correct / strip / deterministic fallback) → UI with provenance + corrections noted.

## 5. Integration
Depends on M1's real station data (explains only what exists), M2's forecast context; M6 audits my security (key isolation verified).

## 6. Status & Limitations
Nugen + validation + assistant + geographic insights COMPLETE (real inference, verified). LangGraph agents PARTIAL. Anthropic configured-not-verified. 3B challenger BLOCKED (base not provisioned). Remaining limit: unusual phrasing can evade the name-association regex — conservative fallback covers it.

## 7. Demo Script
`ai` page → `/ai/nugen-status` shows DEPLOYED → ask for insight → validated explanation → open heatmap → click station → "Explain with AI" → real-measurement explanation with provenance.

## 8. Conclusion
"I built the platform's voice — and, more importantly, the guardrails that make its AI trustworthy enough to quote a measurement."
