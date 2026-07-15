#!/usr/bin/env python3
"""
FreqLearn — seed_listings.py
Seeds 15 organizations and 30 opportunity listings across all 15 Arts.

Run from anywhere as the freqlearn user:
  /var/www/freqlearn/venv/bin/python3 /var/www/freqlearn/scripts/seed_listings.py

Uses aiomysql (already in the venv — no extra installs needed).
Reads DB credentials from backend/.env, same as all other seed scripts.
Safe to re-run: skips orgs/listings that already exist.
"""

import os, sys, json, asyncio
from pathlib import Path

import aiomysql
from dotenv import load_dotenv

# .env lives in backend/ regardless of where this script is placed
_env_path = Path(__file__).parent.parent / "backend" / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).parent / ".env"   # fallback: same dir as script
load_dotenv(dotenv_path=_env_path)

DB = dict(
    host     = os.getenv("DB_HOST",     "127.0.0.1"),
    port     = int(os.getenv("DB_PORT", 3306)),
    user     = os.getenv("DB_USER",     "freqlearn"),
    password = os.getenv("DB_PASSWORD", "changeme"),
    db       = os.getenv("DB_NAME",     "freqlearn"),
    charset  = "utf8mb4",
)

# ── Organizations ─────────────────────────────────────────
ORGS = [
    {"name": "Earth Builders Collective",    "slug": "earth-builders-collective",    "description": "A global network of natural builders practicing earthen, timber and bamboo construction with communities who need affordable, ecological housing.",              "website": "https://earthbuilders.example.org",       "contact_email": "hello@earthbuilders.example.org",       "org_type": "ngo"},
    {"name": "Forest School Alliance",        "slug": "forest-school-alliance",        "description": "Supporting outdoor educators who believe children learn best with mud on their boots.",                                                                          "website": "https://forestschool.example.org",         "contact_email": "connect@forestschool.example.org",       "org_type": "educational"},
    {"name": "Community Kitchen Network",     "slug": "community-kitchen-network",     "description": "Weaving together community kitchens, seed libraries, and food-sovereignty educators.",                                                                           "website": "https://communitykitchen.example.org",     "contact_email": "nourish@communitykitchen.example.org",   "org_type": "community"},
    {"name": "Mindful Cities Lab",            "slug": "mindful-cities-lab",            "description": "A social enterprise researching and prototyping urban design interventions that reduce chronic stress.",                                                           "website": "https://mindfulcities.example.org",        "contact_email": "lab@mindfulcities.example.org",          "org_type": "social_enterprise"},
    {"name": "Open Commons Institute",        "slug": "open-commons-institute",        "description": "Building digital and civic commons: open knowledge, open governance, and open infrastructure that communities anywhere can own, fork, and adapt.",                "website": "https://opencommons.example.org",          "contact_email": "collaborate@opencommons.example.org",    "org_type": "cooperative"},
    {"name": "Watershed Restoration Trust",   "slug": "watershed-restoration-trust",   "description": "Restoring river systems and the cultural knowledge that once kept them alive.",                                                                                   "website": "https://watershed.example.org",            "contact_email": "rivers@watershed.example.org",           "org_type": "ngo"},
    {"name": "Living Arts Collective",        "slug": "living-arts-collective",        "description": "Making art with — not for — communities. Participatory theatre, oral history, mural projects.",                                                                   "website": "https://livingarts.example.org",           "contact_email": "create@livingarts.example.org",          "org_type": "community"},
    {"name": "Listening Circles Network",     "slug": "listening-circles-network",     "description": "Training facilitators in deep listening and non-violent communication to run circles in post-conflict communities.",                                               "website": "https://listeningcircles.example.org",     "contact_email": "circles@listeningcircles.example.org",   "org_type": "ngo"},
    {"name": "Youth Climate Growers",         "slug": "youth-climate-growers",         "description": "A cooperative of young farmers practicing regenerative agriculture and food sovereignty across 12 countries.",                                                     "website": "https://youthgrowers.example.org",         "contact_email": "grow@youthgrowers.example.org",          "org_type": "cooperative"},
    {"name": "Peace Facilitation Centre",     "slug": "peace-facilitation-centre",     "description": "Bringing restorative justice and dialogue facilitation to communities navigating conflict.",                                                                       "website": "https://peacefacilitation.example.org",    "contact_email": "peace@peacefacilitation.example.org",    "org_type": "ngo"},
    {"name": "Regenerative Design School",    "slug": "regenerative-design-school",    "description": "Teaching ecological design from first principles: permaculture, bioclimatic architecture, and systems thinking.",                                                 "website": "https://regendesign.example.org",          "contact_email": "school@regendesign.example.org",         "org_type": "educational"},
    {"name": "Community Health Weavers",      "slug": "community-health-weavers",      "description": "Trauma-informed community health workers stitching together peer support and preventive care in underserved neighbourhoods.",                                     "website": "https://healthweavers.example.org",        "contact_email": "care@healthweavers.example.org",         "org_type": "ngo"},
    {"name": "Global Storytellers Guild",     "slug": "global-storytellers-guild",     "description": "Preserving and amplifying oral traditions across 40 languages via community radio, podcasts, and storytelling residencies.",                                      "website": "https://storytellersguild.example.org",    "contact_email": "stories@storytellersguild.example.org",  "org_type": "cooperative"},
    {"name": "Bioregional Mapping Project",   "slug": "bioregional-mapping-project",   "description": "Combining citizen science, Indigenous ecological knowledge, and open cartography to map living landscapes.",                                                       "website": "https://bioregionalmapping.example.org",   "contact_email": "map@bioregionalmapping.example.org",     "org_type": "ngo"},
    {"name": "Movement & Somatic Arts Studio","slug": "movement-somatic-arts-studio",  "description": "Somatic movement, dance, and embodied wellness for schools, care homes, and refugee communities — free where possible.",                                          "website": "https://somaticarts.example.org",          "contact_email": "move@somaticarts.example.org",           "org_type": "social_enterprise"},
]

# ── Listings (2 per org = 30 total) ───────────────────────
LISTINGS = [
    {"org_slug": "earth-builders-collective",    "title": "Natural Building Workshop Facilitator",        "description": "Lead hands-on earthen and bamboo construction workshops with community groups in rural areas. Training provided.",              "listing_type": "volunteer",   "required_arts": ["build", "give", "collaborate"]},
    {"org_slug": "earth-builders-collective",    "title": "Bioregional Design Researcher",                "description": "Document vernacular building traditions across three bioregions and synthesise findings into open-access guides.",             "listing_type": "project",     "required_arts": ["build", "understand", "respect"]},
    {"org_slug": "forest-school-alliance",       "title": "Outdoor Learning Guide",                       "description": "Accompany groups of children (5–12) into woodland settings, facilitating free play and nature crafts. Training provided.",   "listing_type": "volunteer",   "required_arts": ["move", "notice", "give"]},
    {"org_slug": "forest-school-alliance",       "title": "Forest School Curriculum Developer",           "description": "Design a modular outdoor learning curriculum adaptable to different biomes, languages, and developmental phases.",            "listing_type": "job",         "required_arts": ["notice", "understand", "grow"]},
    {"org_slug": "community-kitchen-network",    "title": "Food Sovereignty Educator",                    "description": "Run weekly cooking workshops rooted in traditional food knowledge with urban communities.",                                   "listing_type": "volunteer",   "required_arts": ["eat", "give", "express"]},
    {"org_slug": "community-kitchen-network",    "title": "Fermentation & Food Systems Intern",           "description": "Support our fermentation research programme: documenting regional traditions and maintaining our living culture library.",    "listing_type": "internship",  "required_arts": ["eat", "understand", "grow"]},
    {"org_slug": "mindful-cities-lab",           "title": "Community Well-being Facilitator",             "description": "Co-design and run neighbourhood stress-reduction programmes — breathing circles, quiet walks, and listening sessions.",       "listing_type": "project",     "required_arts": ["feel", "live", "listen"]},
    {"org_slug": "mindful-cities-lab",           "title": "Urban Mindfulness Researcher",                 "description": "Mixed-methods research studying the impact of urban design on emotional regulation. Field observation and interviews.",       "listing_type": "job",         "required_arts": ["feel", "understand", "notice"]},
    {"org_slug": "open-commons-institute",       "title": "Open Knowledge Contributor",                   "description": "Write, translate, or illustrate for our open-access knowledge commons covering civic education and ecological literacy.",     "listing_type": "volunteer",   "required_arts": ["understand", "collaborate", "express"]},
    {"org_slug": "open-commons-institute",       "title": "Digital Commons Coordinator",                  "description": "Manage our federated network of open-source tools and run onboarding calls for new cooperative members.",                    "listing_type": "job",         "required_arts": ["collaborate", "understand", "live"]},
    {"org_slug": "watershed-restoration-trust",  "title": "River Monitoring Volunteer",                   "description": "Join seasonal monitoring teams: water sampling, species counts, and GPS mapping of riparian zones. Equipment provided.",     "listing_type": "volunteer",   "required_arts": ["respect", "consume", "notice"]},
    {"org_slug": "watershed-restoration-trust",  "title": "Water Policy Researcher",                      "description": "Analyse regulatory frameworks governing water use across five countries and produce accessible policy briefs.",              "listing_type": "project",     "required_arts": ["consume", "understand", "live"]},
    {"org_slug": "living-arts-collective",       "title": "Community Arts Facilitator",                   "description": "Facilitate participatory mural and mosaic projects with neighbourhoods in transition, centering community members as artists.","listing_type": "volunteer",   "required_arts": ["express", "collaborate", "give"]},
    {"org_slug": "living-arts-collective",       "title": "Oral History Recorder",                        "description": "Interview elders, transcribe and archive their stories, and co-create multimedia artefacts communities can share.",          "listing_type": "project",     "required_arts": ["express", "listen", "receive"]},
    {"org_slug": "listening-circles-network",    "title": "Conflict Mediation Trainee",                   "description": "Complete our 6-month facilitation training, then co-run listening circles in schools and community centres. Stipend available.","listing_type": "internship", "required_arts": ["listen", "feel", "collaborate"]},
    {"org_slug": "listening-circles-network",    "title": "Community Dialogue Facilitator",               "description": "Facilitate structured dialogues between groups in conflict using our evidence-based restorative circle method.",              "listing_type": "volunteer",   "required_arts": ["listen", "respect", "collaborate"]},
    {"org_slug": "youth-climate-growers",        "title": "Regenerative Farm Apprentice",                 "description": "6-month apprenticeship: soil science, seed saving, composting, and agroforestry. Food and accommodation included.",          "listing_type": "internship",  "required_arts": ["grow", "eat", "understand"]},
    {"org_slug": "youth-climate-growers",        "title": "Permaculture Education Coordinator",           "description": "Design and run permaculture design courses for youth groups across three countries, adapting content to local contexts.",     "listing_type": "job",         "required_arts": ["grow", "understand", "build"]},
    {"org_slug": "peace-facilitation-centre",    "title": "Peacebuilding Programme Support",              "description": "Support facilitation of dialogue between divided communities: logistics, co-facilitation, and programme documentation.",      "listing_type": "volunteer",   "required_arts": ["collaborate", "listen", "respect"]},
    {"org_slug": "peace-facilitation-centre",    "title": "Non-Violent Communication Trainer",            "description": "Deliver NVC workshops to schools, prisons, and community organisations. Multilingual candidates strongly encouraged.",       "listing_type": "job",         "required_arts": ["listen", "collaborate", "feel"]},
    {"org_slug": "regenerative-design-school",   "title": "Sustainable Architecture Teaching Assistant",  "description": "Support our 3-month bioclimatic design course: studio critiques, material testing, and mentoring students.",                "listing_type": "internship",  "required_arts": ["build", "understand", "respect"]},
    {"org_slug": "regenerative-design-school",   "title": "Green Building Research Fellow",               "description": "6-month fellowship developing open-source construction guides for low-tech, high-performance buildings across climates.",     "listing_type": "project",     "required_arts": ["build", "grow", "consume"]},
    {"org_slug": "community-health-weavers",     "title": "Trauma-Informed Care Volunteer",               "description": "Accompany community health workers on home visits, providing emotional support and peer-listening to isolated residents.",    "listing_type": "volunteer",   "required_arts": ["feel", "give", "receive"]},
    {"org_slug": "community-health-weavers",     "title": "Community Health Navigator",                   "description": "Help community members navigate health systems and run health-literacy workshops in their home language.",                    "listing_type": "job",         "required_arts": ["give", "live", "listen"]},
    {"org_slug": "global-storytellers-guild",    "title": "Community Radio Host",                         "description": "Host a weekly community radio programme in your language — interviews, music, and stories centering rarely-heard voices.",   "listing_type": "volunteer",   "required_arts": ["express", "listen", "collaborate"]},
    {"org_slug": "global-storytellers-guild",    "title": "Multilingual Storytelling Facilitator",        "description": "Facilitate intergenerational storytelling workshops in 2+ languages, documenting traditional narratives.",                   "listing_type": "project",     "required_arts": ["express", "receive", "understand"]},
    {"org_slug": "bioregional-mapping-project",  "title": "Environmental Data Volunteer",                 "description": "Contribute to open ecological datasets: species observations, land-use surveys, and local ecological knowledge capture.",    "listing_type": "volunteer",   "required_arts": ["notice", "respect", "understand"]},
    {"org_slug": "bioregional-mapping-project",  "title": "Ecological Literacy Educator",                 "description": "Design and run ecological literacy programmes for schools, integrating bioregional mapping tools and Indigenous land knowledge.","listing_type": "job",       "required_arts": ["notice", "respect", "consume"]},
    {"org_slug": "movement-somatic-arts-studio", "title": "Somatic Movement Teaching Assistant",          "description": "Co-teach gentle somatic movement and breath work classes for elders, trauma survivors, and refugee communities.",            "listing_type": "internship",  "required_arts": ["move", "feel", "receive"]},
    {"org_slug": "movement-somatic-arts-studio", "title": "Embodied Wellness Practitioner",               "description": "Deliver individual and small-group somatic sessions in schools, care homes, and community health centres.",                  "listing_type": "job",         "required_arts": ["move", "feel", "express"]},
]


# ── Seed functions ─────────────────────────────────────────
async def seed_orgs(conn) -> dict:
    """Insert orgs if not present; return slug → id map."""
    id_map = {}
    async with conn.cursor() as cur:
        for org in ORGS:
            await cur.execute("SELECT id FROM organizations WHERE slug = %s", (org["slug"],))
            row = await cur.fetchone()
            if row:
                id_map[org["slug"]] = row[0]
                print(f"  skip  {org['name']}")
            else:
                await cur.execute(
                    """INSERT INTO organizations
                         (name, slug, description, website, contact_email,
                          org_type, is_verified, is_active, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s, 0, 1, NOW())""",
                    (org["name"], org["slug"], org["description"],
                     org["website"], org["contact_email"], org["org_type"]),
                )
                id_map[org["slug"]] = cur.lastrowid
                print(f"  + org  {org['name']}")
        await conn.commit()
    return id_map


async def seed_listings(conn, org_id_map: dict):
    """Insert listings linked to their org; skip duplicates."""
    seeded = skipped = 0
    async with conn.cursor() as cur:
        for l in LISTINGS:
            org_id = org_id_map.get(l["org_slug"])
            if not org_id:
                print(f"  WARN: no org_id for slug '{l['org_slug']}'")
                continue
            await cur.execute(
                "SELECT id FROM opportunity_listings WHERE org_id=%s AND title=%s",
                (org_id, l["title"]),
            )
            if await cur.fetchone():
                skipped += 1
                continue
            await cur.execute(
                """INSERT INTO opportunity_listings
                     (org_id, title, description, listing_type,
                      required_skills, required_arts,
                      is_active, scavenged, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s, 1, 0, NOW())""",
                (org_id, l["title"], l["description"], l["listing_type"],
                 json.dumps([]), json.dumps(l["required_arts"])),
            )
            seeded += 1
            print(f"  + listing  {l['title']}")
        await conn.commit()
    print(f"\n  Done: {seeded} listings seeded, {skipped} already existed.")


async def main():
    print("\nFreqLearn — seeding organizations and listings")
    print(f"DB: {DB['user']}@{DB['host']}/{DB['db']}\n")

    conn = await aiomysql.connect(**DB)
    try:
        print("Seeding organizations...")
        org_id_map = await seed_orgs(conn)
        print(f"\nSeeding listings...")
        await seed_listings(conn, org_id_map)
    finally:
        conn.close()

    print("\nRun `sudo systemctl status freqlearn` to confirm the API is healthy.")


if __name__ == "__main__":
    asyncio.run(main())
