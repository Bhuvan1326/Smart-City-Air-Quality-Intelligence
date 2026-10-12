# Integration Blockers and Cross-Module Dependencies

| # | Item | Affects | Owner | State |
|---|---|---|---|---|
| B1 | **Open decisions assumed, not confirmed.** (a) Demo users off in production by default; (b) training-target/split fix applied to training code only; (c) frontend aligned to backend roles (not the reverse). Please confirm or reverse. | Rohan, Bhuvan, Adwait | Aryan | Needs confirmation |
| B2 | No `.git` in the delivered zip, so working-tree state and authorship of existing changes could not be recorded. A local baseline commit was made in the sandbox only. Real branches/PRs require the actual repository. | All | Aryan | Blocked |
| B3 | TimescaleDB not available in the sandbox: 10 integration tests (history/`time_bucket`) cannot run. Same 10 fail before and after changes. | Vinyak, Aryan | Aryan | Environment |
| B4 | No training or evaluation data (no DB snapshot, no readings export). Baseline MAE/RMSE cannot be produced. | Bhuvan | Vinyak (data export) -> Bhuvan | Blocked |
| B5 | No OpenAQ/other API credentials or network access to providers: ingestion, units and freshness behaviour could not be observed live. | Vinyak | Vinyak | Blocked |
| B6 | `crewai` and `weasyprint` not installed (very heavy); agent/PDF paths not tested. | Rohan, Bhuvan | Aryan | Environment |
| B7 | Existing model artifacts (9 files) were trained with the defective target/split (see forecasting audit) and should be treated as unvalidated until retrained and evaluated. | Bhuvan, Adwait (forecast UI) | Bhuvan | Open |
| B8 | A citizen community feed was removed; if the product needs it, the API contract (no reporter id/photo) must be agreed before building. | Aryan, Adwait, Rohan | Aryan | Decision |
| B9 | Production Prometheus scraping (if any) must receive `METRICS_TOKEN`; deployment config is out of scope this week. | Rohan | Aryan | Note |
| B10 | Forecast responses lack a `source` (model vs fallback) field; frontend cannot warn users. | Bhuvan, Adwait | Aryan | Proposed contract change |

## Proposed integration process (for the team to adopt)
- One branch per owner per module (`week1/<owner>/<topic>`); PR title lists touched contracts.
- Any change to `schemas/*`, `models/*`, `db_migrations/*`, `deps.py`, or `lib/api/services.ts` requires Aryan plus the module owner as reviewers.
- Required before merge: backend `pytest` (incl. integration where DB available), frontend `npm test`, `tsc --noEmit`, eslint, black/isort/ruff on touched files (CI already runs lint/tests; confirm).
- New migration numbers are allocated by Aryan to avoid collisions (25 migration files today).
