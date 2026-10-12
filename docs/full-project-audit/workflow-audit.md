# Workflow Audit — Alerts, Civic, Impact Ledger, City Action Brief

## Alerts & notifications — IMPLEMENTED-VERIFIED

- Thresholds CRUD is staff-gated (`role_checker`); citizen-facing `POST /alerts` blocks citizens in-handler only where restricted (subscriptions are citizen-appropriate).
- Ownership on read/delete own notifications; unread-count own-scoped.
- Twilio IVR: signature-verified GET+POST (separate handlers — dup-op-ID fixed), fail-closed, external callback URL.
- Audit log middleware covers all mutations.

## Civic reports — IMPLEMENTED-VERIFIED

- Owner+staff visibility scoping server-side; duplicate detection; SLA/escalation tasks; citizen-verify + resolve transitions with authorized actors + timestamps (W2 audit evidence).

## Impact Ledger — VERIFIED-API, PARTIAL-UX

| Check | Evidence |
|---|---|
| Auth | Bearer + role (admin/officer any action; field_inspector own only → 404) |
| Input validation | `RecordOutcomeRequest`: aqi≥0, period 1–720h, confidence 0–1 required (kills silent 0.8 default) |
| Server-computed score | `delta_score = aqi_before − aqi_after` computed on write — **client cannot supply it** |
| Timestamps/baseline | `measurement_period_hours` explicit; `created_at` audit |
| Duplicates | one row per recording event (audit trail semantics, no silent dedup) |
| Provenance | `verified_by=current_user`, `verification_method` required |
| Frontend | `ImpactLedgerCard` — honest states + "descriptive, not causal" |
| Math sanity | delta direction + units consistent (AQI points); per-action scope |
| Persistence | `InterventionOutcome` model (pre-existing migration); write-path test BLOCKED-INFRA |

## City Action Brief — NOT IMPLEMENTED

Design-only since Week 2. No endpoint, worker, or UI. Declared in `known-limitations.md`; not presented as existing anywhere — **honest non-implementation, not a mock**.

## Claims hygiene (sustainability/KPI)

- AQI improvement = mean of recorded deltas — **descriptive**, labeled non-causal in UI + docs.
- `carbon_saved_kg` = self-reported estimate field, surfaced as such.
- No fabricated causal-impact text found in components or endpoints.
- KPI denominators/windows documented in `docs/week-3/data-quality-and-kpis.md`.
