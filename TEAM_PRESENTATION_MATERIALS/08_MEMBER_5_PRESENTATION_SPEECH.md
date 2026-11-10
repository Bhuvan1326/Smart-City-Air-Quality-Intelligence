# Member 5 — Civic Engagement, Enforcement & Field Operations

## 1. Introduction
"I own the action loop — how a pollution problem goes from a citizen's complaint to an enforcement action and a notification. This is where the platform stops being a read-only dashboard and becomes an operational tool for the city."

## 2. Overall Functionality
- **Civic issues**: citizens submit reports; issues are tracked, clustered geographically, and auto-escalated when SLAs breach (15-minute job).
- **Evidence**: photo upload + verification for inspections and issue resolution.
- **Enforcement**: officers create/manage enforcement actions against emission sources.
- **Field operations**: field-inspector assignments, officer routes, drone flight planning and drone hotspot detection.
- **Alerts & notifications**: configurable pollutant thresholds (admin), citizen alerts, mitigation recommendations, pending-alert dispatch every minute, plus a websocket channel.
- **Role-scoped dashboards**: citizen, officer, enforcement, alert-thresholds pages — citizens see only their own city/records.

## 3. Technical Implementation
`civic.py` (issues, clusters, escalation, evidence, status events — with citizen city-scoping enforced server-side), `enforcement.py`, `alerts.py` (thresholds/alerts/mitigation), `notifications.py`, `drone.py`, `media_links.py`, `websocket.py`; tables `civic_issues`, `civic_issue_status_events`, `civic_issue_clusters`, `enforcement_actions`, `officer_routes`, `drone_flight_plans`, `citizen_alerts`, `alert_thresholds`, `notifications`, `intervention_outcomes`, `audit_logs`. Media stored under `backend/media/`.

## 4. Workflow
Citizen submits issue → geolocated record → cluster/assign → inspector verifies with evidence → officer enforcement action → notification dispatch → status timeline events throughout.

## 5. Integration
Consumes M1's stations/geography for siting, M2's attribution for evidence, M6's RBAC for scoping; feeds M6's audit/error surfaces.

## 6. Status & Limitations
PARTIAL — real role-scoped flows, media storage and the escalation/dispatch jobs are verified; the field-side (drone, officer-route) workflows are less exercised and some notification channels depend on broken Firebase/SMTP config (owned and documented by M6).

## 7. Demo Script
Login as citizen → `citizen` page → submit issue → login as inspector → `officer`/inspection + evidence → as officer → enforcement action → thresholds page (admin) → notification appears.

## 8. Conclusion
"I close the loop between measurement and municipal action — the part of the platform that actually changes the city's air."
