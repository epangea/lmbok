#!/usr/bin/env python3
# ============================================================
# LMBoK — seed_exercises.py
#
# Generates ONE exercise per (Art x Development phase) with the platform's
# own AI chain AND stores it in the `sessions` table as a library row, in the
# same pass. It also writes every exercise to a plain-text file in the
# review layout (ART header / EXERCISE TITLE / WARMUP / EXPLORE / CHALLENGE /
# REFLECT / ASSESS + Info).
#
# It reuses backend/routes/seed_sessions.py for everything that already
# exists there (provider chain + fallback, settings, session_config content,
# prompt skeleton, language-free storage, shuffle of options), so there is
# no second copy of the AI plumbing to drift. What this script adds on top:
#   - ART + PHASE ONLY in the prompt (art lens + phase guide from
#     session_config), exactly like seed_sessions.py. No skill or skill-domain
#     line: skills are a backwards-compatible way into the arts and must not
#     steer seeded content (Charbel, 2026-10-22). sessions.primary_skill_id is
#     NOT NULL, so each row still carries a skill id -- only as a tag, picked
#     the way seed_sessions.py picks it (the art's arts_skills primary skill;
#     lowest skill id here, so it is deterministic)
#   - validation of the AI's JSON (4 distinct options, index in range ...)
#     with a retry before counting a combo as failed
#   - the review-text export
#
# Rows are stored exactly like seed_sessions.py stores them (learner_id=1,
# model NULL, status 'scheduled', language 'en'), so the library failover,
# the admin coverage grid and seed_sessions.py's own resume logic all see
# them as ordinary seed rows.
#
# Run (as the freqlearn user, from /var/www/freqlearn/backend):
#   venv/bin/python ../scripts/seed_exercises.py --arts move --phases light
#   venv/bin/python ../scripts/seed_exercises.py --arts move            # all 13 phases of Move
#   venv/bin/python ../scripts/seed_exercises.py                        # all 15 arts x 13 phases
# Useful flags: --dry-run (plan + first prompt, no AI, no DB writes),
#   --no-insert (generate + write the text file only), --force (add another
#   exercise even if the combo already has a seed row), --delay 20,
#   --after-id N (a combo counts as filled only by seed rows with id > N: adds
#   art-only rows beside older ones and, unlike --force, is safe to re-run
#   after an interruption).
# ============================================================

import sys
import json
import asyncio
import argparse
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ROUTES = ROOT / "backend" / "routes"
if not (ROUTES / "seed_sessions.py").exists():
    sys.exit(f"seed_sessions.py not found at {ROUTES} -- run this from a full repo "
             f"checkout (scripts/ must sit next to backend/).")
sys.path.insert(0, str(ROUTES))

import aiomysql                       # noqa: E402
import seed_sessions as ss            # noqa: E402  (loads backend/.env itself)

LANG = "en"
TEXT_KEYS = ("title", "warmup", "explore", "challenge", "reflect", "assess_question")

# Same strings the learner UI shows (frontend/lang/en.json); literals are only
# a fallback if that file can't be read.
_UI_FALLBACK = {
    "session.art_of_x_reflection": "The art of {art} · {group} · reflection",
    "session.sit_with_this": "Take a moment to sit with this. The next phase will invite you to put it into practice.",
    "session.placeholder_no_wrong_answer": "Write freely — there is no wrong answer here...",
    "session.explainer": "What's this question about?",
}


def load_ui_strings() -> dict:
    try:
        d = json.loads((ROOT / "frontend" / "lang" / "en.json").read_text(encoding="utf-8"))
    except Exception:
        d = {}
    return {k: d.get(k, v) for k, v in _UI_FALLBACK.items()}


class BadExercise(ValueError):
    pass


def validate(data) -> dict:
    """Reject anything the player UI or the library couldn't use."""
    if not isinstance(data, dict):
        raise BadExercise("AI reply was not a JSON object")
    for k in TEXT_KEYS:
        v = data.get(k)
        if not isinstance(v, str) or not v.strip():
            raise BadExercise(f"missing or empty '{k}'")
    if len(data["title"]) > 160:
        raise BadExercise("title longer than the 160-char column")
    opts = data.get("assess_options")
    if (not isinstance(opts, list) or len(opts) != 4
            or any(not isinstance(o, str) or not o.strip() for o in opts)):
        raise BadExercise("assess_options must be exactly 4 non-empty strings")
    if len({o.strip().lower() for o in opts}) != 4:
        raise BadExercise("assess_options contain duplicates")
    try:
        c = int(data.get("assess_correct"))
    except (TypeError, ValueError):
        raise BadExercise("assess_correct is not an integer")
    if not 0 <= c <= 3:
        raise BadExercise("assess_correct out of range 0-3")
    data["assess_correct"] = c
    return data


def format_block(art: dict, phase_name: str, ex: dict, ui: dict, footer: str) -> str:
    """The review layout. `ex` carries final (stored) option order."""
    slug = art["slug"].upper()
    tag = ui["session.art_of_x_reflection"].format(art=art["name"], group=art["group"])
    lines = [slug]
    if art.get("tagline"):
        lines.append(art["tagline"])
    if art.get("description"):
        lines.append(art["description"])
    lines += [
        "",
        f"{slug}/{phase_name.upper()} DEV PHASE",
        "",
        f"EXERCISE TITLE: {ex['title']} - {tag}",
        "",
        f"WARMUP: {ex['warmup']}",
        "",
        f"EXPLORE: {ex['explore']}",
        f"\"{ui['session.sit_with_this']}\"",
        "",
        f"CHALLENGE: {ex['challenge']}",
        f"\"{ui['session.placeholder_no_wrong_answer']}\"",
        "",
        f"REFLECT: {ex['reflect']}",
        f"\"{ui['session.placeholder_no_wrong_answer']}\"",
        "",
        f"ASSESS: {ex['question']}",
        "",
    ]
    lines += [f"  {o}" for o in ex["options"]]
    lines += ["", f"  Info: {ui['session.explainer']}", f"  {ex['explore']}",
              "", footer, "", "=" * 72, ""]
    return "\n".join(lines)


async def fetch_catalog(conn, after_id=0):
    async with conn.cursor() as cur:
        await cur.execute("""
            SELECT a.id, a.slug, a.name, a.tagline, a.description, g.name
            FROM arts a JOIN arts_group g ON g.id = a.group_id
        """)
        arts = {r[1]: dict(id=r[0], slug=r[1], name=r[2], tagline=r[3],
                           description=r[4], group=r[5]) for r in await cur.fetchall()}
        # Tag only (sessions.primary_skill_id is NOT NULL); not used in the prompt.
        await cur.execute("SELECT art_id, MIN(skill_id) FROM arts_skills "
                          "WHERE is_primary = 1 GROUP BY art_id")
        tags = {r[0]: r[1] for r in await cur.fetchall()}
        await cur.execute("SELECT id, slug FROM dev_phases")
        phase_ids = {r[1]: r[0] for r in await cur.fetchall()}
        await cur.execute("""
            SELECT art_id, dev_phase_id, COUNT(*) FROM sessions
            WHERE dev_phase_id IS NOT NULL AND warmup_prompt IS NOT NULL
              AND learner_id = 1 AND model IS NULL AND COALESCE(language,'en') = %s
              AND id > %s
            GROUP BY art_id, dev_phase_id
        """, (LANG, after_id))
        existing = {(r[0], r[1]): r[2] for r in await cur.fetchall()}
    return arts, tags, phase_ids, existing


async def read_back(conn, sid: int) -> dict:
    """Format from what is actually stored (options are shuffled on insert)."""
    async with conn.cursor() as cur:
        await cur.execute("""SELECT title, warmup_prompt, explore_content, challenge_prompt,
                                    reflect_prompt, assess_question FROM sessions WHERE id=%s""", (sid,))
        r = await cur.fetchone()
    aq = json.loads(r[5]) if isinstance(r[5], (str, bytes)) else r[5]
    return dict(title=r[0], warmup=r[1], explore=r[2], challenge=r[3], reflect=r[4],
                question=aq["question"], options=aq["options"], correct=aq["correct_index"])


async def main(args) -> int:
    ui = load_ui_strings()
    conn = await aiomysql.connect(**ss.DB)
    await ss._load_settings(conn)
    await ss._load_session_config(conn)
    cfg = ss._session_config
    arts_db, tags_db, phase_ids, existing = await fetch_catalog(conn, args.after_id)

    # Same rebuild seed_sessions.main() does: live, admin-editable content.
    disclaimer = cfg.get("phase_guidance_disclaimer",
                         "This is a starting point, not a rule about this specific learner.")
    phases = [(s, n, a, f"{cfg.get(f'phase_guide:{s}', fb)} {disclaimer}") for s, n, a, fb in ss.PHASES]
    lenses = {s: cfg.get(f"art_lens:{s}", detail) for s, _n, _t, detail in ss.ARTS}

    want_arts = [x for x in args.arts.split(",") if x] if args.arts else None
    want_phases = [x for x in args.phases.split(",") if x] if args.phases else None
    for label, wanted, known in (("art", want_arts, [a[0] for a in ss.ARTS]),
                                 ("phase", want_phases, [p[0] for p in phases])):
        bad = [w for w in (wanted or []) if w not in known]
        if bad:
            print(f"Unknown {label} slug(s): {', '.join(bad)}  (valid: {', '.join(known)})")
            conn.close()
            return 1
    target_arts = [a for a in ss.ARTS if not want_arts or a[0] in want_arts]
    target_phases = [p for p in phases if not want_phases or p[0] in want_phases]

    work, skipped = [], 0
    for slug, _n, _t, _d in target_arts:
        art = arts_db.get(slug)
        if not art:
            print(f"  ⚠ art not in DB: {slug}")
            continue
        tag = tags_db.get(art["id"])
        if not tag:
            print(f"  ⚠ {slug}: no primary skill in arts_skills to use as the row's tag -- skipped")
            continue
        for p in target_phases:
            pid = phase_ids.get(p[0])
            if not pid:
                print(f"  ⚠ phase not in DB: {p[0]}")
                continue
            have = existing.get((art["id"], pid), 0)
            if have >= 1 and not args.force:
                skipped += 1
                continue
            work.append((art, tag, p, pid, have + 1))

    print("=" * 64)
    print("LMBoK — exercise seeder (one per art x phase)")
    print(f"Combos to generate: {len(work)}   already filled, skipped: {skipped}")
    print(f"Provider: {ss._settings['ai_provider']}   insert into DB: {not args.no_insert}")
    if args.after_id:
        print(f"A combo counts as filled only if it has a seed row with id > {args.after_id}")
    print("=" * 64)
    if not work:
        print("Nothing to do. (Use --force to add another exercise to a filled combo.)")
        conn.close()
        return 0

    def build(art, phase, n, avoid=None):
        ctx = lenses.get(art["slug"], "")
        art_t = (art["slug"], art["name"], art["tagline"] or "", ctx)
        return art_t, ss.build_prompt(
            art["slug"], art["name"], art["tagline"] or "", ctx, phase[0], phase[1], phase[2],
            phase[3], n, cfg.get("platform_identity", ss._PLATFORM_IDENTITY_FALLBACK), avoid)

    if args.dry_run:
        for art, _tag, phase, _pid, n in work:
            print(f"  {art['slug']} x {phase[1]}")
        print("\n--- prompt for the first combo (no AI call, nothing written) ---\n")
        avoid = await ss.fetch_titles_to_avoid(conn, work[0][0]["id"], LANG)
        print(build(work[0][0], work[0][2], work[0][4], avoid)[1])
        conn.close()
        return 0

    if not args.no_insert and not args.yes:
        if input(f"Generate {len(work)} exercise(s) and insert them into sessions? (y/N): ").lower() != "y":
            print("Aborted.")
            conn.close()
            return 0

    if not args.no_insert and ss._settings["ai_provider"] == "library":
        print("ERROR: ai_provider is 'library' -- seeding needs a live AI provider.")
        conn.close()
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"seed_exercises_{datetime.now():%Y%m%d-%H%M%S}.txt"

    done = errors = fails_in_a_row = 0
    aborted = False
    for i, (art, tag, phase, pid, n) in enumerate(work):
        if aborted:
            break
        label = f"{art['slug']} x {phase[1]}"
        print(f"  {label} ...", end=" ", flush=True)
        art_t, _prompt = build(art, phase, n)
        avoid = await ss.fetch_titles_to_avoid(conn, art["id"], LANG)
        used = {t.strip().lower() for t in avoid["titles"]}
        try:
            data = None
            last_err = None
            for attempt in range(args.retries + 1):
                try:
                    data = validate(await ss.generate_one(art_t, phase, n, False, LANG, avoid))
                    if data["title"].strip().lower() in used:
                        raise BadExercise("title already used for this art")
                    break
                except (json.JSONDecodeError, BadExercise) as e:
                    last_err = e
                    print(f"[bad reply: {e}; retry {attempt + 1}/{args.retries}] ", end="", flush=True)
            if data is None:
                raise BadExercise(f"no valid exercise after {args.retries + 1} attempts ({last_err})")

            if args.no_insert:
                ex = dict(title=data["title"], warmup=data["warmup"], explore=data["explore"],
                          challenge=data["challenge"], reflect=data["reflect"],
                          question=data["assess_question"], options=list(data["assess_options"]),
                          correct=data["assess_correct"])
                footer = f"[not inserted · correct answer: {'ABCD'[ex['correct']]}]"
                sid = None
            else:
                sid = await ss.store_session(conn, art["id"], pid, tag, data, LANG)
                ex = await read_back(conn, sid)
                footer = (f"[sessions.id={sid} · "
                          f"correct answer: {'ABCD'[ex['correct']]}]")
            with open(out_file, "a", encoding="utf-8") as f:
                f.write(format_block(art, phase[1], ex, ui, footer))
            print(f"✓ {'id=' + str(sid) + ' ' if sid else ''}{ex['title']}")
            done += 1
            fails_in_a_row = 0
            if i < len(work) - 1:
                await asyncio.sleep(args.delay)
        except Exception as e:  # provider chain exhausted, DB error, or no valid reply
            errors += 1
            fails_in_a_row += 1
            print(f"✗ {str(e)[:300]}")
            if fails_in_a_row >= args.max_consecutive_failures:
                print(f"\nSTOPPING: {fails_in_a_row} failures in a row -- providers look unavailable. "
                      f"Re-run later; stored rows are kept and filled combos are skipped.")
                aborted = True
            else:
                wait = min(30 * 2 ** (fails_in_a_row - 1), 300)
                print(f"    backing off {wait}s ({fails_in_a_row}/{args.max_consecutive_failures})")
                await asyncio.sleep(wait)

    conn.close()
    print("\n" + "=" * 64)
    print(f"Done: {done} generated, {errors} errors")
    if done:
        print(f"Review text: {out_file}")
    print("=" * 64)
    return 1 if aborted or done == 0 else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generate + seed one exercise per art x dev phase")
    ap.add_argument("--arts", default="", help="Comma-separated art slugs (default: all 15)")
    ap.add_argument("--phases", default="", help="Comma-separated phase slugs (default: all 13)")
    ap.add_argument("--no-insert", action="store_true", help="Generate and write the text file only; no DB writes")
    ap.add_argument("--force", action="store_true", help="Add an exercise even if the combo already has a seed row")
    ap.add_argument("--after-id", type=int, default=0,
                    help="Count only seed rows with id greater than N when deciding whether a combo is "
                         "filled: adds art-only rows beside older ones, and unlike --force it is safe to "
                         "re-run after an interruption (finished combos are skipped)")
    ap.add_argument("--dry-run", action="store_true", help="Show the plan and the first prompt; no AI call, no DB writes")
    ap.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    ap.add_argument("--delay", type=float, default=20.0, help="Seconds between AI calls (default 20; free-tier Groq is rate-limited)")
    ap.add_argument("--retries", type=int, default=2, help="Re-asks per combo when the reply is malformed (default 2)")
    ap.add_argument("--max-consecutive-failures", type=int, default=5)
    ap.add_argument("--out-dir", default="seed_exercises_out", help="Where the review text file is written (default ./seed_exercises_out)")
    sys.exit(asyncio.run(main(ap.parse_args())) or 0)
