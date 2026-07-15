#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${APP_ROOT}/backend"
ENV_FILE="${BACKEND_DIR}/.env"
FAIL_LOG="/var/log/freqlearn/api-error.log"
UI_BASE="${UI_BASE:-https://build.onehouse.top}"
API_BASE="${API_BASE:-https://build.onehouse.top}"
LTOKEN="${LTOKEN:-}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found"
  exit 1
fi

ADMIN_KEY=$(grep -E '^ADMIN_KEY=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | sed -e 's/^"//' -e 's/"$//')
if [ -z "$ADMIN_KEY" ]; then
  echo "ERROR: ADMIN_KEY not set in $ENV_FILE"
  exit 1
fi

fail=0
pass() {
  local label="$1" code="$2" expected="$3"
  if [ "$code" != "$expected" ]; then
    echo "FAIL  $label -> HTTP $code (expected $expected)"
    fail=$((fail+1))
  else
    echo "OK    $label"
  fi
}

echo "-- Frontend page checks --"
for page in "/" "/admin" "/contribute" "/org" "/polis"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "${UI_BASE}${page}" --max-time 8)
  pass "$page" "$code" "200"
done

echo ""
echo "-- API checks (admin key) --"
for ep in "/api/admin/stats"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE}${ep}" \
    -H "X-Admin-Key: ${ADMIN_KEY}" --max-time 8)
  pass "$ep" "$code" "200"
done
for ep in "/api/" "/api/arts"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE}${ep}" \
    -H "X-Admin-Key: ${ADMIN_KEY}" --max-time 8)
  pass "$ep" "$code" "200"
done
for ep in "/api/bioregions?lat=16.5&lng=107.6"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE}${ep}" \
    -H "X-Admin-Key: ${ADMIN_KEY}" --max-time 8)
  pass "$ep" "$code" "200"
done

echo ""
echo "-- Learner API (admin key, expect 403) --"
for ep in "/api/learners/me" "/api/sessions/today"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE}${ep}" \
    -H "X-Admin-Key: ${ADMIN_KEY}" --max-time 8)
  pass "$ep" "$code" "403"
done

echo ""
echo "-- Learner-facing API checks --"
if [ -n "$LTOKEN" ]; then
  for ep in "/api/learners/me" "/api/sessions/today" "/api/sessions/history"; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE}${ep}" \
      -H "Authorization: Bearer ${LTOKEN}" --max-time 8)
    pass "$ep (learner)" "$code" "200"
  done
else
  echo "WARN  No LTOKEN set — learner endpoints not checked"
  echo "      Set it interactively: export LTOKEN=<learner-jwt-token>"
  echo "      Find your token in browser DevTools > Application > Cookies"
fi

echo ""
if [ "$fail" -ne 0 ]; then
  echo "--- Last 30 lines of $FAIL_LOG ---"
  if [ -f "$FAIL_LOG" ]; then
    tail -n 30 "$FAIL_LOG" || true
  else
    echo "(log file not found)"
  fi
  echo "SMOKE TEST FAILED"
  exit 1
fi
echo "All checks healthy."
