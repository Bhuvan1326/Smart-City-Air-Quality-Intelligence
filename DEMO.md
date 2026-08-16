# Demo Guide

Complete walkthrough of the Urban Air Quality Intelligence Platform. Every step is executable with no manual database edits.

## Prerequisites

```bash
docker compose up -d
# Wait 60 seconds for migrations + seeder
curl http://localhost:8000/health
# → {"status":"healthy","checks":{"api":"ok","database":"ok","redis":"ok"}}
```

---

## Step 1 — Login as City Administrator

Navigate to http://localhost:3000/login

Click **admin** demo button (autofills email/password), then **Sign in**.

You land on the Pune Dashboard overview showing:
- Average AQI across all 8 wards
- Active station count, pending enforcements, anomalies today
- All 8 live station cards with real-time readings

---

## Step 2 — AI Anomaly Detection flags Ward 7 spike

The dashboard shows **1 anomaly today** in the stats panel.

The pre-seeded anomaly (`AQI 285` in Ward W07 / Kothrud) was detected 1 hour ago. It shows:
- Spike value: 285 (baseline: 78)
- Z-score: 4.8
- Probable cause: Construction activity + evening traffic peak
- Confidence: 87%

Navigate to **AI Assistant** and ask:
> "Why is AQI increasing in Ward 7?"

The assistant returns a full evidence-backed answer citing:
- CAAQMS Kothrud station reading history
- Pollution attribution model (construction: 38%, vehicular: 32%)
- Root cause timeline with 4 timestamped events
- Confidence score based on data completeness

---

## Step 3 — Source Attribution identifies primary contributors

Navigate to **Pollution Sources** (sidebar).

For Ward W07, the attribution model shows:
- Construction: **~38%** (Kothrud Metro construction site)
- Vehicular: **~32%** (Paud Road evening peak)
- Overall confidence: **87%**

The Enforcement page already has an AI-generated recommendation for this exact event.

---

## Step 4 — Forecast Agent predicts AQI 285 by tomorrow morning

Navigate to **Forecast** → select Ward **W07**.

The 72-hour chart shows:
- Current AQI: 285
- Peak forecast: matches current spike (PM traffic hours)
- Confidence intervals widen from ~92% at +1h to ~55% at +72h
- Feature importance: current_aqi (38%), hour_of_day (22%), ward_type (18%)

---

## Step 5 — Enforcement Agent generates prioritised recommendation

Navigate to **Enforcement**.

The AI-generated action is pre-seeded:
- **Priority: 92.5 (Critical)**
- Title: "Emergency inspection — Kothrud construction site AQI spike"
- AI Reasoning: anomaly_detection trigger, 87% confidence, recommended action displayed
- Status: **Assigned**

Expand the row to see full AI reasoning panel and map link.

---

## Step 6 — Officer accepts task and route loads

Change action status to **In Progress** using the status buttons.

In a full mobile deployment, the field inspector would receive a push notification and route optimisation would load. The officer route is pre-seeded in `officer_routes` with waypoints, optimisation score, and estimated duration.

---

## Step 7 — Upload photographic evidence

Use the **Update status** buttons → set to **Completed**. Add a note: "Site inspected. Stop-work notice issued. Dust suppression ordered."

The `evidence_urls` field accepts file URLs — in production this is an S3 presigned upload.

---

## Step 8 — Intervention impact score updates

The Yerawada Brick Kiln action (Ward W08) is pre-seeded as **Completed** with a measured outcome:
- AQI before: 195 → AQI after: 128
- Delta: **−67 AQI units**
- Carbon saved: 240 kg
- Verification method: CAAQMS 24h rolling average

Navigate to **Analytics** → the intervention outcomes panel shows avg AQI improvement of −67.

---

## Step 9 — Citizen advisory pushed in Marathi

Navigate to **Citizen Alerts**.

The pre-seeded Marathi alert for Ward W07 shows:
```
अत्यंत अस्वास्थ्यकर हवा — बाहेर जाणे टाळा
वॉर्ड W07 मध्ये AQI 285 पर्यंत पोहोचला आहे...
```

Delivery status: **sent** (1 hour ago). Vulnerability groups: elderly, children, asthma_patients.

English and Hindi versions exist for the same ward.

---

## Step 10 — Policy Analytics before/after comparison

Navigate to **Analytics** → scroll to **Policy Interventions**.

Three pre-seeded interventions show:
| City | Policy | AQI Δ | Impact Score |
|------|--------|-------|-------------|
| Pune | Odd-even vehicles | −28.5 | 72 |
| Mumbai | Construction dust control | −18.0 | 58 |
| Delhi | GRAP Stage III | −45.0 | 85 |

The comparison chart shows Delhi with highest average AQI reduction, with Mumbai as comparable city reference.

---

## AI Assistant sample queries

Copy-paste these into the AI Assistant page:

```
Why is AQI increasing in Ward 7?
Which industries contributed most to pollution yesterday?
Show top pollution hotspots right now.
Recommend actions to reduce PM2.5 in Shivajinagar.
What changed in air quality after yesterday's inspections?
Forecast AQI for tomorrow morning across all wards.
```

Each response includes:
- Answer with evidence citations
- Confidence score (%)
- Data sources used
- Supporting sensor evidence
- Reasoning trace (expandable)
- Spatial data summary (ward AQI map data)

---

## PDF Export

Navigate to **Reports** → select **Enforcement Summary** → click **PDF**.

A regulation-formatted PDF downloads immediately with:
- All enforcement actions for the period
- Officer names, ward IDs, action types, priorities, status
- Blue header styling, alternating row backgrounds
- Generated timestamp

---

## API documentation

http://localhost:8000/docs — full Swagger UI with all 20+ endpoints, request/response schemas, and try-it-out.
