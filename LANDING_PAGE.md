# LMBoK Landing Page — Editing & Integration Guide

`frontend/index.html` is the public marketing/landing page, served at `/`. The
actual learner app (formerly `index.html`) lives at `frontend/app.html` +
`app.js`, served at `/app.html`. This split happened before this doc existed
in the repo — this file documents how it works and how to edit it, current
as of 2026-07-19.

---

## How the landing page + app connect

```
User visits build.onehouse.top/            → index.html (the landing page)
  If logged in AND not arriving via Home    → auto-redirect to /app.html
  Clicks "Join Free"                        → /app.html#register (opens sign-up form)
  Clicks "Sign In"                          → /app.html#login    (opens sign-in form)

User visits build.onehouse.top/app.html
  Reads location.hash on load               → sets authMode = 'register' or 'login'
  Clears hash from URL bar                  → history.replaceState(null, '', '/app.html')
  Clicking "🏠 Home" (in the footer, every view) → /?src=nav
```

### The logged-in-visitor redirect, and why it's not just an `if`

`index.html` auto-redirects a logged-in visitor straight to `/app.html` — a
convenience for anyone hitting the bare root URL while already signed in
(e.g. a bookmark). But that convenience conflicts with someone who
**deliberately** wants to browse the landing page while logged in (via the
in-app Home link) — without this, clicking Home just bounces you straight
back to the app.

Two signals work together to resolve this:

- **`?src=nav`** on the URL — set by every in-app Home link. Checked on
  load; if present, skip the auto-redirect. Stripped from the visible URL
  right after landing (`history.replaceState`), for a clean address bar.
- **`sessionStorage['lmbok_home_visit']`** — set the moment `?src=nav` is
  seen, checked on every subsequent load in the same tab. This is what
  makes a **refresh** of the landing page not bounce you back into the app
  — the query param alone doesn't survive a reload once it's been stripped,
  so the session flag is the thing that actually persists the "I'm
  deliberately browsing home" state.
- `app.js`'s `boot()` clears the session flag once you're back in the app,
  so a later fresh visit to `/` (new tab, a bookmark) still gets the normal
  auto-redirect.

**If you add a new link back to the landing page anywhere** (a new page, a
new button), it must point to `/?src=nav`, never bare `/` — otherwise a
logged-in learner clicking it will just get bounced straight back.

### Logged-in visitor CTAs

If a logged-in learner does end up viewing the landing page (via Home),
"Sign In" / "Join Free" don't make sense for them. `index.html`'s bottom
script checks `localStorage['fl_learner']` (the same display-info cache
`app.js` uses, not real auth — see PROJECT_MASTER PART 6/4) and swaps all
three CTA pairs (top nav, hero, final band) for a single **"LMBoK Agora →"**
link to `/app.html`.

### The Home link itself

Every in-app view links back to the landing page via `/?src=nav`:
- The learner app (`app.js`'s `Footer()`) — present on *every* view,
  including the login/register screens (which skip the main nav entirely).
- `org.html` — the unauthenticated gate screen, the learner-app view (`AL`),
  and the org dashboard (`AO`).
- `polis.html`, `contribute.html`.

Separately, `org.html`/`polis.html`/`contribute.html` also have "← Agora"
links that predate the landing-page split (from when `/` *was* the app) —
those point straight at `/app.html`, not `/`, since their job is "go back
into the app," not "go to the marketing page."

---

## How to edit body text

### The golden rule
Every piece of text on the page lives in **two places**:
1. In the **HTML body** (the default/English content shown on first load).
2. In the **`T` object** inside the `<script>` tag (used by the multilingual engine).

**If you only change the HTML body, the multilingual engine will overwrite it** when the page loads (because it re-applies the English strings from `T` on init). You must update *both* places.

### Step-by-step: editing text

1. **Open `frontend/index.html`** in any text editor.
2. **Find the HTML element** you want to change. Every translatable element has a `data-i18n="KEY"` attribute, e.g.:
   ```html
   <p data-i18n="author_bio3">
     Charbel is a convinced believer...
   </p>
   ```
3. **Note the key** — in this case `author_bio3`.
4. **Search for that key in the `T` object** (inside the `<script>` block). You'll find it in every language block (`en`, `fr`, `es`, `de`, `ru`, `vi`, `zh`, `ar`).
5. **Update the English value first** (in the `en:` block).
6. **Update the HTML body** to match — this controls what visitors see before any JS runs, and what search engines index.
7. **Update the other language blocks** if you have translations. Leaving them as-is means non-English users will still see the old text — fine temporarily.

### Keys reference

| Key | Location | Notes |
|-----|----------|-------|
| `hero_tagline` | Hero section | Tagline below the title |
| `platform_intro` | Platform section | Opening paragraph |
| `card1_body` – `card4_body` | Platform cards | Feature card descriptions |
| `being_body`, `becoming_body`, `connecting_body` | 3 Arts section | Art card paragraphs |
| `avatar_body` | Avatar section | Journey description |
| `music_intro` | SoundCloud section | Paragraph above the player |
| `author_bio1` – `author_bio3` | Author section | Bio paragraphs |
| `dq_text` | Author section | The driving question |
| `cta_body` | Final CTA band | Paragraph above the button |

### Elements that are NOT translated (safe to edit HTML-only)

- The author photo (`<img src="charb.jpg" ...>`)
- The SoundCloud `<iframe>` embed
- The YouTube video placeholders
- The footer copyright line (`footer_bottom` class)
- All external links (`href="..."`)

---

## Updating YouTube video IDs

1. Open `frontend/index.html` in a text editor.
2. Search for `YOUTUBE_VIDEO_ID_1`, `YOUTUBE_VIDEO_ID_2`, `YOUTUBE_VIDEO_ID_3`.
3. Replace each placeholder with the real 11-character YouTube video ID (from the URL after `?v=`).

The click-to-load iframe is handled automatically.

Three videos planned:
1. **Video 01** — The Call to Action: why LMBoK exists
2. **Video 02** — The 3 Arts: Being, Becoming, Connecting
3. **Video 03** — From Factories to Open Fields (status quo vs. vision)

## SoundCloud start track

The embed starts at `start_track=N` (0-based index: 0 = first track, 1 = second, etc.) — search `index.html` for `start_track=` to change it.

## Adding a new language

1. Duplicate the last language block inside `const T = { ... }` in the `<script>` tag.
2. Translate all string values.
3. Add a `<div class="lang-option" onclick="setLang('xx','🏳️','Language name')">Language name</div>` entry inside the `#langDropdown` div in the HTML body.

## Deploying changes

Same sequence as the rest of the frontend (see MAINTENANCE.md, local-only):
Claude/you edit files → sftp to the server → run `scripts/smoke.sh` → **then** commit/push. `frontend/index.html` and `frontend/app.js` are both plain static files — no backend restart needed for either.
