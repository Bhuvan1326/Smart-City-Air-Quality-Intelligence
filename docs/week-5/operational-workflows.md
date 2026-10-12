# Week 5 — Operational Workflows

## Impact Ledger — PARTIAL → functional vertical slice (W3)

| Layer | State | Evidence |
|---|---|---|
| Record outcome | **Real API** — `POST /enforcement/{action_id}/outcome`; admin/officer any action, field_inspector own actions only (404 otherwise); `delta_score` server-computed; `verified_by=current_user`; explicit `confidence_score` | `endpoints/enforcement.py`, contract-checked |
| List outcomes | **Real API** — `GET /enforcement/outcomes`, RequireAnalyst, city-scoped, paginated | 124 routes verified |
| Persistence | `InterventionOutcome` model (pre-existing migration); audit row per recording event | model read |
| Frontend | `ImpactLedgerCard` on `/dashboard/analytics` — loading/empty/error states; "descriptive, not causal" label | component + services.ts client |
| Aggregate KPI | `intervention_outcomes` block in city analytics (avg improvement, total, carbon) | pre-existing, now writable |
| Honesty | deltas are before/after comparisons — **no causal claim**; `carbon_saved_kg` is a self-reported estimate | labeled in UI + docs |
| Remaining gap | outcome recording has no dedicated *form* in the UI (API+list surface shipped; the record-UX is W5+ polish); DB write-path test BLOCKED no-DB | — |

## City Action Brief — NOT IMPLEMENTED (by honest declaration)

Design-document only since Week 2. No endpoint, no worker, no UI. It is **not** shown in the demo as existing; `known-limitations.md` lists it. Building it now would require inventing recommendation logic + data contracts — explicitly out of scope for a hardening week vs. honest non-implementation.

## Waste-burning → collection workflow — VERIFIED (W2 audit)

State transitions, authorized actor, timestamps, and audit records exist server-side (not frontend-mock); outcome recording (W3) now closes the `completed → measured` loop.
