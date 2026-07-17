#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${APP_ROOT}/backend"
ENV_FILE="${BACKEND_DIR}/.env"
FAIL_LOG="/var/log/freqlearn/api-error.log"
UI_BASE="${UI_BASE:-https://build.onehouse.top}"
API_BASE="${API_BASE:-https://build.onehouse.top}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found"
  exit 1
fi

ADMIN_KEY=$({ grep -E '^ADMIN_KEY=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | sed -e 's/^"//' -e 's/"$//'; } || true)
if [ -z "$ADMIN_KEY" ]; then
  echo "ERROR: ADMIN_KEY not set in $ENV_FILE"
  exit 1
fi

# Reads KEY=value from backend/.env, same pattern as ADMIN_KEY above.
# An already-exported env var of the same name takes priority (lets you
# override ad-hoc without touching .env), so this only fills in what's
# missing.
env_or_file() {
  local var_name="$1"
  local current="${!var_name:-}"
  if [ -n "$current" ]; then
    echo "$current"
    return 0
  fi
  # "|| true" is load-bearing: grep exits 1 when the key isn't in .env, and
  # under set -e + pipefail that would silently kill the ENTIRE script right
  # here — before any test output ever prints — since "not found" is a
  # perfectly normal outcome for an optional var like TEST_ORG_EMAIL, not a
  # real error.
  { grep -E "^${var_name}=" "$ENV_FILE" | head -1 | cut -d'=' -f2- | sed -e 's/^"//' -e 's/"$//'; } || true
  return 0
}

# Test accounts for the cookie/CSRF smoke checks below (P-SEC1, 2026-07-16).
# Add these to backend/.env once — same file ADMIN_KEY already lives in,
# already gitignored — and smoke.sh just runs unattended from then on:
#   TEST_LEARNER_EMAIL=charbelh@...
#   TEST_LEARNER_PASSWORD=...
#   TEST_ORG_EMAIL=...       (optional — org checks skip cleanly without it)
#   TEST_ORG_PASSWORD=...
TEST_LEARNER_EMAIL=$(env_or_file TEST_LEARNER_EMAIL)
TEST_LEARNER_PASSWORD=$(env_or_file TEST_LEARNER_PASSWORD)
TEST_ORG_EMAIL=$(env_or_file TEST_ORG_EMAIL)
TEST_ORG_PASSWORD=$(env_or_file TEST_ORG_PASSWORD)

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
for page in "/" "/admin" "/contribute" "/org" "/polis" "/privacy.html"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "${UI_BASE}${page}" --max-time 8)
  pass "$page" "$code" "200"
done

echo ""
echo "-- API checks (public) --"
# These never needed X-Admin-Key (public/learner-facing endpoints) — the
# header was harmless-but-pointless here even before P-SEC2. Dropped now
# that the header means nothing to the backend at all.
for ep in "/api/" "/api/arts" "/api/bioregions?lat=16.5&lng=107.6"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE}${ep}" --max-time 8)
  pass "$ep" "$code" "200"
done

echo ""
echo "-- Learner API (no credentials, expect 401) --"
# Was 403 pre-P-SEC1: the old HTTPBearer() dependency auto-raised 403 when no
# Authorization header was present at all (a known FastAPI quirk — 403
# usually means "authenticated but forbidden," not "no credentials given").
# get_current_learner now reads the fl_access cookie directly and correctly
# raises 401 (not authenticated) when it's missing. Confirmed intentional,
# not a regression — see chat 2026-07-16.
for ep in "/api/learners/me" "/api/sessions/today"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE}${ep}" --max-time 8)
  pass "$ep" "$code" "401"
done

echo ""
echo "-- Admin cookie/CSRF checks (P-SEC2, 2026-07-17) --"
# ADMIN_KEY is only ever sent once now, in this login call, over HTTPS, to
# establish a session — never again as a header on every request. Runs
# unconditionally (unlike the learner/org sections below) since ADMIN_KEY is
# already required at the top of this script.
AJAR=$(mktemp)
AHDRS=$(mktemp)

code=$(curl -s -c "$AJAR" -D "$AHDRS" -o /dev/null -w "%{http_code}" \
  -X POST "${API_BASE}/api/admin/login" \
  -H "Content-Type: application/json" \
  -d "{\"admin_key\":\"${ADMIN_KEY}\"}" \
  --max-time 8)
pass "/api/admin/login" "$code" "200"

if grep -q "#HttpOnly_.*fl_admin_session" "$AJAR"; then
  echo "OK    fl_admin_session is httpOnly"
else
  echo "FAIL  fl_admin_session missing or not httpOnly"; fail=$((fail+1))
fi
if grep -qE "^[^#].*[[:space:]]fl_admin_csrf[[:space:]]" "$AJAR"; then
  echo "OK    fl_admin_csrf is JS-readable (not httpOnly)"
else
  echo "FAIL  fl_admin_csrf missing or unexpectedly httpOnly"; fail=$((fail+1))
fi
if grep -i "^set-cookie: fl_admin_session" "$AHDRS" | grep -qi "secure"; then
  echo "OK    fl_admin_session has Secure flag"
else
  echo "FAIL  fl_admin_session missing Secure flag"; fail=$((fail+1))
fi

ACSRF=$(awk -F'\t' '$6=="fl_admin_csrf"{print $7}' "$AJAR")

# A plain GET should work off the cookie alone, no header needed
code=$(curl -s -o /dev/null -w "%{http_code}" -b "$AJAR" "${API_BASE}/api/admin/stats" --max-time 8)
pass "/api/admin/stats (cookie only)" "$code" "200"

# State-changing request WITHOUT the CSRF header must be rejected. Body is a
# genuine no-op (writes ai_provider back to its own current value — see
# MAINTENANCE.md schema-state table) so this is safe to run repeatedly.
code=$(curl -s -o /dev/null -w "%{http_code}" -b "$AJAR" -X PATCH "${API_BASE}/api/admin/settings" \
  -H "Content-Type: application/json" -d '{"settings":{"ai_provider":"groq"}}' --max-time 8)
pass "PATCH /api/admin/settings without X-CSRF-Token (must be rejected)" "$code" "403"

code=$(curl -s -o /dev/null -w "%{http_code}" -b "$AJAR" -X PATCH "${API_BASE}/api/admin/settings" \
  -H "Content-Type: application/json" -H "X-CSRF-Token: ${ACSRF}" \
  -d '{"settings":{"ai_provider":"groq"}}' --max-time 8)
pass "PATCH /api/admin/settings with X-CSRF-Token" "$code" "200"

# Logout must clear the session
code=$(curl -s -o /dev/null -w "%{http_code}" -b "$AJAR" -c "$AJAR" -X POST "${API_BASE}/api/admin/logout" \
  -H "X-CSRF-Token: ${ACSRF}" --max-time 8)
pass "/api/admin/logout" "$code" "200"

# And the cookie should now be unusable
code=$(curl -s -o /dev/null -w "%{http_code}" -b "$AJAR" "${API_BASE}/api/admin/stats" --max-time 8)
pass "/api/admin/stats after logout (must be rejected)" "$code" "401"

rm -f "$AJAR" "$AHDRS"

echo ""
echo "-- Learner cookie/CSRF checks (P-SEC1, 2026-07-16) --"
# Auth tokens moved from a Bearer header to httpOnly cookies + a CSRF
# double-submit cookie — LTOKEN/Authorization no longer applies. This
# logs in as a real (seed/test) learner and drives the actual cookie flow.
if [ -n "${TEST_LEARNER_EMAIL:-}" ] && [ -n "${TEST_LEARNER_PASSWORD:-}" ]; then
  JAR=$(mktemp)
  HDRS=$(mktemp)

  code=$(curl -s -c "$JAR" -D "$HDRS" -o /dev/null -w "%{http_code}" \
    -X POST "${API_BASE}/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${TEST_LEARNER_EMAIL}\",\"password\":\"${TEST_LEARNER_PASSWORD}\"}" \
    --max-time 8)
  pass "/api/auth/login" "$code" "200"

  # curl marks httpOnly cookies with a "#HttpOnly_" prefix line in the jar —
  # fl_access/fl_refresh must have it, fl_csrf must NOT (JS needs to read it)
  for c in fl_access fl_refresh; do
    if grep -q "#HttpOnly_.*${c}" "$JAR"; then
      echo "OK    ${c} is httpOnly"
    else
      echo "FAIL  ${c} missing or not httpOnly"; fail=$((fail+1))
    fi
  done
  if grep -qE "^[^#].*[[:space:]]fl_csrf[[:space:]]" "$JAR"; then
    echo "OK    fl_csrf is JS-readable (not httpOnly)"
  else
    echo "FAIL  fl_csrf missing or unexpectedly httpOnly"; fail=$((fail+1))
  fi

  # Secure flag, straight from the actual Set-Cookie response headers
  if grep -i "^set-cookie: fl_access" "$HDRS" | grep -qi "secure"; then
    echo "OK    fl_access has Secure flag"
  else
    echo "FAIL  fl_access missing Secure flag"; fail=$((fail+1))
  fi

  CSRF=$(awk -F'\t' '$6=="fl_csrf"{print $7}' "$JAR")

  # A plain GET should work off the cookie alone, no header needed
  code=$(curl -s -o /dev/null -w "%{http_code}" -b "$JAR" "${API_BASE}/api/learners/me" --max-time 8)
  pass "/api/learners/me (cookie only)" "$code" "200"

  # State-changing request WITHOUT the CSRF header must be rejected —
  # this is the actual point of the whole double-submit pattern
  code=$(curl -s -o /dev/null -w "%{http_code}" -b "$JAR" -X PATCH "${API_BASE}/api/auth/me" \
    -H "Content-Type: application/json" -d '{}' --max-time 8)
  pass "PATCH /api/auth/me without X-CSRF-Token (must be rejected)" "$code" "403"

  # Same request WITH the correct header must succeed (empty body — every
  # field in PatchMeRequest is optional, so this is a genuine no-op)
  code=$(curl -s -o /dev/null -w "%{http_code}" -b "$JAR" -X PATCH "${API_BASE}/api/auth/me" \
    -H "Content-Type: application/json" -H "X-CSRF-Token: ${CSRF}" -d '{}' --max-time 8)
  pass "PATCH /api/auth/me with X-CSRF-Token" "$code" "200"

  # Logout must clear the session
  code=$(curl -s -o /dev/null -w "%{http_code}" -b "$JAR" -c "$JAR" -X POST "${API_BASE}/api/auth/logout" \
    -H "X-CSRF-Token: ${CSRF}" --max-time 8)
  pass "/api/auth/logout" "$code" "200"

  # And the cookie should now be unusable
  code=$(curl -s -o /dev/null -w "%{http_code}" -b "$JAR" "${API_BASE}/api/learners/me" --max-time 8)
  pass "/api/learners/me after logout (must be rejected)" "$code" "401"

  rm -f "$JAR" "$HDRS"
else
  echo "WARN  No TEST_LEARNER_EMAIL/TEST_LEARNER_PASSWORD set — cookie/CSRF checks skipped"
  echo "      export TEST_LEARNER_EMAIL=... TEST_LEARNER_PASSWORD=... (use the seed/test learner, e.g. Tony) to enable"
fi

echo ""
echo "-- Org cookie/CSRF checks (P-SEC1, 2026-07-16) --"
if [ -n "${TEST_ORG_EMAIL:-}" ] && [ -n "${TEST_ORG_PASSWORD:-}" ]; then
  OJAR=$(mktemp)
  OHDRS=$(mktemp)

  code=$(curl -s -c "$OJAR" -D "$OHDRS" -o /dev/null -w "%{http_code}" \
    -X POST "${API_BASE}/api/orgs/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${TEST_ORG_EMAIL}\",\"password\":\"${TEST_ORG_PASSWORD}\"}" \
    --max-time 8)
  pass "/api/orgs/login" "$code" "200"

  if grep -q "#HttpOnly_.*fl_org_access" "$OJAR"; then
    echo "OK    fl_org_access is httpOnly"
  else
    echo "FAIL  fl_org_access missing or not httpOnly"; fail=$((fail+1))
  fi
  if grep -qE "^[^#].*[[:space:]]fl_org_csrf[[:space:]]" "$OJAR"; then
    echo "OK    fl_org_csrf is JS-readable (not httpOnly)"
  else
    echo "FAIL  fl_org_csrf missing or unexpectedly httpOnly"; fail=$((fail+1))
  fi
  if grep -i "^set-cookie: fl_org_access" "$OHDRS" | grep -qi "secure"; then
    echo "OK    fl_org_access has Secure flag"
  else
    echo "FAIL  fl_org_access missing Secure flag"; fail=$((fail+1))
  fi

  OCSRF=$(awk -F'\t' '$6=="fl_org_csrf"{print $7}' "$OJAR")

  code=$(curl -s -o /dev/null -w "%{http_code}" -b "$OJAR" "${API_BASE}/api/orgs/me" --max-time 8)
  pass "/api/orgs/me (cookie only)" "$code" "200"

  code=$(curl -s -o /dev/null -w "%{http_code}" -b "$OJAR" -X PATCH "${API_BASE}/api/orgs/me" \
    -H "Content-Type: application/json" -d '{}' --max-time 8)
  pass "PATCH /api/orgs/me without X-CSRF-Token (must be rejected)" "$code" "403"

  code=$(curl -s -o /dev/null -w "%{http_code}" -b "$OJAR" -X PATCH "${API_BASE}/api/orgs/me" \
    -H "Content-Type: application/json" -H "X-CSRF-Token: ${OCSRF}" -d '{}' --max-time 8)
  pass "PATCH /api/orgs/me with X-CSRF-Token" "$code" "200"

  code=$(curl -s -o /dev/null -w "%{http_code}" -b "$OJAR" -c "$OJAR" -X POST "${API_BASE}/api/orgs/logout" \
    -H "X-CSRF-Token: ${OCSRF}" --max-time 8)
  pass "/api/orgs/logout" "$code" "200"

  code=$(curl -s -o /dev/null -w "%{http_code}" -b "$OJAR" "${API_BASE}/api/orgs/me" --max-time 8)
  pass "/api/orgs/me after logout (must be rejected)" "$code" "401"

  rm -f "$OJAR" "$OHDRS"
else
  echo "WARN  No TEST_ORG_EMAIL/TEST_ORG_PASSWORD set — org cookie/CSRF checks skipped"
  echo "      export TEST_ORG_EMAIL=... TEST_ORG_PASSWORD=... (use a dedicated test org account) to enable"
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
