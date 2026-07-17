# ============================================================
# FreqLearn Backend — cookie_auth.py
# Shared helpers for httpOnly-cookie based auth (learner + org).
# Added 2026-07-16 as part of P-SEC1 (move JWTs out of localStorage).
#
# Design:
#   - Access/refresh tokens travel as httpOnly cookies (not readable by JS,
#     not exposed to XSS payloads). Browser attaches them automatically on
#     same-origin requests.
#   - A separate, NON-httpOnly "csrf" cookie holds a random token that JS
#     CAN read. Every state-changing request (POST/PATCH/PUT/DELETE) must
#     echo that value back in an X-CSRF-Token header. This is the standard
#     "double-submit cookie" pattern — an attacker's cross-site form/script
#     can make the browser send the httpOnly cookies, but can't read the
#     csrf cookie to also send a matching header, so the request is
#     rejected. Enforced globally in main.py's csrf_protect middleware.
#   - Learner and org sessions use separate cookie names so a single browser
#     can hold both at once without collision.
# ============================================================

import os
import secrets
from fastapi import Response

COOKIE_SECURE   = os.getenv("COOKIE_SECURE", "true").lower() != "false"  # keep True in prod (HTTPS); allow override for local http dev
COOKIE_SAMESITE = "lax"   # sent on same-site + top-level nav; blocked on cross-site POSTs — first line of CSRF defense, backed up by the double-submit check

# Learner cookies
ACCESS_COOKIE       = "fl_access"
REFRESH_COOKIE      = "fl_refresh"
CSRF_COOKIE         = "fl_csrf"
ACCESS_COOKIE_PATH  = "/api"
REFRESH_COOKIE_PATH = "/api/auth"   # only sent to /api/auth/* — narrows exposure of the long-lived refresh token

# Org cookies (separate namespace from learner cookies)
ORG_ACCESS_COOKIE      = "fl_org_access"
ORG_CSRF_COOKIE        = "fl_org_csrf"
ORG_ACCESS_COOKIE_PATH = "/api/orgs"

CSRF_HEADER = "X-CSRF-Token"


def _new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


# ── Learner ─────────────────────────────────────────────────

def set_learner_cookies(response: Response, access_token: str, refresh_token: str | None = None) -> None:
    """Set fl_access (always) + fl_refresh (only when rotating/issuing a new
    one) as httpOnly, plus fl_csrf as a JS-readable double-submit token."""
    response.set_cookie(
        ACCESS_COOKIE, access_token,
        httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE,
        path=ACCESS_COOKIE_PATH, max_age=30 * 60,
    )
    if refresh_token is not None:
        response.set_cookie(
            REFRESH_COOKIE, refresh_token,
            httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE,
            path=REFRESH_COOKIE_PATH, max_age=30 * 24 * 60 * 60,
        )
    response.set_cookie(
        CSRF_COOKIE, _new_csrf_token(),
        httponly=False, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE,
        path="/", max_age=30 * 24 * 60 * 60,
    )


def clear_learner_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path=ACCESS_COOKIE_PATH)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
    response.delete_cookie(CSRF_COOKIE, path="/")


# ── Org ─────────────────────────────────────────────────────

def set_org_cookies(response: Response, access_token: str) -> None:
    response.set_cookie(
        ORG_ACCESS_COOKIE, access_token,
        httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE,
        path=ORG_ACCESS_COOKIE_PATH, max_age=30 * 24 * 60 * 60,
    )
    response.set_cookie(
        ORG_CSRF_COOKIE, _new_csrf_token(),
        httponly=False, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE,
        path="/", max_age=30 * 24 * 60 * 60,
    )


def clear_org_cookies(response: Response) -> None:
    response.delete_cookie(ORG_ACCESS_COOKIE, path=ORG_ACCESS_COOKIE_PATH)
    response.delete_cookie(ORG_CSRF_COOKIE, path="/")


# ── Admin ───────────────────────────────────────────────────
# Added 2026-07-17 as part of P-SEC2. Admin still authenticates with the
# single shared ADMIN_KEY (checked once, server-side, at POST /api/admin/login)
# but the raw secret is never handed back to the browser and never touches
# localStorage again — this closes the same XSS-exposure class P-SEC1 closed
# for learner/org. A short-lived signed session token stands in for it,
# transported the same httpOnly-cookie-plus-CSRF-cookie way as the others.
#
# ADMIN_ACCESS_COOKIE_PATH is intentionally broad ("/api", not "/api/admin")
# because admin-gated routes live under two different prefixes —
# /api/admin/* (admin.py) and /api/bioregions/admin/* (bioregions.py) — and
# the cookie needs to reach both.
ADMIN_ACCESS_COOKIE      = "fl_admin_session"
ADMIN_CSRF_COOKIE        = "fl_admin_csrf"
ADMIN_ACCESS_COOKIE_PATH = "/api"


def set_admin_cookies(response: Response, admin_token: str) -> None:
    response.set_cookie(
        ADMIN_ACCESS_COOKIE, admin_token,
        httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE,
        path=ADMIN_ACCESS_COOKIE_PATH, max_age=8 * 60 * 60,
    )
    response.set_cookie(
        ADMIN_CSRF_COOKIE, _new_csrf_token(),
        httponly=False, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE,
        path="/", max_age=8 * 60 * 60,
    )


def clear_admin_cookies(response: Response) -> None:
    response.delete_cookie(ADMIN_ACCESS_COOKIE, path=ADMIN_ACCESS_COOKIE_PATH)
    response.delete_cookie(ADMIN_CSRF_COOKIE, path="/")
