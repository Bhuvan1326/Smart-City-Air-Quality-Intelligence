# Week 5 — Release Readiness Report

Legend: **PASS / FAIL / BLOCKED / PARTIAL / NOT IMPLEMENTED** — every row cites the exact validation or the named blocker.

| Area | Criterion | Status | Evidence / command | Remaining risk | Owner next action |
|---|---|---|---|---|---|
| Backend correctness | unit lane green | PASS | `pytest -m "not integration"` → 716 passed (post Redis-mark fix: the 2 env-fails now deselect) | — | — |
| Backend static gates | compile/black/isort/ruff | PASS | all 4 clean this session | — | — |
| Frontend correctness | tests+tsc+lint+build | PASS | 49/49, tsc 0 err, eslint 0err/12warn, build ok | 2 npm vulns (next@16) | owner decision on major |
| Authentication & RBAC | server-side authz verified | PASS (unit) | 31/31 sec tests incl. PyJWT path; role checks in deps | live cross-ward HTTP probes = integration lane | run CI suite |
| Rate limiting | no fail-open | PASS (unit) | Redis-down tests: auth→503, others→bounded 30rpm | per-process bound ×replicas | Redis HA / distributed counter |
| Login throttling | brute-force bound | PASS (unit) | 5/300s→429, no oracle leak | same replica caveat | — |
| WebSocket authz | per-city for citizens | PASS (unit) | foreign city→4403 | live handshake = integration lane | run CI suite |
| Dependency vulns | advisories addressed | PARTIAL | jose→PyJWT done (PYSEC-2025-185 closed); 167 pip findings + 2 npm remain | unpatched transitives | triaged owner decisions |
| DB migrations & persistence | clean upgrade + drift | BLOCKED | needs `docker compose up db`; CI services configured | unverified in real env | run CI / docker host |
| Weather ingestion | writer exists + provenance | PARTIAL | 8 mapper tests; live write BLOCKED | untested round-trip | CI integration run |
| ML evaluation | reproducible + baselines | PASS (pipeline) / BLOCKED (real data) | `walk_forward_results.json` (synthetic) | no accuracy claim possible | ingest ≥35d → rerun |
| Feature parity / skew | measurable | PASS | evaluator scores both `FORECAST_ALIGN_FEATURES_TO_ORIGIN` variants | flag still default-off | staging eval decision |
| KPI evidence | formulas + provenance | PASS | documented; source/freshness per row | causal claims excluded by design | — |
| Impact Ledger | vertical slice | PARTIAL | API+schemas+client+UI card shipped, contract-clean | record-form UX thin; DB test blocked | CI run + optional form |
| City Action Brief | implemented? | NOT IMPLEMENTED | design-only, declared | absent feature | scope decision |
| API contract integrity | drift checker clean | PASS | 93 calls/1232 fields/0 err post-W3 | — | — |
| CI/CD | services + stages | PASS (config) | ci.yml provisions timescale+redis, migrations, drift, tests | **no run observed** | trigger + inspect a CI run |
| Browser/E2E | role walkthrough | BLOCKED | spec authored; browsers absent | untested journeys in real browser | `playwright install` + stack |
| Observability | health distinguishes deps | PARTIAL | `/health` per-dep status; no metrics/correlation IDs | thin ops surface | metrics export decision |
| Deploy & rollback | documented procedure | PASS (doc) | alembic-versioned, env matrix, seed-gate | unexecuted | dry-run on staging |

## Verdict

**READY WITH BLOCKERS.** Code-complete and locally verified for everything executable without services; all BLOCKED items are infrastructure-bound (Docker/Postgres/Redis/browsers), with tests written and `integration`-marked, CI services already configured. The remaining gate is an observed CI run and — before any real deployment — dependency triage + the `next@16` decision.

## Top 3 next actions

1. **Run the CI workflow** (or `docker compose up` on a Docker host) → execute the 260-test integration lane + live schema-drift + coverage gate to confirm ≥80%.
2. **Owner decisions**: `next@16` major for npm vulns; triage remaining pip findings; approve/cancel City Action Brief scope.
3. **Populate observation data** (≥35 days ingest on the compose stack) → run the real walk-forward eval to replace the fixture-only artifact.
