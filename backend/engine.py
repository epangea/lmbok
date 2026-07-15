# ============================================================
# FreqLearn Backend — engine.py
# Recommendation engine — matches schema v2 (15 arts)
# Weights: ZPD 35% · Interest 25% · Radar balance 20%
#          Spaced repetition 12% · Energy/context 8%
# ============================================================

import random
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import (
    Learner, LearnerSkillProgress, Skill,
    Arts, ArtsGroup, ArtsSkills, LearnerArtProgress,
    Session, LearnerStreak
)


class RecommendationEngine:

    async def recommend_next(self, learner_id: int, db: AsyncSession) -> dict:
        all_skills = await self._get_all_skills(db)
        progress   = await self._get_all_progress(learner_id, db)
        streak     = await self._get_streak(learner_id, db)
        radar      = await self.compute_radar(learner_id, db)

        # Build a set of art_ids practiced in the last 24h so _score_skill can
        # apply a cooldown multiplier and steer the engine toward variety.
        recent_art_ids = await self._get_recent_art_ids(learner_id, db)

        # Also build skill_id → art_id map for the cooldown lookup.
        mappings_q = await db.execute(
            select(ArtsSkills).where(ArtsSkills.is_primary == True)
        )
        skill_art_map = {m.skill_id: m.art_id for m in mappings_q.scalars().all()}

        scored = []
        for skill in all_skills:
            prog = progress.get(skill.id)
            art_id = skill_art_map.get(skill.id)
            score, signals = self._score_skill(skill, prog, radar, streak, art_id, recent_art_ids)
            scored.append((score, skill, signals))

        scored.sort(key=lambda x: x[0], reverse=True)

        if not scored:
            # No active skills in DB — should never happen but guard anyway
            return {
                "skill_id": None, "skill_name": "Curiosity", "subcategory": "Meta-Learning",
                "art_slug": "notice", "art_id": None, "art_name": "Noticing",
                "current_level": 0, "target_level": 1, "title": "Discover: Curiosity",
                "duration_min": 15,
                "reasoning": "Start here — curiosity is the root of all learning.",
                "signals": {}, "score": 0.0,
            }

        # Tiebreaker: when many skills score identically (common for new learners
        # with 76 unstarted skills), stable sort always picks the same one.
        # Randomly select from all candidates within 5% of the top score.
        top = scored[0][0]
        candidates = [(s, sk, sg) for s, sk, sg in scored if s >= top * 0.95 or top < 0.1]
        best_score, best_skill, best_signals = random.choice(candidates)

        prog = progress.get(best_skill.id)
        current_level = prog.current_level if prog else 0

        # Find the primary art for this skill
        art_q = await db.execute(
            select(ArtsSkills)
            .where(ArtsSkills.skill_id == best_skill.id, ArtsSkills.is_primary == True)
            .limit(1)
        )
        arts_skill = art_q.scalar_one_or_none()

        # Fall back to any mapping if no primary flagged
        if not arts_skill:
            art_q = await db.execute(
                select(ArtsSkills).where(ArtsSkills.skill_id == best_skill.id).limit(1)
            )
            arts_skill = art_q.scalar_one_or_none()

        # If still no mapping, this skill is an orphan — walk through scored in
        # order and pick the highest-scoring skill that does have a mapping.
        # This is the core fix: prevents unmapped skills from producing the
        # "Art of Growing" fallback on every fresh page load.
        if not arts_skill:
            for _, fallback_skill, fallback_signals in scored:
                if fallback_skill.id == best_skill.id:
                    continue
                art_q = await db.execute(
                    select(ArtsSkills).where(ArtsSkills.skill_id == fallback_skill.id).limit(1)
                )
                arts_skill = art_q.scalar_one_or_none()
                if arts_skill:
                    best_skill    = fallback_skill
                    best_signals  = fallback_signals
                    prog          = progress.get(best_skill.id)
                    current_level = prog.current_level if prog else 0
                    break

        art_slug = 'grow'
        art_id   = None
        art_name = 'Growing'
        if arts_skill:
            art_obj_q = await db.execute(select(Arts).where(Arts.id == arts_skill.art_id))
            art_obj   = art_obj_q.scalar_one_or_none()
            if art_obj:
                art_slug = art_obj.slug
                art_id   = art_obj.id
                art_name = art_obj.name

        return {
            "skill_id":      best_skill.id,
            "skill_name":    best_skill.name,
            "subcategory":   best_skill.subcategory,
            "art_slug":      art_slug,
            "art_id":        art_id,
            "art_name":      art_name,
            "current_level": current_level,
            "target_level":  min(current_level + 1, 3),
            "title":         self._make_title(best_skill, current_level),
            "duration_min":  self._estimate_duration(current_level, streak),
            "reasoning":     self._make_reasoning(best_signals, best_skill),
            "signals":       best_signals,
            "score":         round(best_score, 3),
        }

    async def compute_radar(self, learner_id: int, db: AsyncSession) -> dict:
        """
        Returns scores at two levels:
        - art_scores: {art_slug: 0.0-1.0} for all 15 arts
        - group_scores: {group_slug: 0.0-1.0} for Being/Becoming/Connecting

        FIX: previously used positional skill slicing (skills[i*n:(i+1)*n])
        which produced garbage scores unrelated to actual art-skill mappings.
        Now queries arts_skills directly — 191 seeded rows.
        """
        groups_q = await db.execute(
            select(ArtsGroup).order_by(ArtsGroup.sort_order)
        )
        groups = groups_q.scalars().all()

        arts_q = await db.execute(
            select(Arts).order_by(Arts.sort_order)
        )
        arts = arts_q.scalars().all()

        # Load all arts_skills mappings in one query
        mappings_q = await db.execute(select(ArtsSkills))
        mappings = mappings_q.scalars().all()

        # Build art_id → [skill_ids] index
        art_skill_ids: dict[int, list[int]] = {}
        for m in mappings:
            art_skill_ids.setdefault(m.art_id, []).append(m.skill_id)

        # Load learner's skill progress
        progress_q = await db.execute(
            select(LearnerSkillProgress)
            .where(LearnerSkillProgress.learner_id == learner_id)
        )
        progress_map = {p.skill_id: p for p in progress_q.scalars().all()}

        # Compute per-art score based on actual mapped skills.
        # FIX: previously summed only current_level (integers), keeping the
        # radar at 0 until a full level-up occurred (3 sessions + score ≥ 70).
        # Now adds fractional credit from evidence_count so the radar shape
        # responds after every session, not only after level-ups.
        art_scores = {}
        for art in arts:
            skill_ids = art_skill_ids.get(art.id, [])
            if not skill_ids:
                art_scores[art.slug] = 0.0
                continue
            total_possible = len(skill_ids) * 3  # max level 3 per skill
            earned = 0.0
            for sid in skill_ids:
                if sid in progress_map:
                    p        = progress_map[sid]
                    level    = p.current_level  or 0
                    evidence = p.evidence_count or 0
                    earned  += level  # full levels already achieved
                    if level < 3:    # partial credit toward next level
                        earned += min(evidence / ((level + 1) * 3), 1.0)
            art_scores[art.slug] = round(min(earned / total_possible, 1.0), 3)

        # Blend in direct art-practice bonus (written by complete_session when a
        # Learning Domain skill is clicked). Capped at 20% of the final score so
        # skill-based learning remains the primary driver.
        art_prog_q = await db.execute(
            select(LearnerArtProgress).where(LearnerArtProgress.learner_id == learner_id)
        )
        art_prog_map = {p.art_id: float(p.score or 0) for p in art_prog_q.scalars().all()}

        for art in arts:
            direct = art_prog_map.get(art.id, 0.0)
            if direct > 0:
                skill_score = art_scores[art.slug]
                art_scores[art.slug] = round(min(skill_score + direct * 0.20, 1.0), 3)

        # Group scores = average of constituent art scores
        group_scores = {}
        for group in groups:
            group_arts = [a for a in arts if a.group_id == group.id]
            if group_arts:
                group_scores[group.slug] = round(
                    sum(art_scores.get(a.slug, 0.0) for a in group_arts) / len(group_arts), 3
                )
            else:
                group_scores[group.slug] = 0.0

        return {
            "art_scores":   art_scores,
            "group_scores": group_scores,
        }

    def _score_skill(self, skill, prog, radar, streak,
                     art_id=None, recent_art_ids=None) -> tuple[float, dict]:
        signals = {}

        # Daily recency penalty — if this specific skill was practiced today,
        # score it near zero so the engine is forced to recommend something different.
        now = datetime.now(timezone.utc)
        if prog and prog.last_practiced_at:
            last = prog.last_practiced_at
            if not last.tzinfo:
                last = last.replace(tzinfo=timezone.utc)
            if last.date() == now.date():
                signals["rested"] = False
                return 0.05, signals
        signals["rested"] = True

        # Art-level cooldown — if the learner completed sessions in this art
        # in the last 24h, apply a suppression multiplier so the engine steers
        # toward variety across arts rather than looping within one domain.
        # 0.35 is strong suppression but still beatable by very high ZPD/interest,
        # so a highly motivated learner can continue naturally; it just stops the
        # engine defaulting to the same art on autopilot.
        art_cooldown = 1.0
        if art_id and recent_art_ids and art_id in recent_art_ids:
            art_cooldown = 0.35
        signals["art_cooldown"] = round(art_cooldown, 2)

        # 1. ZPD (35%)
        current = prog.current_level if prog else 0
        if current == 0:
            zpd = 0.6
        elif current < 3:
            xp_pct = (prog.evidence_count / max(prog.evidence_count + 2, 1))
            zpd = 0.5 + (0.5 * xp_pct)
        else:
            zpd = 0.1
        signals["zpd"] = round(zpd, 3)

        # 2. Spaced repetition (12%)
        now = datetime.now(timezone.utc)
        if prog and prog.next_review_at:
            days_overdue = max(0, (now - prog.next_review_at.replace(tzinfo=timezone.utc)).days)
            sr = min(1.0, days_overdue / 7)
        elif prog and prog.last_practiced_at:
            days_since = (now - prog.last_practiced_at.replace(tzinfo=timezone.utc)).days
            sr = min(1.0, days_since / 14)
        else:
            sr = 0.3
        signals["spaced_repetition"] = round(sr, 3)

        # 3. Radar balance (20%) — favour lagging arts
        art_scores = radar.get("art_scores", {})
        mean      = sum(art_scores.values()) / max(len(art_scores), 1) if art_scores else 0.0
        min_score = min(art_scores.values()) if art_scores else 0.0
        balance   = max(0.0, mean - min_score)
        signals["radar_balance"] = round(balance, 3)

        # 4. Context / energy (8%)
        hour = now.hour
        if 7 <= hour <= 10:     context = 0.9
        elif 14 <= hour <= 16:  context = 0.6
        elif 19 <= hour <= 21:  context = 0.8
        else:                   context = 0.4
        signals["context"] = round(context, 3)

        # 5. Interest proxy (25%)
        evidence = prog.evidence_count if prog else 0
        interest = min(1.0, 0.4 + (evidence * 0.15))
        signals["interest"] = round(interest, 3)

        total = (
            zpd      * 0.35 +
            interest * 0.25 +
            balance  * 0.20 +
            sr       * 0.12 +
            context  * 0.08
        ) * art_cooldown
        return total, signals

    async def _get_recent_art_ids(self, learner_id: int, db: AsyncSession) -> set:
        """
        Returns a set of art_ids for which the learner completed at least one
        session in the last 24 hours. Used by _score_skill to apply an art-level
        cooldown and steer the engine toward variety across arts.
        """
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        r = await db.execute(
            select(Session.art_id)
            .where(
                Session.learner_id == learner_id,
                Session.completed_at >= cutoff,
                Session.art_id.isnot(None),
            )
        )
        return set(r.scalars().all())

    async def _get_all_skills(self, db):
        r = await db.execute(
            select(Skill).where(Skill.is_active == True).order_by(Skill.sort_order)
        )
        return r.scalars().all()

    async def _get_all_progress(self, learner_id, db):
        r = await db.execute(
            select(LearnerSkillProgress).where(LearnerSkillProgress.learner_id == learner_id)
        )
        return {p.skill_id: p for p in r.scalars().all()}

    async def _get_streak(self, learner_id, db):
        r = await db.execute(
            select(LearnerStreak).where(LearnerStreak.learner_id == learner_id)
        )
        return r.scalar_one_or_none()

    def _make_title(self, skill, level: int) -> str:
        verbs = {0: "Discover", 1: "Explore", 2: "Deepen", 3: "Teach"}
        return f"{verbs.get(level, 'Explore')}: {skill.name}"

    def _estimate_duration(self, level: int, streak) -> int:
        base = 15 + (level * 3)
        return base + 5 if (streak and streak.current_streak >= 7) else base

    def _make_reasoning(self, signals: dict, skill) -> str:
        parts = []
        if signals.get("zpd", 0) > 0.7:
            parts.append(f"you're close to the next level in {skill.name}")
        if signals.get("spaced_repetition", 0) > 0.6:
            parts.append("it's the right time to revisit this before it fades")
        if signals.get("radar_balance", 0) > 0.3:
            parts.append("this area of your development could use some attention")
        if signals.get("interest", 0) > 0.7:
            parts.append("you've shown real investment here before")
        if signals.get("art_cooldown", 1.0) < 1.0:
            parts.append("stepping into a different area from what you've been doing today")
        if not parts:
            parts.append("this is a good next step on your journey")
        return "I'm suggesting this because " + ", and ".join(parts) + "."
