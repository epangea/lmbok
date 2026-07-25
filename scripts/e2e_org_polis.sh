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
#   Polis: my-access -> referenda read (incl. scope filter + bad
#          scope 400) -> proposals read -> Grove+ write checks
#          (submit local proposal, support/unsupport toggle, scope
#          gate on global proposal) OR the below-Grove 403 gate,
#          whichever applies to TEST_LEARNER's current stage.
#
# This is what surfaced the 2026-07-17 bug: org-submitted listings
# (scavenged=False, is_active=False) never showed up in ANY admin
# endpoint and could never be approved — see admin.py module
# docstring for the fix. Re-run this after any change to orgs.py,
# matching.py, polis.py, or admin.py's listing endpoints.
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
# whatever open referendum it picks.
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
