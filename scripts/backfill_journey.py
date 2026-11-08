#!/usr/bin/env python3
# ============================================================
# LMBoK, scripts/backfill_journey.py   (Phase 2 patch D, 2026-11-08)
# MANUAL server administration, never imported by the running app.
#
# Builds the journey log for history that predates it:
#   * a 'session' entry for every completed session that has none
#   * 'first_in_art' and 'all_families' milestones, from session order
#   * 'stage_change' milestones, from the radar_snapshots sequence
#   * one learner_profile_versions row (source 'backfill') when a learner's
#     latest version is missing or differs from the stored profile
# Level-ups cannot be reconstructed and are not written.
#
# Safe to re-run: it only adds what is missing (sessions by session_id,
# first_in_art by Art, all_families once, stage_change by stage, the profile
# row only when it differs). Entries carry the DATE of what they describe
# (session completed_at / snapshot created_at), not today's date.
#
# DEFAULT IS A DRY RUN: nothing is written without --apply. Back up first.
#
#   cd /var/www/freqlearn/backend
#   venv/bin/python ../scripts/backfill_journey.py                  # dry run
#   venv/bin/python ../scripts/backfill_journey.py --apply
#   venv/bin/python ../scripts/backfill_journey.py --learner 2      # one learner
#   venv/bin/python ../scripts/backfill_journey.py --rule-from 2026-11-01
#
# --rule-from DATE (default 2026-11-01): the "counted toward growth" rule
# (a real written response) began that day. Sessions completed BEFORE it were
# credited whatever the learner wrote, so they are treated as counted;
# from that date on, counted is derived from the stored responses with the
# same function complete_session uses.
#
# Prints counts only, never session text or profile text.
# ============================================================

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "routes"))
os.chdir(BACKEND)                       # so load_dotenv() finds backend/.env

from sqlalchemy import select, text                           # noqa: E402
from db import AsyncSessionLocal                              # noqa: E402
from models import (Arts, JourneyEntry, Learner, LearnerProfileVersion,   # noqa: E402
                    RadarSnapshot, Session)
from journey import make_excerpt, TITLE_MAX, FAMILIES         # noqa: E402
from routes.sessions import has_real_response                 # noqa: E402
from utils import compute_avatar_stage                        # noqa: E402


def counted_for(s, rule_from: datetime) -> bool:
    if s.completed_at is not None and s.completed_at.replace(tzinfo=None) < rule_from:
        return True
    return has_real_response(s.challenge_response, s.reflect_response)


async def backfill_learner(db, learner, arts_group, rule_from, counts):
    lid = learner.id
    existing = (await db.execute(
        select(JourneyEntry.kind, JourneyEntry.milestone, JourneyEntry.session_id,
               JourneyEntry.art_id, JourneyEntry.payload)
        .where(JourneyEntry.learner_id == lid))).all()
    have_sessions = {r.session_id for r in existing if r.kind == "session" and r.session_id}
    seen_arts     = {r.art_id for r in existing if r.milestone == "first_in_art" and r.art_id}
    have_families = any(r.milestone == "all_families" for r in existing)
    have_stages   = {(r.payload or {}).get("to") for r in existing if r.milestone == "stage_change"}

    # ---- sessions and the milestones that follow from their order ----
    sessions = (await db.execute(
        select(Session).where(Session.learner_id == lid, Session.status == "completed",
                              Session.completed_at.is_not(None))
        .order_by(Session.completed_at, Session.id))).scalars().all()
    art_names = {a_id: nm for a_id, nm in (await db.execute(select(Arts.id, Arts.name))).all()}

    for s in sessions:
        when = s.completed_at.replace(tzinfo=None)
        counted = counted_for(s, rule_from)
        if s.id not in have_sessions:
            title = " ".join((s.title or "").split()) or art_names.get(s.art_id, "Session")
            db.add(JourneyEntry(
                learner_id=lid, kind="session", session_id=s.id, art_id=s.art_id,
                skill_id=s.primary_skill_id, title=title[:TITLE_MAX],
                excerpt=make_excerpt(s.reflect_response, s.challenge_response),
                payload={"counted": counted, "backfilled": True}, created_at=when))
            counts["sessions"] += 1
        if counted and s.art_id not in seen_arts:
            seen_arts.add(s.art_id)
            db.add(JourneyEntry(
                learner_id=lid, kind="milestone", milestone="first_in_art",
                session_id=s.id, art_id=s.art_id, skill_id=s.primary_skill_id,
                title=(art_names.get(s.art_id) or "First session in an Art")[:TITLE_MAX],
                payload={"backfilled": True}, created_at=when))
            counts["first_in_art"] += 1
            if not have_families and len({arts_group.get(a) for a in seen_arts}) >= FAMILIES:
                have_families = True
                db.add(JourneyEntry(
                    learner_id=lid, kind="milestone", milestone="all_families",
                    session_id=s.id, art_id=s.art_id, title="All three families",
                    payload={"backfilled": True}, created_at=when))
                counts["all_families"] += 1

    # ---- stage changes, from the snapshot sequence ----
    snaps = (await db.execute(
        select(RadarSnapshot).where(RadarSnapshot.learner_id == lid)
        .order_by(RadarSnapshot.id))).scalars().all()
    prev = compute_avatar_stage({})
    for sn in snaps:
        cur = compute_avatar_stage(sn.art_scores or {})
        if cur["level"] > prev["level"] and cur["key"] not in have_stages:
            have_stages.add(cur["key"])
            db.add(JourneyEntry(
                learner_id=lid, kind="milestone", milestone="stage_change",
                title=cur["label"][:TITLE_MAX],
                payload={"from": prev["key"], "to": cur["key"], "backfilled": True},
                created_at=sn.created_at))
            counts["stage_change"] += 1
        prev = cur

    # ---- profile version ----
    profile = (learner.learner_profile or "").strip()
    if profile:
        latest = (await db.execute(
            select(LearnerProfileVersion.profile).where(LearnerProfileVersion.learner_id == lid)
            .order_by(LearnerProfileVersion.id.desc()).limit(1))).scalar_one_or_none()
        if latest is None or latest.strip() != profile:
            db.add(LearnerProfileVersion(learner_id=lid, profile=learner.learner_profile, source="backfill"))
            counts["profile_versions"] += 1


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--learner", type=int, help="only this learner id")
    ap.add_argument("--rule-from", default="2026-11-01", help="YYYY-MM-DD, see header")
    a = ap.parse_args()
    rule_from = datetime.strptime(a.rule_from, "%Y-%m-%d")

    async with AsyncSessionLocal() as db:
        now, utc = (await db.execute(text("SELECT NOW(), UTC_TIMESTAMP()"))).one()
        if abs((now - utc).total_seconds()) > 60:
            print(f"WARN  database time zone is not UTC (NOW()={now}, UTC={utc}). Journey rows written "
                  f"live use NOW(); backfilled rows use the stored session/snapshot times. "
                  f"Their order may be off by the difference.")
        arts_group = {i: g for i, g in (await db.execute(select(Arts.id, Arts.group_id))).all()}
        q = select(Learner).order_by(Learner.id)
        if a.learner:
            q = q.where(Learner.id == a.learner)
        learners = (await db.execute(q)).scalars().all()
        total = dict(sessions=0, first_in_art=0, all_families=0, stage_change=0, profile_versions=0)
        for lr in learners:
            counts = dict.fromkeys(total, 0)
            try:
                async with db.begin_nested():
                    await backfill_learner(db, lr, arts_group, rule_from, counts)
            except Exception as e:                      # one bad learner must not stop the rest
                print(f"FAIL  learner {lr.id}: {type(e).__name__}: {e}")
                continue
            if any(counts.values()):
                print(f"learner {lr.id}: " + ", ".join(f"{k}={v}" for k, v in counts.items() if v))
            for k in total:
                total[k] += counts[k]
        print("TOTAL " + ", ".join(f"{k}={v}" for k, v in total.items()))
        if a.apply:
            await db.commit()
            print("APPLIED. Re-running adds nothing more.")
        else:
            await db.rollback()
            print("DRY RUN, nothing written. Re-run with --apply (after a backup).")


if __name__ == "__main__":
    asyncio.run(main())
