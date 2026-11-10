#!/usr/bin/env bash
# ============================================================
# FreqLearn, scripts/verify_portfolio.sh   (2026-11-03)
#
# Live checks for the 2026-11-01 learner-portfolio changes (PROJECT.md
# PART 43, backlog 2026.177-180). Run it like smoke.sh:
#
#     scripts/verify_portfolio.sh
#     VERIFY_WRITES=1 scripts/verify_portfolio.sh     # also runs Part D
#
# What it checks
#   A  Settings        ai_include_learner_portfolio / ai_include_prior_context /
#                      ai_inline_reuse_enabled, warns if any of them would stop
#                      the portfolio from reaching a prompt.
#   B  Prompt blocks   Runs the REAL continuity query and portfolio builder
#                      against MariaDB for the test learner (the sandbox tests
#                      ran on sqlite): the queries execute, the block builds
#                      from the learner's profile, the journey additions are a
#                      superset of the legacy block. Prints lengths and yes/no
#                      only, never the profile or response text.
#   C  Generation      First checks GET /api/learners/me returns learner_profile
#                      (the My Story card and the profile the client sends back
#                      to companions/distiller depend on it). Then a real POST /api/generate/session for a land art ("grow")
#                      as the test learner: 200, fields populated, a real AI
#                      model answered (not a library fallback). If the learner
#                      has a bioregion set, notes whether the generated text
#                      mentions it (informational, a model may paraphrase, so
#                      this is never a FAIL).
#   D  Growth rule     ONLY with VERIFY_WRITES=1 (see side effects below).
#                      Completes one session with empty challenge+reflection
#                      -> counted_toward_growth=false and the primary skill's
#                      evidence is unchanged, the session is still saved.
#                      Completes a second session with a real sentence ->
#                      counted_toward_growth=true and evidence +1 (or a
#                      level-up, which resets evidence to 0).
#   E  Frontend        The served app.js and the en/fr language files contain
#                      the new reflect-screen hint. A script cannot see the
#                      screen: hard-refresh a browser to confirm it visually
#                      (the service worker caches the app shell).
#                      Also (2026-11-07): the Refresh bioregion button and the
#                      map's "you are here" strings are deployed.
#   F  Journey log     (2026-11-06, Phase 2) Read-only. Both journey tables
#                      exist (scripts/2026-11-06-journey-log.sql was run) and
#                      the served app.js labels session distillations
#                      source=session. Reports the test learner's profile
#                      version count (informational: it grows as My Story is
#                      updated, never as a result of this script).
#                      (2026-11-07, patch C) Also GET /api/learners/me/journey and
#                      /me/profile-history return 200, the Journey tab strings
#                      are deployed (app.js, en/fr), and with VERIFY_WRITES=1 the
#                      session Part D completed has exactly one journey entry in
#                      the database and in the API response.
#
# Requires in backend/.env (same as e2e_org_polis.sh):
#   ADMIN_KEY, TEST_LEARNER_EMAIL / TEST_LEARNER_PASSWORD
# Optional overrides, to run against a different learner (recommended for
# Part D, see below): VERIFY_LEARNER_EMAIL / VERIFY_LEARNER_PASSWORD.
# Part B needs backend/venv/bin/python; Parts B-D use the mysql/mariadb CLI
# (same db_query() pattern as e2e_org_polis.sh) and warn-and-skip if the CLI
# or venv is missing.
#
# SIDE EFFECTS
#   Part C creates one session row (same as e2e_org_polis.sh Part E).
#   Part D (VERIFY_WRITES=1) marks 2 sessions completed for the test learner
#   and, for the second, adds +1 evidence to a skill. That is real progress
#   on a real account, and it can't be cleaned up through the API. Use a
#   dedicated test learner via VERIFY_LEARNER_EMAIL/PASSWORD if TEST_LEARNER
#   is an account you care about. xp_earned is sent as 0 so XP isn't inflated;
#   the streak and radar snapshot still record the sessions.
#   This script never modifies the learner's profile, bioregion or any setting.
# ============================================================
set -euo pipefail

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${APP_ROOT}/backend"
ENV_FILE="${BACKEND_DIR}/.env"
API_BASE="${API_BASE:-https://build.onehouse.top}"
VERIFY_WRITES="${VERIFY_WRITES:-0}"
AI_GEN_MAX_TIME=160   # same reasoning as e2e_org_polis.sh: the AI chain can take a while

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found"
  exit 1
fi

# Same pattern as smoke.sh / e2e_org_polis.sh, "|| true" is load-bearing under set -e.
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

ADMIN_KEY=$(env_or_file ADMIN_KEY)
if [ -z "$ADMIN_KEY" ]; then
  echo "ERROR: ADMIN_KEY not set in $ENV_FILE"
  exit 1
fi

LEARNER_EMAIL="${VERIFY_LEARNER_EMAIL:-$(env_or_file TEST_LEARNER_EMAIL)}"
LEARNER_PASSWORD="${VERIFY_LEARNER_PASSWORD:-$(env_or_file TEST_LEARNER_PASSWORD)}"
if [ -z "$LEARNER_EMAIL" ] || [ -z "$LEARNER_PASSWORD" ]; then
  echo "SKIP  no learner credentials (TEST_LEARNER_* in $ENV_FILE, or VERIFY_LEARNER_*), nothing to test"
  exit 0
fi

DB_USER=$(env_or_file DB_USER);         DB_USER="${DB_USER:-freqlearn}"
DB_PASSWORD=$(env_or_file DB_PASSWORD); DB_PASSWORD="${DB_PASSWORD:-changeme}"
DB_HOST=$(env_or_file DB_HOST);         DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT=$(env_or_file DB_PORT);         DB_PORT="${DB_PORT:-3306}"
DB_NAME=$(env_or_file DB_NAME);         DB_NAME="${DB_NAME:-freqlearn}"
MYSQL_BIN=$(command -v mariadb || command -v mysql || true)
VENV_PY="${BACKEND_DIR}/venv/bin/python"

db_query() {
  # db_query "SELECT ..." -> first row, or '' if the CLI is missing / no rows
  [ -z "$MYSQL_BIN" ] && { echo ""; return 0; }
  "$MYSQL_BIN" -N -B -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" \
    -e "$1" 2>/dev/null | head -1 || true
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
ok()   { echo "OK    $1"; }
bad()  { echo "FAIL  $1"; fail=$((fail+1)); }
note() { echo "NOTE  $1"; }
warn() { echo "WARN  $1"; }

# call METHOD URL [JAR] [CSRF] [JSON_DATA] [MAX_TIME]  -> sets HTTP_CODE, HTTP_BODY
call() {
  local method="$1" url="$2" jar="${3:-}" csrf="${4:-}" data="${5:-}" max_time="${6:-10}"
  local args=(-s -X "$method" "$url" -w '\n%{http_code}' --max-time "$max_time" -H "Content-Type: application/json")
  [ -n "$jar" ] && args+=(-b "$jar" -c "$jar")
  [ -n "$csrf" ] && args+=(-H "X-CSRF-Token: $csrf")
  [ -n "$data" ] && args+=(-d "$data")
  local raw
  raw=$(curl "${args[@]}")
  HTTP_CODE=$(echo "$raw" | tail -1)
  HTTP_BODY=$(echo "$raw" | sed '$d')
}

# json_get "key.subkey" <<< "$HTTP_BODY"  -> value, or '' on any error
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

AJAR=$(mktemp); LJAR=$(mktemp)
trap 'rm -f "$AJAR" "$LJAR"' EXIT

echo "== Learner portfolio live checks (PART 43) =="
echo ""

# ------------------------------------------------------------
# PART A, settings that decide whether the portfolio can reach a prompt
# ------------------------------------------------------------
echo "-- A: settings --"
call POST "${API_BASE}/api/admin/login" "$AJAR" "" "{\"admin_key\":\"${ADMIN_KEY}\"}"
pass "admin login" "$HTTP_CODE" "200"
call GET "${API_BASE}/api/admin/settings" "$AJAR"
pass "GET admin settings" "$HTTP_CODE" "200"
SETTINGS_BODY="$HTTP_BODY"

S_PORTFOLIO=$(echo "$SETTINGS_BODY" | json_get "settings.ai_include_learner_portfolio.value")
S_PRIOR=$(echo "$SETTINGS_BODY"     | json_get "settings.ai_include_prior_context.value")
S_REUSE=$(echo "$SETTINGS_BODY"     | json_get "settings.ai_inline_reuse_enabled.value")

case "$(echo "${S_PORTFOLIO}" | tr '[:upper:]' '[:lower:]')" in
  "")    ok "ai_include_learner_portfolio has no row -> code default (true) applies; run scripts/2026-11-01-learner-portfolio-setting.sql if you want the toggle visible in admin Settings" ;;
  true|1|yes|on) ok "ai_include_learner_portfolio=${S_PORTFOLIO}" ;;
  *)     warn "ai_include_learner_portfolio=${S_PORTFOLIO}, the portfolio block and journey additions are OFF; Parts B-D below will not reflect them in real prompts" ;;
esac
case "$(echo "${S_PRIOR}" | tr '[:upper:]' '[:lower:]')" in
  false|0|no|off) warn "ai_include_prior_context=${S_PRIOR}, the whole continuity block is OFF" ;;
  *) ok "ai_include_prior_context is on (${S_PRIOR:-default true})" ;;
esac
case "$(echo "${S_REUSE}" | tr '[:upper:]' '[:lower:]')" in
  true|1|yes|on) warn "ai_inline_reuse_enabled=${S_REUSE}, stored sessions can pre-empt the AI call, so the portfolio is skipped for those requests" ;;
  *) ok "ai_inline_reuse_enabled is off (${S_REUSE:-default false})" ;;
esac
echo ""

# ------------------------------------------------------------
# PART B, the real prompt-building code against MariaDB
# ------------------------------------------------------------
echo "-- B: prompt blocks against the real database --"
LEARNER_ID=""; BIOREGION=""; PROFILE_LEN=""
if [ ! -x "$VENV_PY" ]; then
  warn "backend venv python not found at $VENV_PY, skipping Part B"
else
  B_PY=$(mktemp)
  trap 'rm -f "$AJAR" "$LJAR" "$B_PY"' EXIT
  cat > "$B_PY" <<'PY'
import asyncio, os, sys
sys.path.insert(0, os.getcwd())

async def main():
    from sqlalchemy import select
    from db import AsyncSessionLocal, engine
    import models
    from prior_session_context import get_prior_session_context, build_portfolio_block
    email = os.environ["VERIFY_EMAIL"]
    async with AsyncSessionLocal() as db:
        l = (await db.execute(select(models.Learner).where(models.Learner.email == email))).scalar_one_or_none()
        if not l:
            print("learner_found=0"); return
        print("learner_found=1")
        print(f"learner_id={l.id}")
        prof = (l.learner_profile or "").strip()
        print(f"profile_len={len(prof)}")
        print("bioregion=" + (l.bioregion or "").replace("\n", " ").strip())
        print(f"portfolio_block_len={len(build_portfolio_block(l.learner_profile))}")
        art = (await db.execute(select(models.Arts).where(models.Arts.slug == "grow"))).scalar_one_or_none()
        if not art:
            print("ERROR=art 'grow' not found"); return
        legacy  = await get_prior_session_context(db, l.id, art.id, None, 3, include_journey=False)
        journey = await get_prior_session_context(db, l.id, art.id, None, 3, include_journey=True)
        print(f"continuity_legacy_len={len(legacy)}")
        print(f"continuity_journey_len={len(journey)}")
        print("journey_has_excerpt=" + ("1" if "(excerpt)" in journey else "0"))
        print("journey_has_cross_art=" + ("1" if "RECENT JOURNEY ACROSS OTHER ARTS" in journey else "0"))
    await engine.dispose()

try:
    asyncio.run(main())
except Exception as e:
    print("ERROR=" + repr(e)[:300])
PY
  B_OUT=$(cd "$BACKEND_DIR" && VERIFY_EMAIL="$LEARNER_EMAIL" "$VENV_PY" "$B_PY" 2>/dev/null || true)
  getv() { { echo "$B_OUT" | grep -E "^$1=" | head -1 | cut -d'=' -f2-; } || true; }
  B_ERR=$(getv ERROR)
  if [ -n "$B_ERR" ]; then
    bad "Part B raised an error against the live DB: $B_ERR"
  elif [ -z "$B_OUT" ]; then
    warn "Part B produced no output (venv/import problem?), run it by hand: cd backend && venv/bin/python -c 'import prior_session_context'"
  elif [ "$(getv learner_found)" != "1" ]; then
    bad "no learner with email ${LEARNER_EMAIL} in the database"
  else
    LEARNER_ID=$(getv learner_id); BIOREGION=$(getv bioregion)
    ok "continuity + portfolio code runs against MariaDB for learner id ${LEARNER_ID}"
    PROFILE_LEN=$(getv profile_len); PB_LEN=$(getv portfolio_block_len)
    LEG=$(getv continuity_legacy_len); JOU=$(getv continuity_journey_len)
    if [ "${PROFILE_LEN:-0}" -gt 0 ]; then
      note "learner has a My Story profile (${PROFILE_LEN} chars)"
      if [ "${PROFILE_LEN}" -lt 120 ]; then
        warn "My Story is only ${PROFILE_LEN} chars. A short profile that is just a BIOREGION line usually means an older build overwrote it from an empty browser copy (fixed 2026-11-07). Compare with the latest rows of learner_profile_versions and with a database backup."
      fi
      if [ "${PB_LEN:-0}" -gt 0 ]; then ok "portfolio block builds from the profile (${PB_LEN} chars)"; else bad "profile is non-empty but the portfolio block is empty"; fi
    else
      warn "this learner has NO My Story yet, the portfolio block is empty for this account, so the main change cannot be exercised here. Finish a session with a written reflection first, or set VERIFY_LEARNER_EMAIL to a learner who has one."
    fi
    if [ "${JOU:-0}" -ge "${LEG:-0}" ]; then
      ok "journey continuity (${JOU} chars) is a superset of the legacy block (${LEG} chars)"
    else
      bad "journey continuity (${JOU}) is shorter than the legacy block (${LEG})"
    fi
    note "journey excerpts present: $(getv journey_has_excerpt) | cross-art list present: $(getv journey_has_cross_art)  (1 = yes; 0 is normal if the learner has no matching completed sessions)"
    [ -n "$BIOREGION" ] && note "learner bioregion on file: ${BIOREGION}" || note "learner has no bioregion on file, the restored bioregion line is skipped for this account"
  fi
fi
echo ""

# ------------------------------------------------------------
# PART C, a real generation call as the test learner
# ------------------------------------------------------------
echo "-- C: real session generation (land art: grow) --"
call POST "${API_BASE}/api/auth/login" "$LJAR" "" \
  "{\"email\":\"${LEARNER_EMAIL}\",\"password\":\"${LEARNER_PASSWORD}\"}"
pass "learner login" "$HTTP_CODE" "200"
LCSRF=$(csrf_from_jar "$LJAR" fl_csrf)

# 2026-11-03: GET /api/learners/me must return learner_profile. app.js fills
# the Portfolio "My Story" card, the Guiding Star and the profile the client
# sends back to the companions from it; it was missing until this date, so
# My Story showed empty and every distillation restarted from scratch.
call GET "${API_BASE}/api/learners/me" "$LJAR"
pass "GET /api/learners/me" "$HTTP_CODE" "200"
ME_PROFILE_LEN=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
try:
    print(len((json.load(sys.stdin).get('learner_profile') or '').strip()))
except Exception:
    print(0)
" 2>/dev/null || echo 0)
ME_HAS_ONBOARD=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(1 if 'onboarding_complete' in d and 'newsletter_opt_out' in d and 'language' in d else 0)
except Exception:
    print(0)
" 2>/dev/null || echo 0)
if [ "$ME_HAS_ONBOARD" = "1" ]; then ok "/api/learners/me returns onboarding_complete, language and the newsletter flag (what a fresh login or private window needs)"
else bad "/api/learners/me is missing onboarding_complete / language / newsletter_opt_out (backend/routes/learners.py get_me; restart freqlearn after deploying)"; fi
if [ "${PROFILE_LEN:-0}" -gt 0 ]; then
  if [ "${ME_PROFILE_LEN:-0}" -gt 0 ]; then
    ok "/api/learners/me returns learner_profile (${ME_PROFILE_LEN} chars), the My Story card has data to show"
  else
    bad "/api/learners/me returns NO learner_profile although the database has ${PROFILE_LEN} chars, My Story will show empty and the profile cannot accumulate (backend/routes/learners.py get_me; restart freqlearn after deploying)"
  fi
else
  note "no stored profile to compare against /api/learners/me (Part B had none, or was skipped)"
fi

SESSION1_ID=""
call POST "${API_BASE}/api/generate/session" "$LJAR" "$LCSRF" \
  '{"art_slug":"grow","phase_slug":"water","language":"en"}' "$AI_GEN_MAX_TIME"
if [ "$HTTP_CODE" = "503" ]; then
  warn "POST /api/generate/session -> 503 (AI providers unavailable / no library match; upstream, not asserted)"
else
  pass "POST /api/generate/session (grow)" "$HTTP_CODE" "200"
fi
if [ "$HTTP_CODE" = "200" ]; then
  GEN_BODY="$HTTP_BODY"
  GEN_OK=$(echo "$GEN_BODY" | python3 -c "
import json, sys
d = json.load(sys.stdin)
req = ['warmup_prompt','explore_content','challenge_prompt','reflect_prompt','title','art_name','art_slug']
missing = [k for k in req if not (d.get(k) or '').strip()]
print('MISSING:' + ','.join(missing) if missing else 'OK')
")
  if [ "$GEN_OK" = "OK" ]; then ok "generated session has all required fields populated"; else bad "generated session missing fields: ${GEN_OK#MISSING:}"; fi
  SESSION1_ID=$(echo "$GEN_BODY" | json_get "session_id")
  if [ -n "$SESSION1_ID" ] && [ "$SESSION1_ID" != "None" ]; then
    ok "session_id=${SESSION1_ID} returned"
    if [ -n "$MYSQL_BIN" ]; then
      MODEL=$(db_query "SELECT model FROM sessions WHERE id=${SESSION1_ID};")
      if [ -z "$MODEL" ]; then
        warn "could not read sessions.model for id=${SESSION1_ID}"
      elif [ "$MODEL" = "library" ]; then
        warn "sessions.model='library', this session was NOT generated for the learner, so the portfolio did not apply (breaker tripped or ai_inline_reuse_enabled on)"
      else
        ok "sessions.model='${MODEL}', a real AI call answered with the portfolio-aware prompt"
      fi
      # 2026-11-03: live sessions have no dev_phase_id on purpose; the phase they
      # were generated for lives in generated_for_phase_id (admin shows it).
      GEN_PHASE=$(db_query "SELECT generated_for_phase_id FROM sessions WHERE id=${SESSION1_ID};")
      if [ -n "$GEN_PHASE" ] && [ "$GEN_PHASE" != "NULL" ]; then
        ok "sessions.generated_for_phase_id=${GEN_PHASE} recorded, the admin session list can show this session's phase"
      else
        warn "sessions.generated_for_phase_id is empty for id=${SESSION1_ID}, run scripts/2026-11-03-sessions-generated-for-phase.sql, and check the new generate.py is live (restart freqlearn). Not a failure."
      fi
    fi
  else
    bad "no session_id in response"; SESSION1_ID=""
  fi
  if [ -n "$BIOREGION" ]; then
    MENTIONED=$(echo "$GEN_BODY" | BIO="$BIOREGION" python3 -c "
import json, os, sys
d = json.load(sys.stdin)
text = ' '.join(str(d.get(k) or '') for k in ('warmup_prompt','explore_content','challenge_prompt','reflect_prompt')).lower()
bio = os.environ['BIO'].lower()
words = [w.strip(',.()') for w in bio.split() if len(w.strip(',.()')) >= 5]
print('yes' if (bio in text or any(w in text for w in words)) else 'no')
")
    note "generated text mentions the learner's bioregion ('${BIOREGION}'): ${MENTIONED} (informational only, models paraphrase, so this is never a FAIL)"
  fi
fi
echo ""

# ------------------------------------------------------------
# PART D, the real-response growth rule (writes real progress)
# ------------------------------------------------------------
echo "-- D: real-response growth rule --"
if [ "$VERIFY_WRITES" != "1" ]; then
  note "skipped. Re-run with VERIFY_WRITES=1 to complete two sessions for ${LEARNER_EMAIL} (adds real progress; see the SIDE EFFECTS note at the top of this script)."
elif [ -z "$MYSQL_BIN" ] || [ -z "$LEARNER_ID" ]; then
  warn "Part D needs the mysql/mariadb CLI and a learner id from Part B, skipping"
else
  skill_state() {   # skill_state SKILL_ID -> "level|evidence"
    local s
    s=$(db_query "SELECT CONCAT(current_level,'|',evidence_count) FROM learner_skill_progress WHERE learner_id=${LEARNER_ID} AND skill_id=$1;")
    echo "${s:-0|0}"
  }

  # --- D1: empty challenge + reflection -> not counted ---
  if [ -z "$SESSION1_ID" ]; then
    warn "no session from Part C to complete, skipping D1"
  else
    SID1=$(db_query "SELECT primary_skill_id FROM sessions WHERE id=${SESSION1_ID};")
    B1=$(skill_state "$SID1")
    call POST "${API_BASE}/api/sessions/${SESSION1_ID}/complete" "$LJAR" "$LCSRF" \
      '{"duration_seconds":60,"xp_earned":0,"challenge_response":"","reflect_response":"","assess_score":80,"phase_reached":5}'
    pass "complete session ${SESSION1_ID} with empty challenge + reflection" "$HTTP_CODE" "200"
    FLAG=$(echo "$HTTP_BODY" | json_get "counted_toward_growth")
    if [ "$FLAG" = "False" ]; then ok "response says counted_toward_growth=false"
    elif [ -z "$FLAG" ]; then bad "response has no counted_toward_growth field, is the new sessions.py running? (restart freqlearn)"
    else bad "counted_toward_growth=${FLAG} for an empty session (expected False)"; fi
    A1=$(skill_state "$SID1")
    if [ "$A1" = "$B1" ]; then ok "primary skill ${SID1} unchanged (level|evidence ${B1})"; else bad "primary skill ${SID1} changed ${B1} -> ${A1} on an uncounted session"; fi
    STATUS1=$(db_query "SELECT status FROM sessions WHERE id=${SESSION1_ID};")
    if [ "$STATUS1" = "completed" ]; then ok "uncounted session is still saved as completed"; else bad "session status is '${STATUS1}' (expected completed)"; fi
  fi

  # --- D2: a real sentence -> counted ---
  call POST "${API_BASE}/api/generate/session" "$LJAR" "$LCSRF" \
    '{"art_slug":"grow","phase_slug":"water","language":"en"}' "$AI_GEN_MAX_TIME"
  if [ "$HTTP_CODE" != "200" ]; then
    warn "second generation returned HTTP ${HTTP_CODE}, skipping D2"
  else
    SESSION2_ID=$(echo "$HTTP_BODY" | json_get "session_id")
    SID2=$(db_query "SELECT primary_skill_id FROM sessions WHERE id=${SESSION2_ID};")
    B2=$(skill_state "$SID2")
    call POST "${API_BASE}/api/sessions/${SESSION2_ID}/complete" "$LJAR" "$LCSRF" \
      '{"duration_seconds":60,"xp_earned":0,"challenge_response":"","reflect_response":"Automated verification: this sentence stands in for a real reflection.","assess_score":80,"phase_reached":5}'
    pass "complete session ${SESSION2_ID} with a real reflection" "$HTTP_CODE" "200"
    FLAG=$(echo "$HTTP_BODY" | json_get "counted_toward_growth")
    if [ "$FLAG" = "True" ]; then ok "response says counted_toward_growth=true"; else bad "counted_toward_growth='${FLAG}' for a real reflection (expected True)"; fi
    A2=$(skill_state "$SID2")
    BL=${B2%%|*}; BE=${B2##*|}; AL=${A2%%|*}; AE=${A2##*|}
    if [ "$AE" -eq $((BE+1)) ] && [ "$AL" -eq "$BL" ]; then
      ok "primary skill ${SID2}: evidence ${BE} -> ${AE}"
    elif [ "$AL" -eq $((BL+1)) ] && [ "$AE" -eq 0 ]; then
      ok "primary skill ${SID2}: levelled up ${BL} -> ${AL} (evidence resets to 0)"
    else
      bad "primary skill ${SID2} went ${B2} -> ${A2}; expected evidence +1 or a level-up"
    fi
  fi
fi
echo ""

# ------------------------------------------------------------
# PART E, the reflect-screen hint is actually being served
# ------------------------------------------------------------
echo "-- E: frontend assets --"
check_asset() {   # check_asset LABEL URL MIN_COUNT [PATTERN]   (PATTERN defaults to session.growth_hint)
  local body count pat="${4:-session.growth_hint}"
  body=$(curl -s --max-time 20 "$2" || true)
  count=$({ echo "$body" | grep -o -F "$pat" | wc -l | tr -d ' '; } || true)
  if [ "${count:-0}" -ge "$3" ]; then ok "$1 contains $pat (x${count})"
  else bad "$1 does not contain $pat (found ${count:-0}, need >= $3). Did bump_asset_versions.sh run, and is the file deployed?"; fi
}
check_absent() {   # check_absent LABEL URL PATTERN : the served file must NOT contain PATTERN
  local body count
  body=$(curl -s --max-time 20 "$2" || true)
  count=$({ echo "$body" | grep -o -F "$3" | wc -l | tr -d ' '; } || true)
  if [ "${count:-0}" -eq 0 ]; then ok "$1 no longer contains $3"
  else bad "$1 still contains $3 (x${count}), the old XP/streak UI may still be deployed"; fi
}
check_asset "app.js"       "${API_BASE}/app.js"       2
check_asset "lang/en.json" "${API_BASE}/lang/en.json" 1
check_asset "lang/fr.json" "${API_BASE}/lang/fr.json" 1
check_asset "app.js"       "${API_BASE}/app.js"       1 "computeStageProgress"
check_asset "lang/en.json" "${API_BASE}/lang/en.json" 1 "stage.next"
check_absent "lang/en.json" "${API_BASE}/lang/en.json" "stat.lifetime_xp"
check_asset "app.js"       "${API_BASE}/app.js"       1 "initBioregion(true)"
check_asset "app.js"       "${API_BASE}/app.js"       2 "_applyLearnerMe"
check_asset "app.js"       "${API_BASE}/app.js"       1 "_bioClickIsNear"
check_asset "lang/en.json" "${API_BASE}/lang/en.json" 1 "bio.you_here"
check_asset "lang/vi.json" "${API_BASE}/lang/vi.json" 1 "bio.refresh_failed"
note "to see the hint itself: hard-refresh the app (Ctrl+Shift+R), open a session and go to the reflect phase"
echo ""

# ------------------------------------------------------------
# PART F, journey log (Phase 2). Read-only.
# ------------------------------------------------------------
echo "-- F: journey log --"
if [ -z "$MYSQL_BIN" ]; then
  warn "mysql/mariadb CLI not found, skipping the Part F database checks"
else
  F_TABLES=$(db_query "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name IN ('journey_entries','learner_profile_versions')")
  if [ "$F_TABLES" = "2" ]; then ok "journey_entries and learner_profile_versions exist"
  else bad "journey tables missing (found ${F_TABLES:-0} of 2). Run: mysql ${DB_NAME} < scripts/2026-11-06-journey-log.sql"; fi
  if [ "$F_TABLES" = "2" ] && [ -n "$LEARNER_ID" ]; then
    F_VERS=$(db_query "SELECT COUNT(*) FROM learner_profile_versions WHERE learner_id = ${LEARNER_ID}")
    note "profile versions recorded for learner ${LEARNER_ID}: ${F_VERS:-0} (grows when My Story changes; 0 is normal right after the migration)"
  fi
fi
check_asset "app.js" "${API_BASE}/app.js" 1 "source:           'session'"

# F (patch C, 2026-11-07): the learner's own journey and profile-history APIs,
# the Journey tab strings, and (VERIFY_WRITES=1) the entry Part D just created.
call GET "${API_BASE}/api/learners/me/journey?limit=5" "$LJAR"
pass "GET /api/learners/me/journey" "$HTTP_CODE" "200"
if [ "$HTTP_CODE" = "200" ]; then
  if echo "$HTTP_BODY" | python3 -c "import json,sys; assert isinstance(json.load(sys.stdin), list)" 2>/dev/null; then ok "journey response is a list"; else bad "journey response is not a JSON list"; fi
fi
call GET "${API_BASE}/api/learners/me/profile-history?limit=5" "$LJAR"
pass "GET /api/learners/me/profile-history" "$HTTP_CODE" "200"
check_asset "app.js"  "${API_BASE}/app.js"           1 "journey.first_in_art"
check_asset "en.json" "${API_BASE}/lang/en.json"     1 "portfolio.tab_journey"
check_asset "fr.json" "${API_BASE}/lang/fr.json"     1 "portfolio.tab_journey"
# Phase 3 (2026-11-08): the Story and Skills tabs, "then and now", Weekly Story inline in the Journey.
check_asset "app.js"  "${API_BASE}/app.js"           1 "loadProfileHistory"
check_asset "en.json" "${API_BASE}/lang/en.json"     1 "portfolio.tab_story"
check_asset "fr.json" "${API_BASE}/lang/fr.json"     1 "portfolio.then_now"
if [ "$VERIFY_WRITES" = "1" ] && [ -n "${SESSION2_ID:-}" ]; then
  F_ROW=$(db_query "SELECT COUNT(*) FROM journey_entries WHERE learner_id=${LEARNER_ID} AND session_id=${SESSION2_ID} AND kind='session'")
  if [ "$F_ROW" = "1" ]; then ok "completing session ${SESSION2_ID} wrote one journey 'session' entry"; else bad "journey entries for session ${SESSION2_ID}: ${F_ROW:-none} (expected 1; is the new sessions.py running?)"; fi
  call GET "${API_BASE}/api/learners/me/journey?limit=20" "$LJAR"
  if echo "$HTTP_BODY" | python3 -c "
import json,sys
rows=json.load(sys.stdin)
sys.exit(0 if any(r.get('session_id')==int(sys.argv[1]) and r.get('kind')=='session' for r in rows) else 1)" "${SESSION2_ID}" 2>/dev/null; then
    ok "the API returns that entry to its learner"
  else bad "session ${SESSION2_ID}'s entry is not in GET /api/learners/me/journey"; fi
else
  note "write check skipped (needs VERIFY_WRITES=1 and the session Part D completed)"
fi
echo ""

call POST "${API_BASE}/api/auth/logout" "$LJAR" "$LCSRF" || true
call POST "${API_BASE}/api/admin/logout" "$AJAR" "$(csrf_from_jar "$AJAR" fl_admin_csrf)" || true

if [ "$fail" -ne 0 ]; then
  echo "PORTFOLIO VERIFY FAILED ($fail failure(s))"
  exit 1
fi
echo "All portfolio checks healthy (WARN/NOTE lines are for you to read, not failures)."
