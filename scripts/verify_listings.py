#!/usr/bin/env python3
"""
FreqLearn — Listing URL Verifier
Checks all source_urls in opportunity_listings and reports status.
Run from server with venv active.

Usage:
    python verify_listings.py              # check + report only
    python verify_listings.py --fix        # also deactivate dead listings in DB
"""

import asyncio
import sys
import os
import httpx
from datetime import datetime, timezone

# ── DB connection (only needed with --fix) ────────────────
DB_CONFIG = {
    "host":     "localhost",
    "user":     "freqlearn",
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": "freqlearn",
}

# ── Listings with URLs (from audit — extend as scavenger adds more) ──
LISTINGS = [
    {"id": 68, "title": "Program Coordinator, Community Outreach Program",
     "url": "https://www.worldvision.org/jobs"},
    {"id": 69, "title": "Research Intern, Sustainable Agriculture Project",
     "url": "https://www.unesco.org/new/en/unesco/organisation/jobs/"},
    {"id": 70, "title": "Global Education Volunteer, Teach English in South Africa",
     "url": "https://www.iyervalli.org/teach-english-abroad"},
    {"id": 71, "title": "Environmental Education Program Manager, National Park Service",
     "url": "https://www.nps.gov/hrp/jobs/index.htm"},
    {"id": 72, "title": "Community Health Worker, Rural Health Outreach Program",
     "url": "https://www.doctorswithoutborders.org/jobs"},
]

TIMEOUT   = 15.0
HEADERS   = {"User-Agent": "Mozilla/5.0 FreqLearn-Verifier/1.0"}
DEAD_CODES = {404, 410, 451}  # definitely dead
WARN_CODES = {301, 302, 403, 429, 500, 502, 503}  # investigate


async def check_url(client: httpx.AsyncClient, listing: dict) -> dict:
    url = listing["url"]
    result = {**listing, "status": None, "ok": False, "note": ""}
    try:
        r = await client.head(url, follow_redirects=True, timeout=TIMEOUT)
        result["status"] = r.status_code
        if r.status_code == 200:
            result["ok"]   = True
            result["note"] = "✅ Live"
        elif r.status_code in DEAD_CODES:
            result["note"] = f"🔴 DEAD ({r.status_code})"
        elif r.status_code in WARN_CODES:
            # Some servers reject HEAD — retry with GET
            try:
                r2 = await client.get(url, follow_redirects=True, timeout=TIMEOUT)
                result["status"] = r2.status_code
                result["ok"]     = r2.status_code == 200
                result["note"]   = f"{'✅ Live' if r2.status_code == 200 else f'⚠️  Check ({r2.status_code})'} (GET fallback)"
            except Exception as e:
                result["note"] = f"⚠️  HEAD {r.status_code}, GET failed: {e}"
        else:
            result["note"] = f"⚠️  Unexpected ({r.status_code})"
    except httpx.ConnectError:
        result["note"] = "🔴 DEAD (connection refused / DNS failure)"
    except httpx.TimeoutException:
        result["note"] = "⚠️  Timeout — server slow or blocking"
    except Exception as e:
        result["note"] = f"⚠️  Error: {e}"
    return result


async def main():
    fix_mode = "--fix" in sys.argv
    print(f"\nFreqLearn URL Verifier — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Mode: {'FIX (will deactivate dead listings)' if fix_mode else 'REPORT ONLY'}")
    print("=" * 70)

    async with httpx.AsyncClient(headers=HEADERS) as client:
        results = await asyncio.gather(*[check_url(client, l) for l in LISTINGS])

    dead, warn, ok = [], [], []
    for r in results:
        print(f"\n[{r['id']:>3}] {r['title'][:55]}")
        print(f"       URL:    {r['url']}")
        print(f"       Status: {r['note']}")
        if "DEAD" in r["note"]:
            dead.append(r)
        elif "⚠️" in r["note"]:
            warn.append(r)
        else:
            ok.append(r)

    print("\n" + "=" * 70)
    print(f"SUMMARY: {len(ok)} live  |  {len(warn)} warnings  |  {len(dead)} dead")

    if dead:
        print(f"\n🔴 DEAD listings ({len(dead)}):")
        for r in dead:
            print(f"   [{r['id']}] {r['title']}")
        print("\nSQL to deactivate dead listings (review before running):")
        ids = ", ".join(str(r["id"]) for r in dead)
        print(f"""
UPDATE opportunity_listings
SET    is_active = 0,
       deactivation_reason = 'url_dead',
       last_verified_at = NOW()
WHERE  id IN ({ids});
""")

    if warn:
        print(f"\n⚠️  Listings needing manual review ({len(warn)}):")
        for r in warn:
            print(f"   [{r['id']}] {r['title']} — {r['note']}")

    if fix_mode and dead:
        print("\nApplying fixes to DB...")
        try:
            import aiomysql
            conn = await aiomysql.connect(**DB_CONFIG)
            async with conn.cursor() as cur:
                ids = [r["id"] for r in dead]
                await cur.execute(
                    "UPDATE opportunity_listings SET is_active=0, deactivation_reason='url_dead' "
                    "WHERE id IN (%s)" % ",".join(["%s"] * len(ids)),
                    ids
                )
            await conn.commit()
            conn.close()
            print(f"✅ Deactivated {len(dead)} listings in DB.")
        except ImportError:
            print("aiomysql not installed — run the SQL manually from the output above.")
        except Exception as e:
            print(f"DB error: {e}")

    print()


if __name__ == "__main__":
    asyncio.run(main())
