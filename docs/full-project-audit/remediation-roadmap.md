# Remediation Roadmap — prioritized, acceptance-criteria attached

## Done this cycle (verified)

| # | Item | Result |
|---|---|---|
| R2 | npm vulns | **RESOLVED differently than planned** — postcss override fixed all real findings; `next@16` upgrade proven unnecessary (was npm's false `fixAvailable` suggestion) |
| R3 | pip-audit triage | **DONE** — 173→46; every package dispositioned (fixed/deferred/blocked/accepted) |
| R8 | Lockfile warning | **DONE** — `outputFileTracingRoot`; stray root package.json flagged to owner |
| R9-partial | Rate-limit multi-replica | **DOCUMENTED** — Redis-healthy path already distributed; outage fallback per-process accepted-risk |
| R10 | Correlation IDs + metrics | **DONE** — middleware + bounded labels + 13 tests |
| R11 | Password reset | **DEFERRED** — documented decision (no delivery channel exists) |
| — | City Action Brief | **DEFERRED** — documented decision (no spec exists) |

## Remaining — ordered by risk

| # | Item | Sev | Acceptance criterion | Owner |
|---|---|---|---|---|
| R1 | Docker-capable run: 261 integration tests, live schema-drift, real coverage | P1-blocking | suite green, ≥80%, drift clean | infra/CI |
| R13 | FastAPI 0.115→0.14x + starlette 0.47+ | P2 (14 vulns) | upgrade + full regression green | backend lead decision |
| R14 | Agents-stack majors (langgraph/checkpoint/sdk, langchain-core, crewai→mcp/json-repair) | P2 (22 vulns) | crewai/langgraph compat matrix + agents tests green | agents owner |
| R6 | Real-data ML eval | P2 | ≥35d ingestion → eval artifact w/ real provenance | data/ML |
| R7 | Playwright E2E in CI | P2 | browsers + stack + spec green | QA |
| R5 | In-handler→declarative deps swap | P4 | ruff+tests green | backend |
| R12 | Live Twilio verification | P4 | sandbox creds end-to-end | integrations |
| R15 | Remove stray root package.json/lock | P4 | warning already gone; tidy | repo owner |
| R16 | chromadb monitoring | P4 | no fix exists; watch upstream | agents owner |

## Standing rules for all remediation

- Every fix ships with a regression test; integration-dependent fixes marked `integration`.
- No coverage-threshold lowering, no broad exclusions, no test-weakening.
- Secrets stay out of code/logs/fixtures.
- Blocked checks stay BLOCKED with the exact unblock requirement — never re-labeled.
