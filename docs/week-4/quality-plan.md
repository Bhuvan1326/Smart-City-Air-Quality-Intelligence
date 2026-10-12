# Week 4 — Quality Plan

**Baseline:** `main` @ ff33c0f + uncommitted Week-3 implementation (weather writer, rate-limit hardening, WS authz, outcome API, ImpactLedgerCard, eval artifact). Verified this session: 124 routes, contract check 93 calls / 0 errors, W3 tests 24/24, frontend 49/49, tsc + build + lint clean.

## Quality-gate acceptance criteria

| Gate | Criterion | Evidence source |
|---|---|---|
| Backend static | compileall + black + isort + ruff all clean | this-session runs |
| Backend tests | non-integration lane green; integration lane green **or explicitly BLOCKED** with the missing service named | pytest runs |
| Coverage | honor the repo's `--cov-fail-under=80` — do not lower | pytest cov report |
| Frontend | tests green, tsc clean, eslint clean, `next build` success | npm scripts |
| Contract | OpenAPI regen + `contract:check` 0 errors | openapi.json + checker |
| Security | regression tests for W3 fixes green; residual risks enumerated | test_week3_* |
| ML | eval pipeline reproducible on fixture; real eval BLOCKED | walk_forward_results.json |
| Release verdict | PASS / PASS-WITH-BLOCKERS / NOT-READY, evidence-backed | final-test-report.md |

## Priorities

1. **P0 — verify no W3 regressions**: full non-integration rerun (in progress this session).
2. **P1 — defect register**: consolidate audit + W3 residual defects with status.
3. **P2 — demo readiness**: script + checklist + limitations; fallback labeling.
4. **P3 — classify the 2 Redis-lane failures**: they are environment failures (connect refused), but the tests should be `integration`-marked so the unit lane stays truthful — flagged for W5.

## Known infrastructure caps (do not fake)

No Postgres/PostGIS/TimescaleDB, Redis, Docker, or Playwright browsers locally. Everything requiring them is BLOCKED with the unblock requirement recorded, per the integration report.
