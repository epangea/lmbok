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
echo "-- P11 endpoints require org auth (no credentials, expect 401) --"
# Structural check only — confirms these new routes exist and are gated,
# same as the learner block above. The actual behavior of the flow (parse
# -> generate -> notify -> accept -> reveal) is covered end-to-end in
# scripts/e2e_org_polis.sh, not here — smoke.sh stays fast and stateless.
for ep in "/api/orgs/listings/1/parse-needs" "/api/orgs/listings/1/generate-matches" "/api/orgs/listings/1/matches/1/notify"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API_BASE}${ep}" -H "Content-Type: application/json" -d '{}' --max-time 8)
  pass "$ep" "$code" "401"
done
for ep in "/api/matching/1/accept" "/api/matching/1/decline"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API_BASE}${ep}" -H "Content-Type: application/json" -d '{}' --max-time 8)
  pass "$ep" "$code" "401"
done

echo ""
echo "-- P8 validation endpoints require auth (no credentials, expect 401) --"
# Structural check only, same rationale as the P11 block above.
for ep in "/api/orgs/matches/1/validation"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE}${ep}" --max-time 8)
  pass "$ep" "$code" "401"
done
for ep in "/api/orgs/matches/1/tasks/0/verify" "/api/orgs/matches/1/skills/1/verify"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API_BASE}${ep}" -H "Content-Type: application/json" -d '{}' --max-time 8)
  pass "$ep" "$code" "401"
done
for ep in "/api/matching/1/validation"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE}${ep}" --max-time 8)
  pass "$ep" "$code" "401"
done
for ep in "/api/matching/1/tasks/0/submit"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API_BASE}${ep}" -H "Content-Type: application/json" -d '{}' --max-time 8)
  pass "$ep" "$code" "401"
done

echo ""
echo "-- P42: /api/generate structural checks (2026-08-01) --"
# GenerateRequest.art_slug is a REQUIRED field (unlike the P8/P11 bodies
# above, which are all-optional) -- an empty '{}' body here would risk a
# 422 (body validation) racing a 401 (auth dependency) depending on
# FastAPI's internal resolution order, which would make this check flaky
# rather than a real proof the route is auth-gated. Sending a body that
# actually satisfies GenerateRequest means a 401 here is unambiguous.
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API_BASE}/api/generate/session" \
  -H "Content-Type: application/json" -d '{"art_slug":"move"}' --max-time 8)
pass "/api/generate/session (no credentials)" "$code" "401"

# Diagnostic endpoint for the /session circuit breaker -- deliberately
# public (no learner/admin auth) so it can be polled by monitoring/ops
# without a login. Structural check only; the real end-to-end AI
# generation call (and the DB-level proof that model != "library") lives
# in e2e_org_polis.sh's Part E -- kept out of here so smoke.sh stays fast
# and makes no real AI-provider call.
code=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE}/api/generate/breaker-status" --max-time 8)
pass "/api/generate/breaker-status (public diagnostic)" "$code" "200"

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

# P8 — Validation section read endpoints, same cookie-only pattern
code=$(curl -s -o /dev/null -w "%{http_code}" -b "$AJAR" "${API_BASE}/api/admin/verified-skills" --max-time 8)
pass "/api/admin/verified-skills (cookie only)" "$code" "200"
code=$(curl -s -o /dev/null -w "%{http_code}" -b "$AJAR" "${API_BASE}/api/admin/task-completions" --max-time 8)
pass "/api/admin/task-completions (cookie only)" "$code" "200"

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
echo "-- P-SEC3: dual-session CSRF regression check (rewritten 2026-08-11) --"
# Regression test for the CSRF middleware bug class: ADMIN_ACCESS_COOKIE is
# scoped to all of /api (see cookie_auth.py), so it rides along on every
# request whenever the same browser also has an admin session open — a very
# normal thing for a solo operator testing multiple roles at once in one
# window (Charbel's actual report, 2026-08-11: "CSRF check failed" on
# /api/generate/session with both learner and admin logged in). The
# 2026-08-10 fix only special-cased /api/matching and /api/learners; the
# 2026-08-11 fix replaced the whole cookie-presence fallback with real
# path-based routing (see main.py) since admin-gating is actually confined
# to exactly two prefixes (confirmed via `grep -rl require_admin routes/`:
# routes/admin.py and routes/bioregions.py's /admin/... sub-paths only).
# This block recreates the dual-cookie browser state and checks a spread of
# prefixes -- not just the two from the narrower 2026-08-10 patch -- so a
# future prefix-scoping mistake gets caught here instead of live. Gated on
# TEST_LEARNER_EMAIL/PASSWORD since it needs a real learner session to layer
# the admin one on top of; reuses ADMIN_KEY (always required, see top of
# script).
if [ -n "${TEST_LEARNER_EMAIL:-}" ] && [ -n "${TEST_LEARNER_PASSWORD:-}" ]; then
  DJAR=$(mktemp)

  code=$(curl -s -c "$DJAR" -o /dev/null -w "%{http_code}" \
    -X POST "${API_BASE}/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${TEST_LEARNER_EMAIL}\",\"password\":\"${TEST_LEARNER_PASSWORD}\"}" \
    --max-time 8)
  pass "/api/auth/login (dual-session setup)" "$code" "200"

  # Log the SAME jar into an admin session too -- curl's -b -c on the same
  # file merges new Set-Cookie values in alongside what's already there,
  # rather than replacing the jar, so DJAR now genuinely holds both
  # fl_access/fl_csrf and fl_admin_session/fl_admin_csrf at once, exactly
  # matching the real-world scenario that exposed the bug.
  code=$(curl -s -b "$DJAR" -c "$DJAR" -o /dev/null -w "%{http_code}" \
    -X POST "${API_BASE}/api/admin/login" \
    -H "Content-Type: application/json" \
    -d "{\"admin_key\":\"${ADMIN_KEY}\"}" \
    --max-time 8)
  pass "/api/admin/login (dual-session setup)" "$code" "200"

  # Sanity check: both session cookies must actually be present in the same
  # jar, or the tests below wouldn't be reproducing the real bug at all.
  if grep -q "fl_access" "$DJAR" && grep -q "fl_admin_session" "$DJAR"; then
    echo "OK    dual session established (fl_access + fl_admin_session both present)"
  else
    echo "FAIL  dual session setup failed -- fl_access and/or fl_admin_session missing from jar"; fail=$((fail+1))
  fi

  DCSRF=$(awk -F'\t' '$6=="fl_csrf"{print $7}' "$DJAR")
  ACSRF_D=$(awk -F'\t' '$6=="fl_admin_csrf"{print $7}' "$DJAR")

  # PATCH /api/learners/me/preferences with the LEARNER's own CSRF token,
  # while the admin session cookie also rides along. Pre-fix, this 403'd
  # (middleware checked the header against fl_admin_csrf instead). Body is
  # a genuine no-op -- every PreferencesUpdate field is Optional.
  code=$(curl -s -o /dev/null -w "%{http_code}" -b "$DJAR" -X PATCH "${API_BASE}/api/learners/me/preferences" \
    -H "Content-Type: application/json" -H "X-CSRF-Token: ${DCSRF}" -d '{}' --max-time 8)
  pass "PATCH /api/learners/me/preferences with learner X-CSRF-Token + admin cookie present" "$code" "200"

  # DELETE /api/matching/999999 (a match id that doesn't exist) with the
  # same learner CSRF token. A 404 here proves the request got PAST the
  # CSRF check and into the real route logic; a 403 would mean the
  # middleware is still validating against the wrong (admin) CSRF pair.
  # 999999 is chosen to be safely out of range of any real seeded data.
  code=$(curl -s -o /dev/null -w "%{http_code}" -b "$DJAR" -X DELETE "${API_BASE}/api/matching/999999" \
    -H "X-CSRF-Token: ${DCSRF}" --max-time 8)
  pass "DELETE /api/matching/999999 with learner X-CSRF-Token + admin cookie present (expect 404, not 403)" "$code" "404"

  # POST /api/generate/session with an art_slug that doesn't exist, learner
  # CSRF token, admin cookie present. This is the exact live symptom
  # Charbel reported 2026-08-11 -- /api/generate wasn't covered by the
  # 2026-08-10 patch at all. A 404 ("Art not found") proves the request
  # cleared the CSRF check and reached generate.py's own art lookup, well
  # before anything would call an AI provider -- no real AI generation or
  # cost is triggered by this check.
  code=$(curl -s -o /dev/null -w "%{http_code}" -b "$DJAR" -X POST "${API_BASE}/api/generate/session" \
    -H "Content-Type: application/json" -H "X-CSRF-Token: ${DCSRF}" \
    -d '{"art_slug":"__smoke_test_nonexistent_art__"}' --max-time 8)
  pass "POST /api/generate/session with learner X-CSRF-Token + admin cookie present (expect 404, not 403)" "$code" "404"

  # Inverse check: an /api/admin/* request must still validate against the
  # ADMIN CSRF pair, not the learner one, even with a learner cookie also
  # present in the jar -- confirms the path-based rewrite didn't overcorrect
  # and start treating admin-prefixed requests as learner-scoped. Same
  # genuine-no-op settings PATCH the existing admin CSRF block above uses.
  code=$(curl -s -o /dev/null -w "%{http_code}" -b "$DJAR" -X PATCH "${API_BASE}/api/admin/settings" \
    -H "Content-Type: application/json" -H "X-CSRF-Token: ${DCSRF}" \
    -d '{"settings":{"ai_provider":"groq"}}' --max-time 8)
  pass "PATCH /api/admin/settings with LEARNER X-CSRF-Token (must be rejected, wrong pair)" "$code" "403"

  code=$(curl -s -o /dev/null -w "%{http_code}" -b "$DJAR" -X PATCH "${API_BASE}/api/admin/settings" \
    -H "Content-Type: application/json" -H "X-CSRF-Token: ${ACSRF_D}" \
    -d '{"settings":{"ai_provider":"groq"}}' --max-time 8)
  pass "PATCH /api/admin/settings with admin X-CSRF-Token + learner cookie present" "$code" "200"

  # Clean up both sessions
  curl -s -o /dev/null -b "$DJAR" -X POST "${API_BASE}/api/auth/logout" -H "X-CSRF-Token: ${DCSRF}" --max-time 8 || true
  curl -s -o /dev/null -b "$DJAR" -X POST "${API_BASE}/api/admin/logout" -H "X-CSRF-Token: ${ACSRF_D}" --max-time 8 || true
  rm -f "$DJAR"
else
  echo "WARN  No TEST_LEARNER_EMAIL/TEST_LEARNER_PASSWORD set — P-SEC3 dual-session check skipped"
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
echo "-- Registration DB round-trip check (PART 30, 2026-08-14) --"
# Exercises the exact code path that was hitting the stale-connection
# RuntimeError (POST /api/auth/register -> a real INSERT via the async
# pool) rather than a synthetic health check, then cleans up after itself.
# This is the closest thing to a canary for the db.py pool_recycle fix:
# if the pool goes stale again, this is what will catch it, same as a
# real learner would hit it.

DB_USER=$(env_or_file DB_USER); DB_USER="${DB_USER:-freqlearn}"
DB_PASSWORD=$(env_or_file DB_PASSWORD); DB_PASSWORD="${DB_PASSWORD:-changeme}"
DB_HOST=$(env_or_file DB_HOST); DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT=$(env_or_file DB_PORT); DB_PORT="${DB_PORT:-3306}"
DB_NAME=$(env_or_file DB_NAME); DB_NAME="${DB_NAME:-freqlearn}"
MYSQL_BIN=$(command -v mariadb || command -v mysql || true)

db_exec() {
  # db_exec "DELETE ..." -> best-effort, never fails the script (cleanup only)
  [ -z "$MYSQL_BIN" ] && return 0
  "$MYSQL_BIN" -N -B -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" \
    -e "$1" 2>/dev/null || true
}

# Reuses TEST_LEARNER_EMAIL's local part with a +smoketest-<epoch> alias so a
# real send (the register endpoint fires a verification email as a
# fire-and-forget background task) lands harmlessly in an inbox Charbel
# already owns, rather than bouncing against a fake domain. Falls back to a
# clearly-junk address if TEST_LEARNER_EMAIL isn't set — registration itself
# is still tested either way, only the "does the email actually land
# somewhere sane" nicety is lost.
if [ -n "$TEST_LEARNER_EMAIL" ] && [[ "$TEST_LEARNER_EMAIL" == *"@"* ]]; then
  SMOKE_REG_EMAIL="${TEST_LEARNER_EMAIL%%@*}+smoketest-$(date +%s)@${TEST_LEARNER_EMAIL##*@}"
else
  SMOKE_REG_EMAIL="smoketest-$(date +%s)@example.invalid"
fi
SMOKE_REG_PASS="Sm0keTest$(date +%s)!"

reg_code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API_BASE}/api/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${SMOKE_REG_EMAIL}\",\"password\":\"${SMOKE_REG_PASS}\"}" \
  --max-time 8)
pass "POST /api/auth/register (real DB round-trip)" "$reg_code" "200"

# Best-effort cleanup — never blocks or fails the script. FK order matters:
# learner_streaks/learner_preferences reference learners.id.
if [ "$reg_code" = "200" ]; then
  db_exec "DELETE ls FROM learner_streaks ls JOIN learners l ON l.id=ls.learner_id WHERE l.email='${SMOKE_REG_EMAIL}';"
  db_exec "DELETE lp FROM learner_preferences lp JOIN learners l ON l.id=lp.learner_id WHERE l.email='${SMOKE_REG_EMAIL}';"
  db_exec "DELETE FROM learners WHERE email='${SMOKE_REG_EMAIL}';"
  if [ -z "$MYSQL_BIN" ]; then
    echo "WARN  mysql/mariadb CLI not found -- smoke-test account ${SMOKE_REG_EMAIL} was NOT cleaned up, delete manually"
  fi
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
