#!/usr/bin/env bash
# ============================================================
# FreqLearn — scripts/e2e_org_polis.sh   (P2, 2026-07-17)
#
# End-to-end functional test for the Org and Polis business logic —
# NOT just auth/CSRF plumbing (that's smoke.sh's job; this script
# assumes smoke.sh already passes). Covers:
#
#   Org:   register/login -> create listing (pending) -> admin sees
#          it in the review queue -> admin approves -> learner sees
#          it live -> learner expresses interest -> org sees the
#          match -> two-way Pnyx messaging -> org updates match
#          status -> learner withdraws -> org deactivates listing.
#
#   P11:   org writes needs_text -> AI parses skill targets -> org
#          generates AI-suggested matches (anonymized) -> learner
#          can't see an un-notified match -> org notifies -> learner
#          sees 'invited' -> learner accepts -> org's view reveals
#          the real identity. Re-notify-after-invite is rejected.
#
#   P8:    org writes needs_text -> AI parses skill targets AND task
#          line items -> learner expresses interest -> validation is
#          blocked until org marks the match 'connected' (checked both
#          ways) -> learner submits a task -> org verifies the task and
#          a skill demonstration (developing/proficient/master) -> both
#          sides' own validation views reflect it -> learner's aggregate
#          /me/verified-skills and admin's Validation page both see it.
#
#   Polis: my-access -> referenda read (incl. scope filter + bad
#          scope 400) -> proposals read -> Grove+ write checks
#          (submit local proposal, support/unsupport toggle, scope
#          gate on global proposal) OR the below-Grove 403 gate,
#          whichever applies to TEST_LEARNER's current stage.
#
#   P42 (new, 2026-08-01): a REAL end-to-end POST /api/generate/session
#          AI generation call — the actual gap that let P41's
#          `_bool_setting` NameError ship past both this script and
#          smoke.sh and 500 every real session generation in the live
#          app, since nothing in either script called this route with
#          a valid learner session before. Asserts a real 200 + a
#          fully-populated GeneratedSession body, then looks the new
#          session row up directly in the DB (same db_query() Part C
#          already uses) to confirm `model` was actually stamped and
#          note whether it came from a live AI call or served from the
#          library (either is legitimate depending on breaker/
#          inline-reuse state — see Part E's own comments for how it
#          tells the two apart).
#
# This is what surfaced the 2026-07-17 bug: org-submitted listings
# (scavenged=False, is_active=False) never showed up in ANY admin
# endpoint and could never be approved — see admin.py module
# docstring for the fix. Re-run this after any change to orgs.py,
# matching.py, polis.py, admin.py's listing endpoints, generate.py,
# or ai_client.py.
#
# Requires in backend/.env (same file ADMIN_KEY lives in):
#   TEST_LEARNER_EMAIL / TEST_LEARNER_PASSWORD  (required)
#   TEST_ORG_EMAIL / TEST_ORG_PASSWORD          (required)
# TEST_LEARNER can be at any avatar stage — the Polis section
# branches on whichever stage it finds and tests the checks that
# apply. Referendum vote/comment/upvote tests only run when
# E2E_POLIS_WRITE=1 is exported, since (unlike proposals/support,
# which this script cleans up after itself) there's no delete
# endpoint for votes or discussion comments — running that branch
# leaves a real [E2E TEST]-tagged comment and vote sitting in
# whatever open referendum it picks. Part E's DB lookup uses the same
# DB_USER/DB_PASSWORD/DB_HOST/DB_PORT/DB_NAME + mysql/mariadb-CLI-
# optional pattern as Part C — warns-and-skips the DB-level assertion
# (not the whole part) if the CLI isn't on the box.
# ============================================================
set -euo pipefail

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${APP_ROOT}/backend"
ENV_FILE="${BACKEND_DIR}/.env"
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

# Same pattern as smoke.sh — see that file for why "|| true" is load-bearing.
env_or_file() {
  local var_name="$1"
  local current="${!var_name:-}"
  if [ -n "$current" ]; then
    echo "$current"
    return 0
  fi
  { grep -E "^${var_name}=" "$ENV_FILE" | head -1 | cut -d'=' -f2- | sed -e 's/^"//' -e 's/"$//'; } || true
  return 0
}

TEST_LEARNER_EMAIL=$(env_or_file TEST_LEARNER_EMAIL)
TEST_LEARNER_PASSWORD=$(env_or_file TEST_LEARNER_PASSWORD)
TEST_ORG_EMAIL=$(env_or_file TEST_ORG_EMAIL)
TEST_ORG_PASSWORD=$(env_or_file TEST_ORG_PASSWORD)

if [ -z "$TEST_LEARNER_EMAIL" ] || [ -z "$TEST_LEARNER_PASSWORD" ]; then
  echo "SKIP  TEST_LEARNER_EMAIL/TEST_LEARNER_PASSWORD not set in $ENV_FILE — nothing to test"
  exit 0
fi
if [ -z "$TEST_ORG_EMAIL" ] || [ -z "$TEST_ORG_PASSWORD" ]; then
  echo "SKIP  TEST_ORG_EMAIL/TEST_ORG_PASSWORD not set in $ENV_FILE — nothing to test"
  exit 0
fi

# Same source of truth db.py reads from — used ONLY by Part C, to look up
# which learner an anonymized ai_suggested match belongs to. This is
# legitimate test-infra access (the script already runs as root on the
# server), not an API consumer bypassing the P11 consent model — the org
# and learner sessions above never see this, only the test assertions do.
DB_USER=$(env_or_file DB_USER); DB_USER="${DB_USER:-freqlearn}"
DB_PASSWORD=$(env_or_file DB_PASSWORD); DB_PASSWORD="${DB_PASSWORD:-changeme}"
DB_HOST=$(env_or_file DB_HOST); DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT=$(env_or_file DB_PORT); DB_PORT="${DB_PORT:-3306}"
DB_NAME=$(env_or_file DB_NAME); DB_NAME="${DB_NAME:-freqlearn}"
MYSQL_BIN=$(command -v mariadb || command -v mysql || true)

db_query() {
  # db_query "SELECT ..." -> single value, or '' if MYSQL_BIN missing / no rows
  [ -z "$MYSQL_BIN" ] && { echo ""; return 0; }
  "$MYSQL_BIN" -N -B -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" \
    -e "$1" 2>/dev/null | head -1
}

fail=0
pass() {
  local label="$1" code="$2" expected="$3"
  if [ "$code" != "$expected" ]; then
    echo "FAIL  $label -> HTTP $code (expected $expected)"
    echo "      body: $(echo "$HTTP_BODY" | head -c 300)"
    fail=$((fail+1))
  else
    echo "OK    $label"
  fi
}
note() { echo "NOTE  $1"; }
warn() { echo "WARN  $1"; }

# curl wrapper: sets HTTP_CODE + HTTP_BODY globals.
# call METHOD URL [JAR] [CSRF] [JSON_DATA]
call() {
  local method="$1" url="$2" jar="${3:-}" csrf="${4:-}" data="${5:-}"
  local args=(-s -X "$method" "$url" -w '\n%{http_code}' --max-time 10 -H "Content-Type: application/json")
  [ -n "$jar" ] && args+=(-b "$jar" -c "$jar")
  [ -n "$csrf" ] && args+=(-H "X-CSRF-Token: $csrf")
  [ -n "$data" ] && args+=(-d "$data")
  local raw
  raw=$(curl "${args[@]}")
  HTTP_CODE=$(echo "$raw" | tail -1)
  HTTP_BODY=$(echo "$raw" | sed '$d')
}

# json_get "key.subkey" <<< "$HTTP_BODY"  -> prints value, or '' on any error
json_get() {
  python3 -c "
import json, sys
path = sys.argv[1].split('.')
try:
    d = json.load(sys.stdin)
    for p in path:
        d = d[int(p)] if p.lstrip('-').isdigit() else d[p]
    print(d if not isinstance(d, (dict, list)) else json.dumps(d))
except Exception:
    print('')
" "$1"
}

csrf_from_jar() { awk -F'\t' -v name="$2" '$6==name{print $7}' "$1"; }

echo "== P2: Org + Polis end-to-end test =="
echo ""

# ------------------------------------------------------------
# PART A — Org listing lifecycle
# ------------------------------------------------------------
echo "-- Org listing lifecycle --"

OJAR=$(mktemp)
call POST "${API_BASE}/api/orgs/login" "$OJAR" "" \
  "{\"email\":\"${TEST_ORG_EMAIL}\",\"password\":\"${TEST_ORG_PASSWORD}\"}"
pass "org login" "$HTTP_CODE" "200"
ORG_NAME=$(echo "$HTTP_BODY" | json_get "org.name")
OCSRF=$(csrf_from_jar "$OJAR" fl_org_csrf)

TS=$(date +%s)
LISTING_TITLE="[E2E TEST] Trail volunteer ${TS}"
call POST "${API_BASE}/api/orgs/listings" "$OJAR" "$OCSRF" \
  "{\"title\":\"${LISTING_TITLE}\",\"description\":\"Automated e2e test listing — safe to ignore/delete.\",\"listing_type\":\"volunteer\",\"required_arts\":[]}"
pass "org creates listing" "$HTTP_CODE" "200"
LISTING_ID=$(echo "$HTTP_BODY" | json_get "listing.id")
PENDING=$(echo "$HTTP_BODY" | json_get "listing.pending_approval")
if [ "$PENDING" = "True" ]; then
  echo "OK    new listing is pending_approval"
else
  echo "FAIL  new listing should be pending_approval, got: $PENDING"; fail=$((fail+1))
fi

AJAR=$(mktemp)
call POST "${API_BASE}/api/admin/login" "$AJAR" "" "{\"admin_key\":\"${ADMIN_KEY}\"}"
pass "admin login" "$HTTP_CODE" "200"
ACSRF=$(csrf_from_jar "$AJAR" fl_admin_csrf)

call GET "${API_BASE}/api/admin/scavenger/listings" "$AJAR"
pass "admin sees review queue" "$HTTP_CODE" "200"
FOUND_SOURCE=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
rows = json.load(sys.stdin)
for r in rows:
    if str(r.get('id')) == '${LISTING_ID}':
        print(r.get('source', ''))
        break
")
if [ "$FOUND_SOURCE" = "org" ]; then
  echo "OK    org-submitted listing appears in admin review queue, tagged source=org"
else
  echo "FAIL  org-submitted listing NOT found in admin review queue (source='$FOUND_SOURCE') — this is the 2026-07-17 bug if it recurs"
  fail=$((fail+1))
fi

call PATCH "${API_BASE}/api/admin/scavenger/listings/${LISTING_ID}/approve" "$AJAR" "$ACSRF"
pass "admin approves listing" "$HTTP_CODE" "200"

LJAR=$(mktemp)
call POST "${API_BASE}/api/auth/login" "$LJAR" "" \
  "{\"email\":\"${TEST_LEARNER_EMAIL}\",\"password\":\"${TEST_LEARNER_PASSWORD}\"}"
pass "learner login" "$HTTP_CODE" "200"
LCSRF=$(csrf_from_jar "$LJAR" fl_csrf)

call GET "${API_BASE}/api/learners/me" "$LJAR"
pass "learner GET /me" "$HTTP_CODE" "200"
TEST_LEARNER_ID=$(echo "$HTTP_BODY" | json_get "id")

call GET "${API_BASE}/api/matching/listings" "$LJAR"
pass "learner GET listings" "$HTTP_CODE" "200"
VISIBLE=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
rows = json.load(sys.stdin)
print('yes' if any(str(r.get('id')) == '${LISTING_ID}' for r in rows) else 'no')
")
if [ "$VISIBLE" = "yes" ]; then
  echo "OK    approved listing is visible to learner"
else
  echo "FAIL  approved listing not visible to learner"; fail=$((fail+1))
fi

call POST "${API_BASE}/api/matching/" "$LJAR" "$LCSRF" "{\"listing_id\":${LISTING_ID}}"
pass "learner expresses interest" "$HTTP_CODE" "200"
MATCH_ID=$(echo "$HTTP_BODY" | json_get "id")

call GET "${API_BASE}/api/orgs/listings/${LISTING_ID}/matches" "$OJAR"
pass "org sees the match" "$HTTP_CODE" "200"
MATCH_VISIBLE=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
rows = json.load(sys.stdin)
print('yes' if any(str(r.get('match_id')) == '${MATCH_ID}' for r in rows) else 'no')
")
if [ "$MATCH_VISIBLE" = "yes" ]; then
  echo "OK    match_id ${MATCH_ID} visible in org's match list"
else
  echo "FAIL  match_id ${MATCH_ID} not visible in org's match list"; fail=$((fail+1))
fi

# Two-way Pnyx messaging
call POST "${API_BASE}/api/orgs/messages/${MATCH_ID}" "$OJAR" "$OCSRF" \
  '{"body":"[E2E TEST] Thanks for your interest!"}'
pass "org sends message" "$HTTP_CODE" "200"

call GET "${API_BASE}/api/matching/${MATCH_ID}/messages" "$LJAR"
pass "learner reads thread" "$HTTP_CODE" "200"
ORG_MSG_SEEN=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
rows = json.load(sys.stdin)
print('yes' if any(r.get('sender_type') == 'org' for r in rows) else 'no')
")
[ "$ORG_MSG_SEEN" = "yes" ] && echo "OK    learner sees org's message" || { echo "FAIL  learner does not see org's message"; fail=$((fail+1)); }

call POST "${API_BASE}/api/matching/${MATCH_ID}/messages" "$LJAR" "$LCSRF" \
  '{"body":"[E2E TEST] Looking forward to it!"}'
pass "learner replies" "$HTTP_CODE" "200"

call GET "${API_BASE}/api/orgs/messages/${MATCH_ID}" "$OJAR"
pass "org reads thread" "$HTTP_CODE" "200"
LEARNER_MSG_SEEN=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
rows = json.load(sys.stdin)
print('yes' if any(r.get('sender_type') == 'learner' for r in rows) else 'no')
")
[ "$LEARNER_MSG_SEEN" = "yes" ] && echo "OK    org sees learner's reply" || { echo "FAIL  org does not see learner's reply"; fail=$((fail+1)); }

call PATCH "${API_BASE}/api/orgs/listings/${LISTING_ID}/matches/${MATCH_ID}" "$OJAR" "$OCSRF" \
  '{"org_status":"reviewing"}'
pass "org updates match status" "$HTTP_CODE" "200"

# Cleanup — leaves the DB as close to untouched as this flow allows
call DELETE "${API_BASE}/api/matching/${MATCH_ID}" "$LJAR" "$LCSRF"
pass "learner withdraws interest (cleanup)" "$HTTP_CODE" "200"

call DELETE "${API_BASE}/api/orgs/listings/${LISTING_ID}" "$OJAR" "$OCSRF"
pass "org deactivates test listing (cleanup)" "$HTTP_CODE" "200"

echo ""

# ------------------------------------------------------------
# PART C — P11: AI needs-matching (Synergy)
# ------------------------------------------------------------
# Added 2026-07-24 alongside the P11 build. Covers the whole consent-model
# flow: org writes needs_text -> AI parses it into skill targets -> org
# generates AI-suggested matches -> those matches stay anonymized to the org
# AND invisible to the learner until the org notifies -> learner sees
# 'invited' -> learner accepts -> BOTH sides now see the real match (org
# gets identity, learner already saw the listing). Re-run this after any
# change to orgs.py's P11 endpoints or matching.py's accept/decline.
#
# Uses parse-needs' own real skill_id (rather than guessing one) so this
# stays valid against whatever the skills table actually contains, then
# overrides min_level to 0 before generate-matches — that makes every
# active learner trivially "meet" the target, so the test doesn't depend
# on TEST_LEARNER having practiced any particular skill.
echo "-- P11: AI needs-matching --"

P11_LISTING_TITLE="[E2E TEST] AI-matched need ${TS}"
call POST "${API_BASE}/api/orgs/listings" "$OJAR" "$OCSRF" \
  "{\"title\":\"${P11_LISTING_TITLE}\",\"description\":\"Automated e2e test listing for P11 — safe to ignore/delete.\",\"listing_type\":\"project\",\"required_arts\":[],\"needs_text\":\"Someone comfortable facilitating group discussions and basic first aid.\"}"
pass "org creates P11 test listing" "$HTTP_CODE" "200"
P11_LISTING_ID=$(echo "$HTTP_BODY" | json_get "listing.id")

TARGET_COUNT=0
call POST "${API_BASE}/api/orgs/listings/${P11_LISTING_ID}/parse-needs" "$OJAR" "$OCSRF"
if [ "$HTTP_CODE" = "200" ]; then
  echo "OK    parse-needs"
  TARGET_COUNT=$(echo "$HTTP_BODY" | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('needs_skill_targets',[])))")
  if [ "$TARGET_COUNT" -gt 0 ]; then
    echo "OK    parse-needs returned ${TARGET_COUNT} skill target(s)"
    FIRST_SKILL_ID=$(echo "$HTTP_BODY" | json_get "needs_skill_targets.0.skill_id")
    FIRST_SKILL_SLUG=$(echo "$HTTP_BODY" | json_get "needs_skill_targets.0.slug")
    call PATCH "${API_BASE}/api/orgs/listings/${P11_LISTING_ID}" "$OJAR" "$OCSRF" \
      "{\"needs_skill_targets\":[{\"skill_id\":${FIRST_SKILL_ID},\"slug\":\"${FIRST_SKILL_SLUG}\",\"name\":\"${FIRST_SKILL_SLUG}\",\"min_level\":0}]}"
    pass "org saves forced (min_level=0) skill target for deterministic test" "$HTTP_CODE" "200"
  else
    warn "parse-needs returned zero targets against the current skills table — skipping the rest of the P11 flow test"
  fi
elif [ "$HTTP_CODE" = "503" ]; then
  warn "parse-needs returned 503 (GROQ_API_KEY likely not configured) — skipping the rest of the P11 flow test"
else
  pass "parse-needs" "$HTTP_CODE" "200"
fi

if [ "$TARGET_COUNT" -gt 0 ]; then
  call POST "${API_BASE}/api/orgs/listings/${P11_LISTING_ID}/generate-matches" "$OJAR" "$OCSRF"
  pass "org generates AI matches" "$HTTP_CODE" "200"
  CREATED=$(echo "$HTTP_BODY" | json_get "created")
  note "generate-matches created ${CREATED} candidate(s) (min_level=0, so every active learner should qualify)"

  call GET "${API_BASE}/api/orgs/listings/${P11_LISTING_ID}/matches" "$OJAR"
  pass "org sees candidate list" "$HTTP_CODE" "200"

  # NOTE: generate-matches ranks ALL active learners, and with min_level=0
  # everyone ties at the same score — so "top 10" isn't guaranteed to
  # include TEST_LEARNER specifically if there are more than 10 active
  # learners on this deployment. The org's own view is anonymized by design
  # (that's the whole point of P11), so we can't identify "which candidate
  # is TEST_LEARNER" from that endpoint — we look it up directly in the DB
  # instead, the same way a human operator debugging this would.
  P11_MATCH_ID=$(db_query "SELECT id FROM opportunity_matches WHERE listing_id=${P11_LISTING_ID} AND learner_id=${TEST_LEARNER_ID};")

  if [ -z "$P11_MATCH_ID" ]; then
    warn "TEST_LEARNER (id ${TEST_LEARNER_ID}) wasn't selected into this run's top 10 — likely more than 10 active learners tied at the forced score. Skipping the rest of the P11 flow test (not a failure, just can't verify this run)."
  else
    ANON_NAME=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
rows = json.load(sys.stdin)
for r in rows:
    if str(r.get('match_id')) == '${P11_MATCH_ID}':
        print(r.get('display_name')); break
")
    if [[ "$ANON_NAME" == Candidate* ]]; then
      echo "OK    org sees TEST_LEARNER as an anonymized candidate (${ANON_NAME}), identity hidden"
    else
      echo "FAIL  expected TEST_LEARNER's match to appear anonymized as 'Candidate N', got '${ANON_NAME}'"; fail=$((fail+1))
    fi
  fi

  if [ -n "$P11_MATCH_ID" ]; then
    # Learner must NOT see this match yet — org hasn't notified them.
    call GET "${API_BASE}/api/matching/" "$LJAR"
    pass "learner GET my matches (pre-notify)" "$HTTP_CODE" "200"
    PRE_NOTIFY_VISIBLE=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
rows = json.load(sys.stdin)
print('yes' if any(str(r.get('id')) == '${P11_MATCH_ID}' for r in rows) else 'no')
")
    if [ "$PRE_NOTIFY_VISIBLE" = "no" ]; then
      echo "OK    learner does not see the un-notified AI match (consent model holds)"
    else
      echo "FAIL  learner sees an AI match the org hasn't notified them about yet"; fail=$((fail+1))
    fi

    call POST "${API_BASE}/api/orgs/listings/${P11_LISTING_ID}/matches/${P11_MATCH_ID}/notify" "$OJAR" "$OCSRF"
    pass "org notifies the candidate" "$HTTP_CODE" "200"

    # Notifying twice must be rejected — the endpoint requires learner_status=='suggested'.
    call POST "${API_BASE}/api/orgs/listings/${P11_LISTING_ID}/matches/${P11_MATCH_ID}/notify" "$OJAR" "$OCSRF"
    pass "re-notifying an already-invited candidate is rejected" "$HTTP_CODE" "400"

    call GET "${API_BASE}/api/matching/" "$LJAR"
    pass "learner GET my matches (post-notify)" "$HTTP_CODE" "200"
    INVITED_STATUS=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
rows = json.load(sys.stdin)
for r in rows:
    if str(r.get('id')) == '${P11_MATCH_ID}':
        print(r.get('learner_status')); break
")
    if [ "$INVITED_STATUS" = "invited" ]; then
      echo "OK    learner now sees the match with status=invited"
    else
      echo "FAIL  expected learner_status=invited after notify, got '${INVITED_STATUS}'"; fail=$((fail+1))
    fi

    call POST "${API_BASE}/api/matching/${P11_MATCH_ID}/accept" "$LJAR" "$LCSRF"
    pass "learner accepts the AI match" "$HTTP_CODE" "200"

    call GET "${API_BASE}/api/orgs/listings/${P11_LISTING_ID}/matches" "$OJAR"
    pass "org re-fetches candidate list after accept" "$HTTP_CODE" "200"
    REVEALED_NAME=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
rows = json.load(sys.stdin)
for r in rows:
    if str(r.get('match_id')) == '${P11_MATCH_ID}':
        print(r.get('display_name')); break
")
    if [ -n "$REVEALED_NAME" ] && [[ "$REVEALED_NAME" != Candidate* ]]; then
      echo "OK    org now sees the real learner identity (${REVEALED_NAME}) after acceptance"
    else
      echo "FAIL  org still sees an anonymized/candidate placeholder after acceptance"; fail=$((fail+1))
    fi

    # Cleanup — same pattern as PART A
    call DELETE "${API_BASE}/api/matching/${P11_MATCH_ID}" "$LJAR" "$LCSRF"
    pass "learner withdraws AI match (cleanup)" "$HTTP_CODE" "200"
  fi
fi

call DELETE "${API_BASE}/api/orgs/listings/${P11_LISTING_ID}" "$OJAR" "$OCSRF"
pass "org deactivates P11 test listing (cleanup)" "$HTTP_CODE" "200"

echo ""

# ------------------------------------------------------------
# PART D — P8: org validation (task line items + skill demonstrations)
# ------------------------------------------------------------
# Added 2026-07-25, using PART C above as the template per Charbel's own
# request. Covers: parse-needs now also returns needs_tasks -> org forces
# deterministic needs_skill_targets/needs_tasks (same override trick PART C
# uses for min_level, here so submit/verify steps reference a known
# task_index/skill_id rather than whatever Groq happened to generate) ->
# learner expresses interest (plain learner-initiated match, P8 doesn't care
# whether a match is ai_suggested or learner_initiated) -> validation is
# gated on org_status=='connected' (checked BOTH ways: 400 before, 200
# after) -> learner submits a task -> org verifies it -> org verifies a
# skill demonstration -> learner's own view reflects both -> the learner's
# aggregate /me/verified-skills and admin's two oversight endpoints both
# see it. Re-run this after any change to orgs.py/matching.py/learners.py's
# P8 endpoints or admin.py's Validation section.
echo "-- P8: org validation --"

P8_LISTING_TITLE="[E2E TEST] Validation flow ${TS}"
call POST "${API_BASE}/api/orgs/listings" "$OJAR" "$OCSRF" \
  "{\"title\":\"${P8_LISTING_TITLE}\",\"description\":\"Automated e2e test listing for P8 — safe to ignore/delete.\",\"listing_type\":\"project\",\"required_arts\":[],\"needs_text\":\"Someone comfortable facilitating group discussions and basic first aid.\"}"
pass "org creates P8 test listing" "$HTTP_CODE" "200"
P8_LISTING_ID=$(echo "$HTTP_BODY" | json_get "listing.id")

P8_TARGET_COUNT=0
call POST "${API_BASE}/api/orgs/listings/${P8_LISTING_ID}/parse-needs" "$OJAR" "$OCSRF"
if [ "$HTTP_CODE" = "200" ]; then
  echo "OK    parse-needs (P8 listing)"
  P8_TARGET_COUNT=$(echo "$HTTP_BODY" | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('needs_skill_targets',[])))")
  if [ "$P8_TARGET_COUNT" -gt 0 ]; then
    P8_SKILL_ID=$(echo "$HTTP_BODY" | json_get "needs_skill_targets.0.skill_id")
    P8_SKILL_SLUG=$(echo "$HTTP_BODY" | json_get "needs_skill_targets.0.slug")
    P8_TASK_TEXT="Facilitate one group discussion with a written recap"
    # Force deterministic needs_skill_targets + needs_tasks — same override
    # trick PART C uses for min_level, here so the submit/verify steps below
    # reference a known task_index (0) and skill_id regardless of what Groq
    # actually returned for this run.
    call PATCH "${API_BASE}/api/orgs/listings/${P8_LISTING_ID}" "$OJAR" "$OCSRF" \
      "{\"needs_skill_targets\":[{\"skill_id\":${P8_SKILL_ID},\"slug\":\"${P8_SKILL_SLUG}\",\"name\":\"${P8_SKILL_SLUG}\",\"min_level\":0}],\"needs_tasks\":[\"${P8_TASK_TEXT}\"]}"
    pass "org saves forced skill target + task line item for deterministic test" "$HTTP_CODE" "200"
  else
    warn "parse-needs returned zero targets against the current skills table — skipping the rest of the P8 flow test"
  fi
elif [ "$HTTP_CODE" = "503" ]; then
  warn "parse-needs returned 503 (GROQ_API_KEY likely not configured) — skipping the rest of the P8 flow test"
else
  pass "parse-needs (P8 listing)" "$HTTP_CODE" "200"
fi

if [ "$P8_TARGET_COUNT" -gt 0 ]; then
  call POST "${API_BASE}/api/matching/" "$LJAR" "$LCSRF" "{\"listing_id\":${P8_LISTING_ID}}"
  pass "learner expresses interest (P8 listing)" "$HTTP_CODE" "200"
  P8_MATCH_ID=$(echo "$HTTP_BODY" | json_get "id")

  # Gate check: validation must be closed before the org marks the match connected.
  call GET "${API_BASE}/api/orgs/matches/${P8_MATCH_ID}/validation" "$OJAR"
  pass "org validation blocked before match is connected" "$HTTP_CODE" "400"
  call GET "${API_BASE}/api/matching/${P8_MATCH_ID}/validation" "$LJAR"
  pass "learner validation blocked before match is connected" "$HTTP_CODE" "400"

  call PATCH "${API_BASE}/api/orgs/listings/${P8_LISTING_ID}/matches/${P8_MATCH_ID}" "$OJAR" "$OCSRF" \
    '{"org_status":"connected"}'
  pass "org marks match connected" "$HTTP_CODE" "200"

  call GET "${API_BASE}/api/orgs/matches/${P8_MATCH_ID}/validation" "$OJAR"
  pass "org validation opens once connected" "$HTTP_CODE" "200"
  TASK0_STATUS=$(echo "$HTTP_BODY" | json_get "tasks.0.status")
  [ "$TASK0_STATUS" = "open" ] && echo "OK    task line item starts as 'open'" || { echo "FAIL  expected task status 'open', got '${TASK0_STATUS}'"; fail=$((fail+1)); }

  call POST "${API_BASE}/api/matching/${P8_MATCH_ID}/tasks/0/submit" "$LJAR" "$LCSRF" \
    '{"note":"[E2E TEST] Ran the discussion and wrote up a recap doc."}'
  pass "learner submits task line item" "$HTTP_CODE" "200"

  call GET "${API_BASE}/api/orgs/matches/${P8_MATCH_ID}/validation" "$OJAR"
  pass "org re-fetches validation after learner submission" "$HTTP_CODE" "200"
  TASK0_STATUS2=$(echo "$HTTP_BODY" | json_get "tasks.0.status")
  [ "$TASK0_STATUS2" = "submitted" ] && echo "OK    task line item now 'submitted'" || { echo "FAIL  expected task status 'submitted', got '${TASK0_STATUS2}'"; fail=$((fail+1)); }

  call POST "${API_BASE}/api/orgs/matches/${P8_MATCH_ID}/tasks/0/verify" "$OJAR" "$OCSRF" \
    '{"status":"verified","verified_by":"[E2E TEST] rep"}'
  pass "org verifies the task line item" "$HTTP_CODE" "200"

  call POST "${API_BASE}/api/orgs/matches/${P8_MATCH_ID}/skills/${P8_SKILL_ID}/verify" "$OJAR" "$OCSRF" \
    '{"level":"proficient","session_ids":[],"note":"[E2E TEST] facilitated well","verified_by":"[E2E TEST] rep"}'
  pass "org verifies the skill demonstration" "$HTTP_CODE" "200"

  call GET "${API_BASE}/api/matching/${P8_MATCH_ID}/validation" "$LJAR"
  pass "learner sees both verifications" "$HTTP_CODE" "200"
  LEARNER_TASK_STATUS=$(echo "$HTTP_BODY" | json_get "tasks.0.status")
  LEARNER_SKILL_LEVEL=$(echo "$HTTP_BODY" | json_get "skills.0.level")
  [ "$LEARNER_TASK_STATUS" = "verified" ] && echo "OK    learner's own view shows task 'verified'" || { echo "FAIL  expected learner-side task status 'verified', got '${LEARNER_TASK_STATUS}'"; fail=$((fail+1)); }
  [ "$LEARNER_SKILL_LEVEL" = "proficient" ] && echo "OK    learner's own view shows skill level 'proficient'" || { echo "FAIL  expected learner-side skill level 'proficient', got '${LEARNER_SKILL_LEVEL}'"; fail=$((fail+1)); }

  call GET "${API_BASE}/api/learners/me/verified-skills" "$LJAR"
  pass "learner's aggregate verified-skills list" "$HTTP_CODE" "200"
  AGG_HAS_IT=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
rows = json.load(sys.stdin)
print('yes' if any(r.get('listing_title') == '${P8_LISTING_TITLE}' and r.get('level') == 'proficient' for r in rows) else 'no')
")
  [ "$AGG_HAS_IT" = "yes" ] && echo "OK    org-verified skill appears in learner's aggregate list" || { echo "FAIL  org-verified skill missing from learner's aggregate list"; fail=$((fail+1)); }

  call GET "${API_BASE}/api/admin/verified-skills" "$AJAR"
  pass "admin sees the verified skill" "$HTTP_CODE" "200"
  ADMIN_SKILL_SEEN=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
rows = json.load(sys.stdin)
print('yes' if any(r.get('match_id') == ${P8_MATCH_ID} for r in rows) else 'no')
")
  [ "$ADMIN_SKILL_SEEN" = "yes" ] && echo "OK    admin Validation page lists this match's verified skill" || { echo "FAIL  admin does not see this match's verified skill"; fail=$((fail+1)); }

  call GET "${API_BASE}/api/admin/task-completions" "$AJAR"
  pass "admin sees the task completion" "$HTTP_CODE" "200"
  ADMIN_TASK_SEEN=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
rows = json.load(sys.stdin)
print('yes' if any(r.get('match_id') == ${P8_MATCH_ID} and r.get('status') == 'verified' for r in rows) else 'no')
")
  [ "$ADMIN_TASK_SEEN" = "yes" ] && echo "OK    admin Validation page lists this match's verified task, status=verified" || { echo "FAIL  admin does not see this match's task completion as verified"; fail=$((fail+1)); }

  # Cleanup — same pattern as PART A/C. task_completions/verified_skills rows
  # are left in place (harmless, tagged [E2E TEST] via the listing title they
  # join back to) since withdraw is a soft-delete (learner_status='withdrawn',
  # the match row itself isn't removed) and there's no delete endpoint for
  # these two tables — deleting them isn't part of what P8 exposes to either
  # side, by design (an org's validation is meant to be a durable record).
  call DELETE "${API_BASE}/api/matching/${P8_MATCH_ID}" "$LJAR" "$LCSRF"
  pass "learner withdraws P8 test match (cleanup)" "$HTTP_CODE" "200"
fi

call DELETE "${API_BASE}/api/orgs/listings/${P8_LISTING_ID}" "$OJAR" "$OCSRF"
pass "org deactivates P8 test listing (cleanup)" "$HTTP_CODE" "200"

echo ""

# ------------------------------------------------------------
# PART B — Polis
# ------------------------------------------------------------
echo "-- Polis --"

call GET "${API_BASE}/api/polis/my-access" "$LJAR"
pass "GET my-access" "$HTTP_CODE" "200"
STAGE_KEY=$(echo "$HTTP_BODY" | json_get "key")
CAN_POLIS=$(echo "$HTTP_BODY" | json_get "can_access_polis")
note "TEST_LEARNER stage=${STAGE_KEY} can_access_polis=${CAN_POLIS}"

call GET "${API_BASE}/api/polis/referenda" "$LJAR"
pass "GET referenda (unfiltered)" "$HTTP_CODE" "200"
REF_COUNT=$(echo "$HTTP_BODY" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")
FIRST_REF_ID=$(echo "$HTTP_BODY" | json_get "0.id")
note "${REF_COUNT} open referendum/a found"

call GET "${API_BASE}/api/polis/referenda?scope=local" "$LJAR"
pass "GET referenda?scope=local" "$HTTP_CODE" "200"

call GET "${API_BASE}/api/polis/referenda?scope=not-a-real-scope" "$LJAR"
pass "GET referenda?scope=<invalid> rejected" "$HTTP_CODE" "400"

call GET "${API_BASE}/api/polis/proposals" "$LJAR"
pass "GET proposals" "$HTTP_CODE" "200"

if [ "$CAN_POLIS" = "True" ]; then
  echo "  (Grove+ — testing write endpoints)"

  PROP_TITLE="[E2E TEST] proposal ${TS}"
  call POST "${API_BASE}/api/polis/proposals" "$LJAR" "$LCSRF" \
    "{\"title\":\"${PROP_TITLE}\",\"description\":\"Automated e2e test — safe to ignore/delete.\",\"scope\":\"local\"}"
  pass "submit local proposal (Grove+ allowed)" "$HTTP_CODE" "200"
  PROP_ID=$(echo "$HTTP_BODY" | json_get "id")

  call POST "${API_BASE}/api/polis/proposals/${PROP_ID}/support" "$LJAR" "$LCSRF"
  pass "support own proposal" "$HTTP_CODE" "200"
  SUPPORTED=$(echo "$HTTP_BODY" | json_get "supported")
  [ "$SUPPORTED" = "True" ] && echo "OK    supported=true on first toggle" || { echo "FAIL  expected supported=true, got $SUPPORTED"; fail=$((fail+1)); }

  call POST "${API_BASE}/api/polis/proposals/${PROP_ID}/support" "$LJAR" "$LCSRF"
  pass "un-support own proposal (cleanup toggle)" "$HTTP_CODE" "200"
  SUPPORTED2=$(echo "$HTTP_BODY" | json_get "supported")
  [ "$SUPPORTED2" = "False" ] && echo "OK    supported=false on second toggle (dedup works)" || { echo "FAIL  expected supported=false, got $SUPPORTED2"; fail=$((fail+1)); }

  if [ "$STAGE_KEY" != "ecosystem" ]; then
    call POST "${API_BASE}/api/polis/proposals" "$LJAR" "$LCSRF" \
      "{\"title\":\"[E2E TEST] should be rejected\",\"scope\":\"global\"}"
    pass "global proposal blocked below Ecosystem stage" "$HTTP_CODE" "403"
  else
    note "TEST_LEARNER is already Ecosystem stage — skipping the below-Ecosystem global-scope-block check"
  fi

  if [ -n "$FIRST_REF_ID" ] && [ "${E2E_POLIS_WRITE:-0}" = "1" ]; then
    echo "  (E2E_POLIS_WRITE=1 — testing vote/discussion on referendum ${FIRST_REF_ID}; NOT auto-cleaned-up)"
    call POST "${API_BASE}/api/polis/referenda/${FIRST_REF_ID}/vote" "$LJAR" "$LCSRF" '{"position":"abstain"}'
    pass "cast vote (abstain)" "$HTTP_CODE" "200"

    call GET "${API_BASE}/api/polis/referenda/${FIRST_REF_ID}/discussion" "$LJAR"
    pass "GET discussion" "$HTTP_CODE" "200"

    call POST "${API_BASE}/api/polis/referenda/${FIRST_REF_ID}/discussion" "$LJAR" "$LCSRF" \
      '{"body":"[E2E TEST] automated check — feel free to delete"}'
    pass "post discussion comment" "$HTTP_CODE" "200"
    COMMENT_ID=$(echo "$HTTP_BODY" | json_get "id")

    call POST "${API_BASE}/api/polis/referenda/${FIRST_REF_ID}/discussion/${COMMENT_ID}/upvote" "$LJAR" "$LCSRF"
    pass "upvote own comment" "$HTTP_CODE" "200"
    call POST "${API_BASE}/api/polis/referenda/${FIRST_REF_ID}/discussion/${COMMENT_ID}/upvote" "$LJAR" "$LCSRF"
    ALREADY=$(echo "$HTTP_BODY" | json_get "already_upvoted")
    [ "$ALREADY" = "True" ] && echo "OK    duplicate upvote deduped (already_upvoted=true)" || { echo "FAIL  duplicate upvote not deduped"; fail=$((fail+1)); }
  elif [ -n "$FIRST_REF_ID" ]; then
    note "referenda exist but E2E_POLIS_WRITE!=1 — skipping vote/discussion/upvote (no delete endpoint exists to clean these up; export E2E_POLIS_WRITE=1 to opt in)"
  else
    note "no open referenda to test vote/discussion/upvote against — seed one via polis_migrate.sql or add_polis_tables.sql if you want that path covered"
  fi
else
  echo "  (below Grove — testing the write gate)"
  call POST "${API_BASE}/api/polis/proposals" "$LJAR" "$LCSRF" \
    '{"title":"[E2E TEST] should be rejected","scope":"local"}'
  pass "proposal blocked below Grove stage" "$HTTP_CODE" "403"
fi

echo ""

# ------------------------------------------------------------
# PART E — AI session generation (P42, 2026-08-01)
#
# The actual gap that let P41 ship a `_bool_setting` NameError past both
# smoke.sh AND this script: neither one had ever called
# POST /api/generate/session with a real learner session. That route ran
# fine right up until it hit a bare NameError near the top of every
# request (before any AI-provider logic even started) -- 500 in the live
# app, clean everywhere else. This part closes that gap by actually
# calling it and checking the response is a real, fully-populated
# GeneratedSession, not just a 200 status code.
# ------------------------------------------------------------
echo "-- AI session generation --"

# Baseline breaker state before the call, purely for context in the
# output below -- not asserted against, since "already tripped" is a
# legitimate state this test shouldn't fight with or reset.
call GET "${API_BASE}/api/generate/breaker-status" ""
BREAKER_BEFORE=$(echo "$HTTP_BODY" | json_get "library_mode")
note "session breaker library_mode=${BREAKER_BEFORE} before the call"

call POST "${API_BASE}/api/generate/session" "$LJAR" "$LCSRF" \
  '{"art_slug":"move","phase_slug":"adult","language":"en"}'
pass "POST /api/generate/session" "$HTTP_CODE" "200"

if [ "$HTTP_CODE" = "200" ]; then
  # Check every required GeneratedSession field actually came back non-
  # empty -- this is the real regression check. A route that 500s never
  # gets here (caught by the "pass" line above); a route that returns 200
  # with e.g. an empty warmup_prompt would sail through a status-code-only
  # check the way P41's bug slipped past the old scripts.
  GEN_OK=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
d = json.load(sys.stdin)
required_text = ['warmup_prompt','explore_content','challenge_prompt','reflect_prompt','title','art_name','art_slug']
missing = [k for k in required_text if not (d.get(k) or '').strip()]
aq = d.get('assess_question') or {}
if not (aq.get('question') or '').strip():
    missing.append('assess_question.question')
opts = aq.get('options') or []
if len(opts) < 2:
    missing.append('assess_question.options (need >=2)')
ci = aq.get('correct_index')
if not isinstance(ci, int) or not (0 <= ci < len(opts)):
    missing.append('assess_question.correct_index (out of range)')
print('MISSING:' + ','.join(missing) if missing else 'OK')
")
  if [ "$GEN_OK" = "OK" ]; then
    echo "OK    generated session has all required fields populated"
  else
    echo "FAIL  generated session missing/invalid fields -- ${GEN_OK#MISSING:}"; fail=$((fail+1))
  fi

  SESSION_ID=$(echo "$HTTP_BODY" | json_get "session_id")
  if [ -n "$SESSION_ID" ] && [ "$SESSION_ID" != "None" ]; then
    echo "OK    session_id=${SESSION_ID} returned"

    # DB-level proof of which path actually served this request. Same
    # db_query() / MYSQL_BIN pattern Part C already uses -- warns and
    # skips just this assertion (not the whole part) if the CLI isn't
    # on the box, same as Part C's own fallback.
    if [ -n "$MYSQL_BIN" ]; then
      SESSION_MODEL=$(db_query "SELECT model FROM sessions WHERE id=${SESSION_ID};")
      SESSION_LATENCY=$(db_query "SELECT latency_ms FROM sessions WHERE id=${SESSION_ID};")
      if [ -z "$SESSION_MODEL" ]; then
        warn "could not read sessions.model for id=${SESSION_ID} (DB lookup failed or CLI not usable) -- skipping this assertion"
      elif [ "$SESSION_MODEL" = "library" ]; then
        # Legitimate in two cases: the breaker was already tripped (noted
        # above) or an admin has ai_inline_reuse_enabled=true in Settings
        # (off by default -- see generate.py's module comment). Either
        # way this is a real, non-buggy outcome of the reuse/breaker
        # logic, not evidence of the P41-style failure this part exists
        # to catch -- so it's a WARN prompting a manual look, not a FAIL.
        warn "sessions.model='library' for id=${SESSION_ID} -- expected if the breaker is tripped or ai_inline_reuse_enabled is on; check admin Settings/AI status if this is unexpected"
      else
        echo "OK    sessions.model='${SESSION_MODEL}' (latency_ms=${SESSION_LATENCY:-?}) -- a real AI call actually answered, not a silent library fallback"
      fi
    else
      warn "mysql/mariadb CLI not found -- skipping sessions.model DB-level check (HTTP-level checks above still ran)"
    fi
  else
    echo "FAIL  no session_id in response"; fail=$((fail+1))
  fi
fi

# Breaker status after -- a successful call (AI or library) always leaves
# consecutive_failures at 0 (record_success() resets it; the library
# path never touches the breaker at all), so this is a light sanity
# check, not the main assertion above.
call GET "${API_BASE}/api/generate/breaker-status" ""
BREAKER_AFTER_FAILURES=$(echo "$HTTP_BODY" | json_get "consecutive_failures")
[ "$BREAKER_AFTER_FAILURES" = "0" ] && echo "OK    breaker consecutive_failures=0 after the call" || warn "breaker consecutive_failures=${BREAKER_AFTER_FAILURES} after the call -- worth a look if unexpected"

# No cleanup: this is a real, ordinary session for TEST_LEARNER (same as
# one they'd get from actually using the app) -- there's no [E2E TEST]
# tag on it and no delete endpoint for sessions, so it's left in place on
# purpose, same as P8/P11's verified_skills/task_completions rows above.

# Logout both sessions
call POST "${API_BASE}/api/orgs/logout" "$OJAR" "$OCSRF"
pass "org logout" "$HTTP_CODE" "200"
call POST "${API_BASE}/api/auth/logout" "$LJAR" "$LCSRF"
pass "learner logout" "$HTTP_CODE" "200"

rm -f "$OJAR" "$AJAR" "$LJAR"

echo ""
if [ "$fail" -ne 0 ]; then
  echo "E2E ORG+POLIS TEST FAILED ($fail failure(s))"
  exit 1
fi
echo "All Org + Polis end-to-end checks healthy."
