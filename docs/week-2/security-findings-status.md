# Security Findings — Status after Week 2 (Rohan)

| ID | Sev | Finding | Status | Evidence |
|---|---|---|---|---|
| S1 | High | Citizens listed all civic reports | **Fixed (Week 1)** | `test_week1_rbac_regression.py` |
| S2 | High | Drone endpoints open to any user | **Fixed (Week 1)** | same |
| S3 / R1 | High | Demo accounts with published passwords | **Fixed (Week 2)**: no static password in `seeder.py`, README, `.env.example` or the **frontend login bundle** (the login page shipped all four passwords to every browser); password only via `DEMO_USER_PASSWORD`; never logged | `test_week2_demo_seeding.py` (9 + 7 tests) |
| S4 | Med | `/metrics` open | Fixed (Week 1) | `test_week1_data_ml.py` |
| S5 | Med | UI/API role mismatch | Fixed (Week 1); browser verification **written, not run** | `role-policy.test.mjs`, `e2e/role-walkthrough.spec.ts` |
| S6 | Med | IVR webhook unauthenticated | **Fixed (Week 2)**: signature validation, fail-closed, correct external URL; also fixes a latent GET-only/POST-default (405) bug | `test_week2_ivr_signature.py` (9 tests incl. cross-check vs official Twilio SDK algorithm) |
| S7 | Med | Evidence media public | **Fixed (Week 2)**: auth + ownership or short-lived signed link | `test_week2_media_access.py` (6 tests) |
| S8 | Low | Public docs / `/health` error text in production | **Fixed (Week 2)**; production app construction verified (`docs_url=None`) | `test_week2_demo_seeding.py` (policy + health label) |
| S9 | Low | No per-account login lockout; rate limiter keys on socket IP and fails open | **Open** (Week 3, Rohan): add per-account/IP failed-login counter in Redis, trusted-proxy handling, fail-closed on `/auth/*` | – |
| S10 | Low | WebSocket allows any user/any city | **Open** (Week 3, Rohan); no broadcaster exists today | – |
| S11 | Low | Misnamed `Require*` dependencies | **Fixed (Week 2)**: `RequireStaff` (ADM+OFF+INS), `RequireInspectorOnly` (INS), `RequireAnalyst` (ADM+OFF). Runtime route/role table (121 entries) **identical before and after** | route snapshots compared |
| S12 | Info | Stale comment in `deps.py` | Fixed | – |
| B4 | – | Notification ownership | **Verified, no defect**: list/count/read-all scoped to caller; cross-user read/dismiss -> 403 | `test_week2_notification_ownership.py` (5 tests) |
| N1 | Med | `twilio` is imported lazily but is **not in `requirements.txt`**: SMS/IVR sending fails on a clean install | **Open** (Aryan/Rohan): add a pinned dependency or document as optional; the signature check itself uses only the standard library | found while testing S6 |
| N2 | Low | Notification delete/read returns 403 (not 404) for another user's id, confirming the id exists (UUIDs, so low) | Open (Rohan) | tests accept 403/404 |
| N3 | Low | Prompt/Week 1 D4 wording: D4 is "no valid pollutant yields AQI 500", not HTTP 500 | Clarified; fixed as written in Week 1 (see data tests) | – |

## Not verified
No dynamic scanning, no dependency-CVE audit, no end-to-end Twilio call (credentials unavailable), no run against a TimescaleDB database.
