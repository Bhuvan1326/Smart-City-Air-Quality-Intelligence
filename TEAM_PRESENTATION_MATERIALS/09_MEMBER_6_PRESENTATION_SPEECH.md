# Member 6 — Identity, Administration & Platform Reliability

## 1. Introduction
"I own who-can-do-what and whether-the-system-is-healthy: authentication, the 4-role permission model, the admin monitoring endpoints, the security and API-reliability audits, and the infrastructure glue — Docker, seeding, audit logging and reporting."

## 2. Overall Functionality
- **Authentication**: JWT access + single-flight refresh rotation, bcrypt hashing, login throttling, secure cookies, per-request `CurrentUser`.
- **RBAC**: `require_roles` deps — `RequireAdmin`, `RequireStaff`, `RequireInspectorOnly`, `RequireAnalyst` — mirrored by frontend `lib/role-policy.ts`; citizens get row-level city/record scoping.
- **Accounts**: 4 roles (city_administrator, pollution_control_officer, field_inspector, citizen) + 4 seeded demo users.
- **Admin monitoring** (new `/admin` router, all admin-only): `/admin/errors` + `/errors/summary` (real captured errors from `audit_logs`), `/admin/users/statistics`, `/admin/system/statistics`, `/admin/system/health`, `/admin/audits`.
- **Audits**: real security audit (0 critical, 1 high — invalid Sentinel creds) and API-reliability audit (14/14 representative endpoints, 100% pass, noauth→403, invalid→422) persisted as evidence.
- **Infra**: Docker Compose stack, resumable seeder, `AuditLogMiddleware` request logging, reports/transparency/data-sources.

## 3. Technical Implementation
`auth.py` + `deps.py` + `middleware.py` + `admin.py` over `users`/`audit_logs`; Redis for rate-limit/locks; Compose orchestrates backend/frontend/db/redis/migrate; CI runs Black/isort/Ruff/pytest/coverage.

## 4. Workflow
Login → JWT → role claim → dep gate per endpoint → audit middleware records mutating calls → admin endpoints aggregate users/errors/health into the dashboard.

## 5. Integration
Everyone depends on my auth — every route is `CurrentUser`-protected; I consume M1–M5's data for system statistics; I feed them the audit/error surfaces.

## 6. Status & Limitations
Auth + admin monitoring APIs COMPLETE and verified live; security/reliability audits executed with persisted real results. PARTIAL: admin dashboard card wiring, and 3 broken external credentials (Sentinel, Firebase file path, SMTP host) — documented, not hidden.

## 7. Demo Script
Login as admin → `/dashboard/administration?module=admin` → service health, stations reporting, alerts → show `/api/v1/admin/users/statistics` (4 users by role) and `/admin/errors/summary` (real captured errors) → explain the audit-status cards.

## 8. Conclusion
"I'm the platform's gatekeeper and its honesty layer — making sure the right people see the right things, and that 'system status' is measured, not assumed."
