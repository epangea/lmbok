# ============================================================
# ADD THIS BLOCK TO routes/learners.py
# Paste after the existing @router.patch("/me/preferences") block.
# Also add these imports at the top of learners.py if not present:
#   from models import ArtsGroup, Arts, ArtsSkills, LearnerSkillProgress
#   from datetime import datetime, timezone
# ============================================================

from pydantic import BaseModel as _BaseModel

class SeedProgressRequest(_BaseModel):
    # Keys: "being", "becoming", "connecting"
    # Values: 0 = new, 1 = some experience, 2 = comfortable
    familiarity: dict


@router.post("/me/seed-progress")
async def seed_initial_progress(
    req: SeedProgressRequest,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    """
    Called once after onboarding. Seeds learner_skill_progress rows
    based on self-reported familiarity per art group, so the
    recommendation engine has real signal from the very first session.

    Familiarity levels:
      0 = new        → evidence_count=1,  current_level=0
      1 = some       → evidence_count=2,  current_level=0
      2 = comfortable → evidence_count=0, current_level=1
    """
    # Load group → arts → skills mapping
    groups_q = await db.execute(select(ArtsGroup))
    groups   = {g.slug: g for g in groups_q.scalars().all()}

    arts_q = await db.execute(select(Arts))
    arts   = arts_q.scalars().all()

    mappings_q = await db.execute(select(ArtsSkills))
    mappings   = mappings_q.scalars().all()

    # Build group_slug → [skill_ids]
    art_to_group  = {a.id: a.group_id for a in arts}
    group_id_map  = {g.id: slug for slug, g in groups.items()}
    group_skills: dict[str, list[int]] = {}
    for m in mappings:
        gslug = group_id_map.get(art_to_group.get(m.art_id))
        if gslug:
            group_skills.setdefault(gslug, []).append(m.skill_id)

    # Existing progress rows (don't overwrite real progress)
    existing_q = await db.execute(
        select(LearnerSkillProgress)
        .where(LearnerSkillProgress.learner_id == learner.id)
    )
    existing_ids = {p.skill_id for p in existing_q.scalars().all()}

    seeded = 0
    now    = datetime.now(timezone.utc)

    for group_slug, fam_level in req.familiarity.items():
        fam_level = int(fam_level)
        skill_ids = group_skills.get(group_slug, [])

        if fam_level == 0:
            ev, lv = 1, 0     # new: tiny signal, no level
        elif fam_level == 1:
            ev, lv = 2, 0     # some: approaching level 1
        else:
            ev, lv = 0, 1     # comfortable: already at level 1

        for sid in skill_ids:
            if sid in existing_ids:
                continue      # never overwrite real session progress
            db.add(LearnerSkillProgress(
                learner_id=learner.id,
                skill_id=sid,
                current_level=lv,
                evidence_count=ev,
                recall_count=ev,
                last_practiced_at=None,
            ))
            seeded += 1

    await db.commit()
    return {"seeded": seeded}
