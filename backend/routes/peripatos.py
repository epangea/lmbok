# peripatos1_01.py — P2: Peripatos learning journal routes
#
# Endpoints:
#   POST   /api/peripatos/           save a Socratic exchange
#   GET    /api/peripatos/           list all entries for current learner
#   GET    /api/peripatos/{id}       fetch a single entry (messages included)
#   DELETE /api/peripatos/{id}       delete an entry
#
# Auth: require_learner (same dep used elsewhere; check auth9_01.py if import fails)
# DB:   request.app.state.pool (aiomysql)

from __future__ import annotations

import json
from typing import List

import aiomysql
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

# ── Auth dependency ───────────────────────────────────────────────────────────
# Verify exact function name against auth9_01.py if this import fails.
from routes.auth import get_current_learner

router = APIRouter()


# ── Pydantic models ───────────────────────────────────────────────────────────

class MessageItem(BaseModel):
    role: str          # 'user' | 'assistant'
    content: str


class SaveEntryPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    messages: List[MessageItem] = Field(..., min_items=1)


# ── DB helper ─────────────────────────────────────────────────────────────────

def _pool(request: Request):
    return request.app.state.pool


def _iso(dt):
    """Serialize datetime → ISO string; pass None through."""
    return dt.isoformat() if dt else None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/", status_code=201)
async def save_entry(
    request: Request,
    payload: SaveEntryPayload,
    learner=Depends(get_current_learner),
):
    """Save a Socratic exchange to the learner's Peripatos journal."""
    messages_json = json.dumps([m.dict() for m in payload.messages])

    async with _pool(request).acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """
                INSERT INTO peripatos_entries (learner_id, title, messages)
                VALUES (%s, %s, %s)
                """,
                (learner.id, payload.title, messages_json),
            )
            entry_id = cur.lastrowid
            await conn.commit()

    return {"ok": True, "id": entry_id, "title": payload.title}


@router.get("/")
async def list_entries(
    request: Request,
    learner=Depends(get_current_learner),
):
    """List all Peripatos entries for the current learner, newest first."""
    async with _pool(request).acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """
                SELECT id,
                       title,
                       JSON_LENGTH(messages) AS turn_count,
                       created_at
                FROM peripatos_entries
                WHERE learner_id = %s
                ORDER BY created_at DESC
                """,
                (learner.id,),
            )
            rows = await cur.fetchall()

    for row in rows:
        row["created_at"] = _iso(row["created_at"])

    return {"entries": rows}


@router.get("/{entry_id}")
async def get_entry(
    request: Request,
    entry_id: int,
    learner=Depends(get_current_learner),
):
    """Fetch a single Peripatos entry including full message thread."""
    async with _pool(request).acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """
                SELECT id, title, messages, created_at
                FROM peripatos_entries
                WHERE id = %s AND learner_id = %s
                """,
                (entry_id, learner.id),
            )
            row = await cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Entry not found")

    row["created_at"] = _iso(row["created_at"])

    # aiomysql returns JSON columns as strings; parse to list
    if isinstance(row["messages"], str):
        row["messages"] = json.loads(row["messages"])

    return row


@router.delete("/{entry_id}", status_code=204)
async def delete_entry(
    request: Request,
    entry_id: int,
    learner=Depends(get_current_learner),
):
    """Delete a Peripatos entry (learner must own it)."""
    async with _pool(request).acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                DELETE FROM peripatos_entries
                WHERE id = %s AND learner_id = %s
                """,
                (entry_id, learner.id),
            )
            affected = cur.rowcount
            await conn.commit()

    if affected == 0:
        raise HTTPException(status_code=404, detail="Entry not found")

    return None  # 204 No Content
