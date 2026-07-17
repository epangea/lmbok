# ============================================================
# FreqLearn Backend — main.py
# FastAPI entry point — schema v2
# Run: uvicorn main:app --host 0.0.0.0 --port 8000
# ============================================================

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from db import engine, Base
from cookie_auth import (
    ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER,
    ORG_ACCESS_COOKIE, ORG_CSRF_COOKIE,
    ADMIN_ACCESS_COOKIE, ADMIN_CSRF_COOKIE,
)

# ── Route imports ─────────────────────────────────────────
from routes.auth            import router as auth_router
from routes.learners        import router as learners_router
from routes.skills          import router as skills_router
from routes.sessions        import router as sessions_router
from routes.progress        import router as progress_router
from routes.radar           import router as radar_router
from routes.matching        import router as matching_router
from routes.generate        import router as generate_router
from routes.contribute      import router as contribute_router
from routes.polis           import router as polis_router
from routes.reflections     import router as reflections_router
from routes.ollama_generate import router as ollama_router
from routes.groq_generate   import router as groq_router
from routes.orgs            import router as orgs_router
from routes.admin           import router as admin_router
from routes.bioregions      import router as bioregions_router
from routes.peripatos       import router as peripatos_router

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("freqlearn")


# ── Lifespan ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tables managed via schema.sql — no create_all to avoid
    # silently diverging from the canonical schema.
    logger.info("FreqLearn API starting — schema v2 (P_MAP versioning)")
    yield
    logger.info("FreqLearn API shutting down")


# ── App ───────────────────────────────────────────────────
app = FastAPI(
    title       = "FreqLearn API",
    description = "Surfing the Frequencies — adaptive lifelong learning platform",
    version     = "2.1.0",
    lifespan    = lifespan,
)

# ── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://build.onehouse.top",
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── CSRF (double-submit cookie check) ─────────────────────
# Added 2026-07-16 as part of P-SEC1: now that auth tokens live in httpOnly
# cookies, browsers attach them automatically to *any* request to this origin
# — including ones triggered by a malicious cross-site page. A JS-readable
# csrf cookie + a required matching header closes that gap: a cross-site
# attacker can make the browser send the auth cookies, but can't read the
# csrf cookie's value to also put it in the header, so the request 403s.
# GET/HEAD/OPTIONS are left alone (safe methods, no state change). The
# session-establishing endpoints are exempt because no csrf cookie exists
# until after they succeed.
_CSRF_EXEMPT_PATHS = {
    "/api/auth/register", "/api/auth/login", "/api/auth/refresh",
    "/api/orgs/register", "/api/orgs/login",
    "/api/admin/login",
}

@app.middleware("http")
async def csrf_protect(request: Request, call_next):
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return await call_next(request)
    if request.url.path in _CSRF_EXEMPT_PATHS:
        return await call_next(request)

    # Admin session cookie is checked by presence, not path prefix, because
    # admin-gated routes live under two different prefixes (/api/admin/* and
    # /api/bioregions/admin/*) — see cookie_auth.py's ADMIN_ACCESS_COOKIE_PATH
    # comment. Added 2026-07-17 as part of P-SEC2 (admin moved off the old
    # X-Admin-Key-header-only auth that fell through this middleware entirely).
    if request.cookies.get(ADMIN_ACCESS_COOKIE):
        cookie_name = ADMIN_CSRF_COOKIE
        session_cookie = ADMIN_ACCESS_COOKIE
    elif request.url.path.startswith("/api/orgs"):
        cookie_name = ORG_CSRF_COOKIE
        session_cookie = ORG_ACCESS_COOKIE
    else:
        cookie_name = CSRF_COOKIE
        session_cookie = ACCESS_COOKIE

    # Requests with no matching session cookie at all aren't riding on
    # cookie auth for this request — let them through; they'll 401/403 on
    # their own merits if they needed auth.
    if not request.cookies.get(session_cookie):
        return await call_next(request)

    cookie_val  = request.cookies.get(cookie_name)
    header_val  = request.headers.get(CSRF_HEADER)
    if not cookie_val or not header_val or cookie_val != header_val:
        return JSONResponse({"detail": "CSRF check failed"}, status_code=403)

    return await call_next(request)


# ── Routers ───────────────────────────────────────────────
app.include_router(auth_router,        prefix="/api/auth",        tags=["auth"])
app.include_router(learners_router,    prefix="/api/learners",    tags=["learners"])
app.include_router(skills_router,      prefix="/api",             tags=["skills"])
app.include_router(sessions_router,    prefix="/api/sessions",    tags=["sessions"])
app.include_router(progress_router,    prefix="/api/progress",    tags=["progress"])
app.include_router(radar_router,       prefix="/api/radar",       tags=["radar"])
app.include_router(matching_router,    prefix="/api/matching",    tags=["matching"])
app.include_router(generate_router,    prefix="/api/generate",    tags=["generate"])
app.include_router(contribute_router,  prefix="/api/contribute",  tags=["contribute"])
app.include_router(polis_router,       prefix="/api/polis",       tags=["polis"])
app.include_router(reflections_router, prefix="/api/reflections", tags=["reflections"])
app.include_router(ollama_router,      prefix="/api/ollama",      tags=["ollama"])
app.include_router(groq_router,        prefix="/api/groq",        tags=["groq"])
app.include_router(orgs_router,        prefix="/api/orgs",        tags=["orgs"])
app.include_router(admin_router,       prefix="/api/admin",       tags=["admin"])
app.include_router(bioregions_router,  prefix="/api/bioregions",  tags=["bioregions"])
app.include_router(peripatos_router,   prefix="/api/peripatos",   tags=["peripatos"])


# ── Health check ──────────────────────────────────────────
@app.get("/api/health", tags=["meta"])
async def health():
    return {"status": "ok", "version": "2.1.0"}
