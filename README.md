# LMBoK — Surfing the Frequencies

**A free, lifelong learning platform for making a quality life accessible to everyone.**

LMBoK (Life Management Body of Knowledge, also known by its working name **ePangea**) is a forever-free, human-centered, open-source lifelong-learning framework. **FreqLearn** is its technical home — a learning platform built around a simple bet: that intrinsic motivation, autonomous thinking, and self-defined satisfaction can be nurtured at scale, for free, for anyone.

Live at [build.onehouse.top](https://build.onehouse.top).

## Two projects, one vision

**Learning & Growth — LMBoK (ePangea)**
Built around **15 human arts**, **48 learning domains**, and **6 developmental phases**, shaped by the learner's own bioregion. Two features carry this beyond individual study:
1. A **community matching tool** connecting real local challenges with learner progress — putting theory into practice, with real impact and meaning.
2. **Polis** — an Avaaz-like referenda, discussion, and voting section that can shape One 'Ouse's Blueprint.

→ [build.onehouse.top](https://build.onehouse.top)

**Collective & Civic — One 'Ouse (The Blueprint)**
A MediaWiki-like open dialogue where we design a blueprint for how we — all of us — want humanity to live together. Your own voice becomes your vote; nobody speaks on your behalf unless you choose that. Open to everyone, everywhere. If you — or someone you know — feels inadequate expressing yourself constructively in that kind of space, LMBoK was designed with exactly that struggle in mind: build the capacity there, bring your voice here.

→ [onehouse.top](https://onehouse.top)

**These are not two unrelated products.** LMBoK is where you grow the capacity to participate; One 'Ouse is where that participation actually shapes something. Polis is the intended bridge between the two — a learner's civic voice, earned through real learning, feeding directly into the Blueprint. This integration is a core piece of unfinished vision, not a someday nice-to-have — see Roadmap below.

## Philosophy

FreqLearn is built on **["The Arts to Be Human"](https://docs.google.com/document/d/1RFxrO_mzHjTjk5qAg09KZzXIgqBija5F/edit?usp=sharing&ouid=102217663626879191510&rtpof=true&sd=true)** — a framework organizing human development around:

- **15 universal arts**, grouped under three domains: *Being*, *Becoming*, and *Connecting*
- **48 learning domains**
- **6 developmental phases**: prenascent → nascent → child → adolescent → adult → elder

Rooted in permaculture ethics, Vygotsky's Zone of Proximal Development, self-reliance, and civic agency. The goal isn't credentials — it's a self-directed, AI-assisted path through your own development, at your own pace, in your own language.

## How it works

- Learners move through a **Socratic AI companion** (Warmup → Explore → Challenge → Reflect → Assess) across each art
- Progress is tracked through **avatar stages** (Seed → Sprout → Sapling → Grove → Forest → Ecosystem) based on XP and breadth of arts explored — no leaderboards, no streaks (this is intentional)
- Reaching **Grove** stage or higher unlocks **Polis**, the civic participation layer described above (referenda, proposals, threaded discussion), scoped by community, regional, or global reach
- **Orgs / Ekklesia** — organization accounts post real local challenges; learner progress is matched against them
- A **bioregion** feature roots each learner's experience in the actual ecological place they live, not a nation-state abstraction
- Learners can **contribute** bioregion portraits and other content back into the platform, subject to moderation

## Stack

- **Backend:** FastAPI (Python), MariaDB, async SQLAlchemy
- **Frontend:** vanilla JS SPA (no framework), nginx
- **AI:** Groq (primary) → Ollama (local fallback) → stored session library (final fallback via circuit breaker), all via `httpx` — no vendor SDKs
- **Infra:** DigitalOcean droplet, Certbot/nginx, fail2ban

## Project structure

    backend/
      ai_client.py             Provider-agnostic AI client (Groq / Ollama / library)
      circuit_breaker.py       In-memory AI failure breaker -> library fallback
      db.py                    Database connection/session setup
      engine.py                SQLAlchemy engine config
      mail.py                  Email sending (verification, notifications)
      main.py                  FastAPI app entrypoint
      models.py                SQLAlchemy models
      prior_session_context.py Builds learner continuity context for AI prompts
      utils.py                 Shared helpers (avatar stage computation, etc.)
      requirements.txt
      routes/
        admin.py              Admin panel API
        auth.py                Auth (login, register, tokens)
        bioregions.py          Bioregion profiles + learner-contributed portraits
        contribute.py          Learner content contribution + moderation
        generate.py            AI session generation (Groq -> Ollama -> library)
        groq_generate.py       Groq provider integration
        ollama_generate.py     Ollama provider integration
        learners.py            Learner profile + progress endpoints
        matching.py            Learner/org challenge matching algorithm
        orgs.py                Organization accounts
        peripatos.py           Save-to-Peripatos feature
        polis.py               Civic participation (Polis) -- see One 'Ouse integration in Roadmap
        progress.py            Progress tracking
        radar.py                Skill radar chart data
        reflections.py          Reflect-phase content
        sessions.py             Session CRUD
        skills.py               Skill/domain taxonomy
        weekly_report.py        Weekly summary generation

    frontend/
      index.html    Main SPA
      app.js        Main SPA logic
      app.css       Main SPA styles
      admin.html    Admin panel
      polis.html    Civic participation UI
      org.html      Organization/Ekklesia UI
      contribute.html  Learner contribution UI
      favicon.ico

    scripts/        DB migrations, seed data, diagnostics, and one-off fixes
                    (kept for history -- see commit log for context on each)

## Roadmap (high level -- see PROJECT_MASTER.md for the working backlog)

- **Polis ↔ One 'Ouse integration** -- the core unfinished piece of the vision above: Polis referenda/votes feeding directly into the One 'Ouse Blueprint, so civic participation earned through learning has a real destination. Not yet scoped.
- Security hardening ahead of wider public traffic (see PROJECT_MASTER.md)
- Bioregion page: map view alongside the existing portrait list
- Org-verified skills, email verification infrastructure, and other items tracked in PROJECT_MASTER.md

## Status

Actively developed, pre-1.0. Single maintainer ([@epangea](https://github.com/epangea)) building toward a full public release. Contributions are welcome via pull request — see `CODEOWNERS`. `main` is protected; all changes go through PR review.

## License

[AGPL-3.0](LICENSE) — chosen deliberately: if you run a modified version of this platform as a public service, your changes must be open too. This project exists to stay open.
