#!/usr/bin/env bash
# Live AQI runtime verification script.
#
# Run this from the project root (same directory as docker-compose.yml),
# in Git Bash / WSL / a Linux or Mac shell. If you only have PowerShell,
# run it inside WSL ("wsl bash verify_live_aqi.sh") or Git Bash — it uses
# bash features (arrays, [[ ]]) that don't translate directly to PowerShell.
#
# It builds/starts the stack, checks env vars are present (never prints
# their values), calls the real endpoints, manually triggers the Pune
# ingestion task, and greps the DB + API response for demo station names.
# Paste the FULL output back and I'll diagnose from it.

set -uo pipefail
LOG=verify_live_aqi_output.txt
: > "$LOG"

log() { echo "$@" | tee -a "$LOG"; }
section() { log ""; log "===== $1 ====="; }

# Use files in the current project directory rather than /tmp: /tmp is
# not reliably writable/present the same way across Windows Git Bash,
# WSL, and Linux/Mac shells, which is exactly what broke Section 12
# ("No such file or directory: '/tmp/live_response.json'") even though
# the API call itself succeeded.
HEALTH_FILE="${PWD}/health_response.json"
LIVE_RESPONSE_FILE="${PWD}/live_response.json"
export LIVE_RESPONSE_FILE

section "1. Clean rebuild"
docker compose down 2>&1 | tee -a "$LOG"
docker compose build --no-cache 2>&1 | tee -a "$LOG"
docker compose up -d 2>&1 | tee -a "$LOG"
sleep 5
docker compose ps 2>&1 | tee -a "$LOG"

section "2. Wait for backend health (up to 90s)"
HEALTHY=0
for i in $(seq 1 18); do
  if curl -sf http://localhost:8000/health >"$HEALTH_FILE" 2>/dev/null; then
    HEALTHY=1
    break
  fi
  sleep 5
done
if [ "$HEALTHY" = "1" ]; then
  cat "$HEALTH_FILE" | tee -a "$LOG"
else
  log "backend never became healthy — dumping backend logs"
  docker compose logs --tail=300 backend 2>&1 | tee -a "$LOG"
fi

section "3. Env vars inside containers (values never printed)"
for svc in backend celery_worker celery_beat; do
  log "--- $svc ---"
  docker compose exec -T "$svc" sh -c '
    test -n "$OPENAQ_API_KEY" && echo OPENAQ_API_KEY=set || echo OPENAQ_API_KEY=MISSING
    test -n "$OPENAQ_BASE_URL" && echo "OPENAQ_BASE_URL=$OPENAQ_BASE_URL" || echo OPENAQ_BASE_URL=MISSING
  ' 2>&1 | tee -a "$LOG"
done

section "4. OpenAQ reachability from inside backend container"
docker compose exec -T backend python -c "
import asyncio
from app.services.aqi_providers import openaq

async def main():
    print('is_configured:', openaq.is_configured())
    if not openaq.is_configured():
        print('BLOCKED: OPENAQ_API_KEY not set inside the backend container')
        return
    # Real call using the app's own provider code — Hadapsar approx coords.
    try:
        res = await openaq.search_locations_near(18.5089, 73.9259, radius_m=12000)
        print('search_locations_near returned', len(res) if res else 0, 'candidates')
        if res:
            print('first candidate name:', res[0].get('name'))
    except Exception as e:
        print('OPENAQ REQUEST FAILED:', repr(e))

asyncio.run(main())
" 2>&1 | tee -a "$LOG"

section "5. Get an admin auth token (seeded dev user)"
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@pune.gov.in","password":"Admin@123"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('access_token',''))" 2>/dev/null)
if [ -z "$TOKEN" ]; then
  log "Could not obtain a token — login response was:"
  curl -s -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@pune.gov.in","password":"Admin@123"}' | tee -a "$LOG"
else
  log "token acquired (not printed)"
fi
AUTH_HEADER="Authorization: Bearer $TOKEN"

section "6. Manually run the Pune live ingestion task (do not wait 60s)"
docker compose exec -T celery_worker python -c "
from app.workers.tasks.aqi_ingestion import fetch_live_aqi_pune_stations
result = fetch_live_aqi_pune_stations.apply().get()
print('task result:', result)
" 2>&1 | tee -a "$LOG"

section "7. celery_worker logs (last 300 lines)"
docker compose logs --tail=300 celery_worker 2>&1 | tee -a "$LOG"

section "8. celery_beat logs (last 200 lines) — confirm schedule loaded"
docker compose logs --tail=200 celery_beat 2>&1 | grep -i "pune\|beat: starting\|scheduler" | tee -a "$LOG"

section "9. Inspect monitoring_stations + latest aqi_readings in Postgres"
docker compose exec -T db psql -U "${POSTGRES_USER:-airuser}" -d "${POSTGRES_DB:-airquality}" -c "
SELECT station_code, name, openaq_location_id, last_data_at
FROM monitoring_stations
WHERE station_code LIKE 'PUNE_LIVE_%'
ORDER BY station_code;
" 2>&1 | tee -a "$LOG"

docker compose exec -T db psql -U "${POSTGRES_USER:-airuser}" -d "${POSTGRES_DB:-airquality}" -c "
SELECT ms.station_code, ar.aqi, ar.pm25, ar.timestamp, ar.quality_flag
FROM aqi_readings ar
JOIN monitoring_stations ms ON ms.id = ar.station_id
WHERE ms.station_code LIKE 'PUNE_LIVE_%'
ORDER BY ar.timestamp DESC
LIMIT 20;
" 2>&1 | tee -a "$LOG"

section "10. Call the real API: GET /api/v1/aqi/live?city=Pune"
curl -s "http://localhost:8000/api/v1/aqi/live?city=Pune" -H "$AUTH_HEADER" -o "$LIVE_RESPONSE_FILE"
python3 -m json.tool "$LIVE_RESPONSE_FILE" 2>&1 | tee -a "$LOG"

section "11. Check the response for banned demo station names"
for name in Shivajinagar Pimpri Katraj Wakad Kothrud Yerawada; do
  if grep -qi "$name" "$LIVE_RESPONSE_FILE" 2>/dev/null; then
    log "FAIL: found banned station '$name' in /aqi/live response"
  else
    log "OK: '$name' not present"
  fi
done

section "12. Station count check"
python3 -c "
import json, os
try:
    d = json.load(open(os.environ['LIVE_RESPONSE_FILE']))
    items = d.get('data', d) if isinstance(d, dict) else d
    print('station count:', len(items))
    for it in items:
        print(' -', it.get('station_name'), '| source:', it.get('data_source'), '| unresolved:', it.get('unresolved'))
except Exception as e:
    print('could not parse response:', e)
" 2>&1 | tee -a "$LOG"

section "13. Other endpoints (checking for 503s)"
for ep in "/health" "/api/v1/aqi/live?city=Pune" "/api/v1/aqi/history?city=Pune" "/api/v1/aqi/stations?page=1&city=Pune" "/api/v1/aqi/india" "/api/v1/dashboard/overview?city=Pune"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000${ep}" -H "$AUTH_HEADER")
  log "$ep -> HTTP $code"
done

section "14. If any endpoint returned 503, dump backend logs"
docker compose logs --tail=500 backend 2>&1 | grep -B5 -A40 -i "traceback\|error\|503" | tail -300 | tee -a "$LOG"

section "DONE — send back $LOG"
log "Full output saved to $LOG in the current directory."
