# ============================================================
# FreqLearn — routes/polis.py   [polis9_13.py — P27]
# Civic participation portal — The Polis
#
# ACCESS MODEL:
#   Read  (browse referenda, discussions, proposals) — any authenticated learner
#   Write (vote, comment, upvote, submit, support)   — Grove+ via require_polis_access
#   Proposal scope additionally stage-gated (P27):
#     local    — Grove+    (any Polis-access holder)
#     regional — Forest+   (9 arts, 3 domains)
#     global   — Ecosystem (500 XP, 12 arts, all 3 domains)
#
# DB CALL STRATEGY:
#   require_polis_access fetches stage once and returns PolisAccess(learner, stage).
#   Write endpoints receive it via Depends — stage is already in hand, no re-fetch.
#   submit_proposal uses ctx.stage for scope check: zero extra DB calls.
#
# Avatar stage mirrors computeAvatarStage() in app.js:
#   Seed      — start
#   Sprout    — 18 XP + 2 arts
#   Sapling   — 50 XP + 4 arts
#   Grove     — 100 XP + 6 arts + 2 domains  <- Polis write unlocks here
#   Forest    — 200 XP + 9 arts + 3 domains
#   Ecosystem — 500 XP + 12 arts + all 3 domains
#
# GET  /api/polis/my-access                               — stage + access status
# GET  /api/polis/referenda                               — open referenda (filter: scope, bioregion)
# POST /api/polis/referenda/{id}/vote                     — cast a vote (Grove+)
# GET  /api/polis/referenda/{id}/discussion               — comments (open read)
# POST /api/polis/referenda/{id}/discussion               — post a comment (Grove+)
# POST /api/polis/referenda/{id}/discussion/{cid}/upvote  — upvote (Grove+, deduped)
# GET  /api/polis/proposals                               — proposals (filter: scope, bioregion)
# POST /api/polis/proposals                               — submit proposal (Grove+, scope enforced)
# POST /api/polis/proposals/{id}/support                  — endorse a proposal (Grove+)
# ============================================================

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from pydantic import BaseModel

from db import get_db
from models import Learner
from routes.auth import get_current_learner
from utils import compute_avatar_stage, get_learner_stage

router = APIRouter()


# -- Scope -> stage enforcement (P27) -------------------------
# Mirrors frontend scope-gating in polis9_11.html.
SCOPE_PERMITTED = {
    "local":    {"grove", "forest", "ecosystem"},
    "regional": {"forest", "ecosystem"},
    "global":   {"ecosystem"},
}
SCOPE_MIN_STAGE = {
    "local":    ("grove",     "\U0001f333", "Grove"),
    "regional": ("forest",    "\U0001f332", "Forest"),
    "global":   ("ecosystem", "\U0001f30d", "Ecosystem"),
}
VALID_SCOPES = ("local", "regional", "global")


# -- PolisAccess context --------------------------------------
@dataclass
class PolisAccess:
    """Carries learner + pre-computed stage through write-endpoint dependencies.
    Eliminates redundant DB calls: stage is fetched once in require_polis_access
    and reused by the endpoint body without a second lookup."""
    learner: Learner
    stage:   dict


async def require_polis_access(
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
) -> PolisAccess:
    """Gate: Grove+ only. Returns PolisAccess so callers get stage for free."""
    stage = await get_learner_stage(learner, db)
    if not stage["can_access_polis"]:
        raise HTTPException(
            403,
            f"The Polis opens at Grove stage ({stage['icon']} {stage['label']} -> \U0001f333 Grove). "
            f"Keep surfing — you need 100 XP across 6 arts in 2 domains."
        )
    return PolisAccess(learner=learner, stage=stage)


# -- Pydantic models ------------------------------------------
class VoteIn(BaseModel):
    position:  str
    reasoning: Optional[str] = None

class CommentIn(BaseModel):
    body:      str
    parent_id: Optional[int] = None

class ProposalIn(BaseModel):
    title:       str
    description: Optional[str] = None
    scope:       str = "local"
    bioregion:   Optional[str] = None


# -- My access ------------------------------------------------
@router.get("/my-access")
async def my_access(
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    """Returns avatar stage and Polis access status for the current learner."""
    return await get_learner_stage(learner, db)


# -- Referenda ------------------------------------------------
@router.get("/referenda")
async def list_referenda(
    scope:     Optional[str] = Query(None, description="Filter: local | regional | global"),
    bioregion: Optional[str] = Query(None, description="Filter by bioregion name"),
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    """Open referenda — readable by any authenticated learner.
    Optional query params: ?scope=local&bioregion=Annamite+Coast"""
    if scope and scope not in VALID_SCOPES:
        raise HTTPException(400, "scope must be local, regional, or global")

    filters = ["r.status = :status"]
    params  = {"lid": learner.id, "status": "open"}
    if scope:
        filters.append("r.scope = :scope")
        params["scope"] = scope
    if bioregion:
        filters.append("r.bioregion = :bioregion")
        params["bioregion"] = bioregion
    where = " AND ".join(filters)

    rows = await db.execute(text(
        "SELECT r.id, r.title, r.description, r.scope, r.bioregion,"
        "       r.status, r.opens_at, r.closes_at, r.created_at,"
        "       COUNT(v.id)                                             AS total_votes,"
        "       SUM(v.position = 'support')                            AS support_count,"
        "       SUM(v.position = 'oppose')                             AS oppose_count,"
        "       SUM(v.position = 'abstain')                            AS abstain_count,"
        "       MAX(CASE WHEN v.learner_id = :lid THEN v.position END) AS my_vote"
        "  FROM referenda r"
        "  LEFT JOIN referendum_votes v ON v.referendum_id = r.id"
        f" WHERE {where}"
        "  GROUP BY r.id"
        "  ORDER BY r.created_at DESC"
    ), params)

    results = []
    for row in rows.mappings():
        results.append({
            "id":            row["id"],
            "title":         row["title"],
            "description":   row["description"],
            "scope":         row["scope"],
            "bioregion":     row["bioregion"],
            "status":        row["status"],
            "closes_at":     row["closes_at"].isoformat() if row["closes_at"] else None,
            "total_votes":   int(row["total_votes"]   or 0),
            "support_count": int(row["support_count"] or 0),
            "oppose_count":  int(row["oppose_count"]  or 0),
            "abstain_count": int(row["abstain_count"] or 0),
            "my_vote":       row["my_vote"],
        })
    return results


@router.post("/referenda/{ref_id}/vote")
async def cast_vote(
    ref_id: int,
    req: VoteIn,
    ctx: PolisAccess = Depends(require_polis_access),
    db: AsyncSession = Depends(get_db)
):
    if req.position not in ("support", "oppose", "abstain"):
        raise HTTPException(400, "Position must be support, oppose, or abstain")

    row = await db.execute(text(
        "SELECT id, status FROM referenda WHERE id = :id"
    ), {"id": ref_id})
    ref = row.mappings().first()
    if not ref:
        raise HTTPException(404, "Referendum not found")
    if ref["status"] != "open":
        raise HTTPException(400, "This referendum is no longer open")

    await db.execute(text(
        "INSERT INTO referendum_votes (referendum_id, learner_id, position, reasoning, created_at)"
        " VALUES (:rid, :lid, :pos, :rsn, NOW())"
        " ON DUPLICATE KEY UPDATE position = :pos, reasoning = :rsn"
    ), {"rid": ref_id, "lid": ctx.learner.id, "pos": req.position, "rsn": req.reasoning})
    await db.commit()
    return {"ok": True, "position": req.position}


@router.get("/referenda/{ref_id}/discussion")
async def get_discussion(
    ref_id: int,
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    """Discussion thread — readable by any authenticated learner."""
    rows = await db.execute(text(
        "SELECT d.id, d.learner_id, d.parent_id, d.body, d.upvotes, d.created_at,"
        "       l.display_name, l.avatar_emoji"
        "  FROM polis_discussions d"
        "  JOIN learners l ON l.id = d.learner_id"
        " WHERE d.referendum_id = :rid"
        " ORDER BY d.created_at ASC"
    ), {"rid": ref_id})
    return [dict(r) for r in rows.mappings()]


@router.post("/referenda/{ref_id}/discussion")
async def post_comment(
    ref_id: int,
    req: CommentIn,
    ctx: PolisAccess = Depends(require_polis_access),
    db: AsyncSession = Depends(get_db)
):
    if not req.body or not req.body.strip():
        raise HTTPException(400, "Comment body cannot be empty")
    result = await db.execute(text(
        "INSERT INTO polis_discussions (referendum_id, learner_id, parent_id, body, created_at)"
        " VALUES (:rid, :lid, :pid, :body, NOW())"
    ), {"rid": ref_id, "lid": ctx.learner.id, "pid": req.parent_id, "body": req.body.strip()})
    await db.commit()
    return {"ok": True, "id": result.lastrowid}


@router.post("/referenda/{ref_id}/discussion/{comment_id}/upvote")
async def upvote_comment(
    ref_id: int,
    comment_id: int,
    ctx: PolisAccess = Depends(require_polis_access),
    db: AsyncSession = Depends(get_db)
):
    """
    Upvote a discussion comment. Grove+ only.
    Server-side dedup via polis_discussion_upvotes junction table.
    Returns current upvote count; already_upvoted=True on duplicate (no error, no double-increment).
    """
    row = await db.execute(text(
        "SELECT id FROM polis_discussions WHERE id = :cid AND referendum_id = :rid"
    ), {"cid": comment_id, "rid": ref_id})
    if not row.first():
        raise HTTPException(404, "Comment not found")

    existing = await db.execute(text(
        "SELECT 1 FROM polis_discussion_upvotes WHERE learner_id = :lid AND comment_id = :cid"
    ), {"lid": ctx.learner.id, "cid": comment_id})

    if existing.first():
        count_row = await db.execute(text(
            "SELECT upvotes FROM polis_discussions WHERE id = :cid"
        ), {"cid": comment_id})
        return {"ok": True, "upvotes": count_row.scalar_one(), "already_upvoted": True}

    await db.execute(text(
        "INSERT INTO polis_discussion_upvotes (learner_id, comment_id) VALUES (:lid, :cid)"
    ), {"lid": ctx.learner.id, "cid": comment_id})
    await db.execute(text(
        "UPDATE polis_discussions SET upvotes = upvotes + 1 WHERE id = :cid"
    ), {"cid": comment_id})
    await db.commit()

    count_row = await db.execute(text(
        "SELECT upvotes FROM polis_discussions WHERE id = :cid"
    ), {"cid": comment_id})
    return {"ok": True, "upvotes": count_row.scalar_one(), "already_upvoted": False}


# -- Proposals ------------------------------------------------
@router.get("/proposals")
async def list_proposals(
    scope:     Optional[str] = Query(None, description="Filter: local | regional | global"),
    bioregion: Optional[str] = Query(None, description="Filter by bioregion name"),
    learner: Learner = Depends(get_current_learner),
    db: AsyncSession = Depends(get_db)
):
    """Proposals — readable by any authenticated learner.
    Optional query params: ?scope=regional&bioregion=Annamite+Coast"""
    if scope and scope not in VALID_SCOPES:
        raise HTTPException(400, "scope must be local, regional, or global")

    filters = ["p.status != :excluded"]
    params  = {"lid": learner.id, "excluded": "archived"}
    if scope:
        filters.append("p.scope = :scope")
        params["scope"] = scope
    if bioregion:
        filters.append("p.bioregion = :bioregion")
        params["bioregion"] = bioregion
    where = " AND ".join(filters)

    rows = await db.execute(text(
        "SELECT p.id, p.title, p.description, p.scope, p.bioregion,"
        "       p.status, p.support_count, p.created_at,"
        "       l.display_name, l.avatar_emoji,"
        "       MAX(CASE WHEN ps.learner_id = :lid THEN 1 ELSE 0 END) AS i_support"
        "  FROM proposals p"
        "  JOIN learners l ON l.id = p.learner_id"
        "  LEFT JOIN proposal_supports ps ON ps.proposal_id = p.id"
        f" WHERE {where}"
        "  GROUP BY p.id"
        "  ORDER BY p.support_count DESC, p.created_at DESC"
        "  LIMIT 50"
    ), params)
    return [dict(r) for r in rows.mappings()]


@router.post("/proposals")
async def submit_proposal(
    req: ProposalIn,
    ctx: PolisAccess = Depends(require_polis_access),
    db: AsyncSession = Depends(get_db)
):
    if not req.title or not req.title.strip():
        raise HTTPException(400, "Title is required")
    if req.scope not in VALID_SCOPES:
        raise HTTPException(400, "Scope must be local, regional, or global")

    # Scope enforcement via ctx.stage — already computed by require_polis_access.
    # No additional DB call needed.
    if ctx.stage["key"] not in SCOPE_PERMITTED.get(req.scope, set()):
        _, min_icon, min_label = SCOPE_MIN_STAGE[req.scope]
        stage_icon  = ctx.stage["icon"]
        stage_label = ctx.stage["label"]
        raise HTTPException(
            403,
            f"Submitting a {req.scope} proposal requires {min_icon} {min_label} stage "
            f"(you are {stage_icon} {stage_label}). Keep surfing — you're on your way."
        )

    result = await db.execute(text(
        "INSERT INTO proposals (learner_id, title, description, scope, bioregion, created_at)"
        " VALUES (:lid, :title, :desc, :scope, :bio, NOW())"
    ), {
        "lid":   ctx.learner.id,
        "title": req.title.strip(),
        "desc":  req.description,
        "scope": req.scope,
        "bio":   req.bioregion,
    })
    await db.commit()
    return {"ok": True, "id": result.lastrowid}


@router.post("/proposals/{prop_id}/support")
async def support_proposal(
    prop_id: int,
    ctx: PolisAccess = Depends(require_polis_access),
    db: AsyncSession = Depends(get_db)
):
    existing = await db.execute(text(
        "SELECT 1 FROM proposal_supports WHERE proposal_id=:pid AND learner_id=:lid"
    ), {"pid": prop_id, "lid": ctx.learner.id})

    if existing.first():
        await db.execute(text(
            "DELETE FROM proposal_supports WHERE proposal_id=:pid AND learner_id=:lid"
        ), {"pid": prop_id, "lid": ctx.learner.id})
        await db.execute(text(
            "UPDATE proposals SET support_count = GREATEST(support_count-1,0) WHERE id=:pid"
        ), {"pid": prop_id})
        supported = False
    else:
        await db.execute(text(
            "INSERT IGNORE INTO proposal_supports (proposal_id, learner_id, created_at)"
            " VALUES (:pid, :lid, NOW())"
        ), {"pid": prop_id, "lid": ctx.learner.id})
        await db.execute(text(
            "UPDATE proposals SET support_count = support_count+1 WHERE id=:pid"
        ), {"pid": prop_id})
        supported = True

    await db.commit()
    return {"ok": True, "supported": supported}
