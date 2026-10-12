# Week 2 Starting-State Report

Verified at the start of Week 2 (not assumed from the Week 1 report).

| Check | Result |
|---|---|
| Repository | Working copy of the uploaded zip. The zip never had `.git`; a **local-only** git history exists in the sandbox (baseline snapshot -> "week1" -> Week 2 checkpoints). No remote, nothing pushed. Real branches/PRs need the actual repository. |
| Week 1 code present | Yes: `civic.py` citizen scoping, `drone.py` staff gate, `should_seed_demo_users`, metrics token, `build_training_frame`/`chronological_split`, `role-policy.ts`. |
| Week 1 docs present | Yes: 13 documents in `docs/week-1/` + `tools/`. |
| Week 1 tests re-run this session | 23 new Week 1 tests (`test_week1_data_ml.py`, `test_week1_rbac_regression.py`): **23 passed**. |
| Full Week 1 baseline (851 pass / 10 fail) | **Not blindly trusted.** The full suite was re-run at the end of Week 2 (see completion report). |
| Cause of the "10 Timescale failures" | **Correction to Week 1:** they were specific to the Week 1 sandbox (no TimescaleDB). The repository's `.github/workflows/ci.yml` already used `timescale/timescaledb-ha:pg16` and `CREATE EXTENSION timescaledb`. Whether those 10 tests pass in real CI is **still unverified** (CI was not run). |
| Week 1 findings status | S1, S2, S3(partial), S4, S5, D2, M1-M3 fixed in Week 1; remaining status in `security-findings-status.md`. |
| Week 1 assumption B1 | Still **unconfirmed by a stakeholder** (a bare "Continue" is not approval). See `decisions-and-contracts.md`. |
| Environment limits (unchanged) | No provider credentials or provider network; no real historical data; no TimescaleDB; no browser binary (Playwright CDN blocked); `crewai`/`weasyprint` not installed. |
