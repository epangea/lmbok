# Session & Companion Architecture

**Who this is for:** anyone incorporating this open-source code into their own community
or organization — or anyone on this project picking it back up after time away. It answers
one question: *how does a session actually get built, and how do the AI companions around
it actually behave?* `README.md` covers the project as a whole; `PHILOSOPHY.md` covers the
framework's *why*. This doc is the *how*, at the level of "here is every building block that
goes into the prompt, and here is exactly what each companion is and isn't allowed to do."

Everything below is a direct read of `backend/routes/generate.py` — the single file that
owns every AI call in the platform's learner-facing product (see `ai_client.py`'s own
header comment: "There is no other way to call an LLM in this project"). If this file and
the code ever disagree, the code is right — update this doc.

---

## 1. The five-phase session, and where it comes from

Every session a learner does — regardless of art, phase, or language — has the same shape,
generated in one call to `POST /api/generate/session`:

| Phase | What it is | Prompt instruction (paraphrased) |
|---|---|---|
| **Warmup** | Opens the learner's attention | "2–4 sentences... ask them to notice something," connecting to their existing experience |
| **Explore** | The core concept | "3–5 sentences... one vivid analogy or example" |
| **Challenge** | Something real to do | "Describe exactly what the learner will create or do... no single right answer" |
| **Reflect** | Opens rather than closes | "1–2 open questions... genuine introspection," connecting the session to the learner's life |
| **Assess** | Formative check, not a test | One question + 4 options, scored Developing/Proficient/Master — never framed as pass/fail |

This is the **universal learning cycle** the prompt itself names: *observe → connect → act →
reflect*. It's deliberately the same cycle for every one of the 15 Arts — the content
changes, the shape doesn't.

### The building blocks that assemble into one prompt

`generate_session()` builds the actual prompt to the model out of these pieces, in this
order. If you're extending the platform (a new art, a new phase, a new language), this is
the map of what you're plugging into:

1. **Core philosophy block** (static, same every call) — the platform's mission statement,
   its intellectual lineage (alternative-education thinkers, developmental psychologists,
   the reading list — see `PHILOSOPHY.md` for the full list), and the non-negotiables:
   formative not competitive assessment, errors as the learning path not failures, intrinsic
   over extrinsic motivation, the MKO (More Knowledgeable Other) framing. **Explicitly
   instructed to let these ideas "breathe naturally into sessions — never cite by name in
   learner-facing content."** A learner should feel Freire's dialogic spirit, never read
   "as Freire argued."
2. **`ART_LENS`** — a hand-written, precise definition of what each of the 15 arts actually
   *is*, sourced directly from "To Be Human." This exists because early seed content
   collapsed almost everything into a permaculture/land/ecology frame — permaculture
   legitimately belongs to Build/Grow/Consume/Live/Eat, and explicitly *not* to Move, Feel,
   Notice, Listen, Give, Receive, Understand, Respect, Express, or Collaborate. The prompt
   states this exclusion directly, because it's the single most common failure mode this
   generator has actually produced in practice.
3. **Phase-specific pedagogy** (`phase_guides`) — one block per developmental phase
   (Prenascent → Elder), each rewriting *who the session is actually for* and *how it should
   sound*. This is more than a reading-level knob: Prenascent and Nascent sessions are
   explicitly written **for the adult caregiver, not the child** — a phase-guide correction
   that exists because earlier content drifted into writing baby-activity content instead.
   Child-phase sessions have an explicit anti-pattern rule ("DO NOT default to 'draw a
   picture'") because that was the generator's own lazy default before the rule was added.
4. **Skill/domain context** — if the learner arrived via a specific skill (from the Mouseion
   skill map or a direct click), its `learning_domain` and `skill_type`
   (cognitive/affective/psychomotor) shape a `DOMAIN_GUIDANCE` line — e.g. psychomotor
   sessions are told explicitly to ground in the body, "theory should serve the doing, not
   replace it."
5. **Learner interests** — free text the learner has shared, woven in "where natural," never
   forced.
6. **Continuity block** (`prior_session_context.py`) — the learner's last 3 sessions for this
   (art, phase) combination, so a new session builds on prior work instead of repeating
   itself. Also where a companion-resolved "wrong answer was actually defensible" verdict
   (see §2.3) gets folded back in, so a future session's prompt knows *why* that was
   accepted, not just that it was.
7. **Bioregion context** — soft everywhere except the five land/ecology arts, where it's
   framed as essential shaping context.
8. **Language instruction** — when set, a hard requirement that every single field (title
   through every `assess_option`) is written in that language, no mixing.

The model returns strict JSON (title/warmup/explore/challenge/reflect/assess_question/
assess_options/assess_correct). The backend then **shuffles the four assess options** before
storing/serving them — language models reliably over-favor position B, so this is a
deliberate de-bias step, not cosmetic randomness.

### What happens when the AI is unavailable

Three-tier fallback, all governed by `ai_client.py`'s circuit breaker:
1. **Fresh generation** (the path above) — the default.
2. **Inline reuse** — admin-toggleable, off by default; serves a stored session verbatim
   (with options re-shuffled) when the breaker hasn't tripped but an admin wants to cut AI
   spend.
3. **Library mode** — after N consecutive AI failures, serves only from the stored session
   library for a configured TTL, no AI calls at all, auto-resetting once the TTL elapses.

This exists so a solo-maintained, free platform degrades gracefully under provider outage
rather than hard-failing for every learner mid-outage.

---

## 2. The companions — one shared philosophy, documented exceptions

There are **five** distinct AI-driven learner touchpoints in this codebase. Four are
conversational ("companions" in the product sense); one is silent. They share a philosophical
core but differ in role by design — the table below is the map, followed by what's actually
consistent and what's a **deliberate, documented** exception (as opposed to accidental
drift, which is the thing worth catching).

| # | Name | Endpoint | Learner-facing? | Core stance |
|---|---|---|---|---|
| 1 | **Socratic Companion** | `POST /generate/scaffold` (default path) | Yes, chat | Asks, doesn't tell — *except* for plain comprehension questions (see 2.1) |
| 2 | **Portfolio Companion** | `POST /generate/scaffold` (`phase_label:'Portfolio'`) | Yes, chat | Answers directly — deliberately **not** Socratic (see 2.2) |
| 3 | **Assess Companion** | `POST /generate/assess-companion` | Yes, chat | Socratic evaluation of the learner's own reasoning on a specific wrong pick (see 2.3) |
| 4 | **Profile Distiller** | `POST /generate/profile-update` | No — silent, background | Not a conversation at all — see 2.4 |
| 5 | **Guiding Star Distiller** | `POST /generate/guiding-star` | No — silent, background | Same category as #4 — see 2.4 |

### 2.1 — Socratic Companion (Mouseion / Challenge / Reflect)

The default companion a learner meets in free exploration, mid-challenge, or during
reflection. Its own self-description in the system prompt:

> "Your role is that of a More Knowledgeable Other (MKO) — not a teacher who delivers
> answers, but a companion who helps the learner find their own way through. You ask
> questions, not give answers."

**Fixed 2026-08-17 (2026.116):** that rule was being applied too broadly — a learner asking
*"what's a slow squat?"* (a comprehension question about the challenge's own wording) was
getting Socratic questions back instead of a plain answer, which isn't Socratic, it's just
unhelpful. The prompt now draws an explicit line:

- **Comprehension** ("what does this word/instruction mean") → answer plainly, 1–2 sentences,
  then hand back to the exercise.
- **Reflection** ("what did I notice / which felt right") → stay fully Socratic. This is the
  learner's own insight; it's the part worth them discovering themselves.

When it plainly defines a concrete physical/visual term, it can flag an **opt-in** media hint
(`[[MEDIA: term]]`, parsed server-side into a search term — never a URL the model controls).
The frontend renders this as two small external link chips ("🔍 See a photo" / "▶ Watch a
short video, opens externally") — nothing embeds or preloads, in keeping with the platform's
free-on-2G accessibility target. See `frontend/app.js::mediaHintChipsHTML`.

Also shared tone rules, unchanged: 2–4 sentence replies, never "great question," never
mentions permaculture/ecology outside Build/Grow/Consume, draws on the full breadth of human
knowledge, phase-aware (different guidance for Mouseion vs. Challenge vs. Reflect).

### 2.2 — Portfolio Companion (same endpoint, different mode)

Lives at the same `/scaffold` endpoint but branches on `phase_label == 'Portfolio'` into a
**completely different role**, by explicit design:

> "You are not a Socratic guide — you are a reflective mirror... You speak directly, warmly,
> and honestly. You answer questions."

This is the one place in the platform where "just answer the question" is correct, not a
bug — the learner has come to see themselves reflected in their own accumulated profile, and
withholding that with Socratic questions would be a non-sequitur (there's no "answer" to
discover; the data just *is* what it is). **This is the model other companions should be
checked against when in doubt: is the learner asking to discover something about themselves,
or asking to see something that already exists?** The former stays Socratic; the latter
doesn't.

### 2.3 — Assess Companion (P40)

Fires only when a learner picks an assess option the answer key marks as not-best. Unlike
the others, it returns **structured JSON** (`{reply, resolved, score_update}`), not plain
text — because it has actual scoring authority: it can silently raise the learner's real
`assess_score` if their reasoning holds up, or if it genuinely agrees more than one option
was defensible (the AI-generated distractors often contain real partial truth). Shared DNA
with the Socratic Companion — warm, 2–4 sentences, assume good faith, never "great question,"
never make the learner feel incapable — but its Socratic questioning is aimed at a narrower
target: *why did you pick this, does that reasoning hold up*, not open exploration.

**Closed 2026-08-17 (2026.117), same session this doc was first written.** This companion
now has the same carve-out as 2.1: if a learner is asking what a *word* in the question or
options means, not defending their reasoning, that's comprehension — answer it directly in
1–2 sentences, then return to evaluating whether their reasoning holds up. Plumbed
differently than 2.1 (this endpoint already returns structured JSON, so `media_hint` is just
a fourth key in that schema rather than a text marker parsed out of plain text) but the same
principle, and the frontend reuses 2.1's `mediaHintChipsHTML()` rather than duplicating it.

### 2.4 — Profile Distiller & Guiding Star Distiller

Not companions in the conversational sense — no chat UI, no back-and-forth, nothing Socratic
to be consistent *about*. Two silent background jobs:

- **Profile Distiller** (`/profile-update`) reads a just-finished companion conversation and
  merges new signals into the learner's persistent "life-CV" (curiosities, practices, fears,
  recurring themes — capped at 1500 characters, distilled not appended). Fires automatically
  every 4 exchanges in a companion thread, or once a session ends.
- **Guiding Star Distiller** (`/guiding-star`) reads that life-CV and compresses it into one
  short phrase (4–9 words) shown in the learner's "Where I Stand" card — deliberately poetic
  and specific, with explicit bad-example guardrails against generic output like "keep
  learning."

These don't need tone consistency with the chat companions because the learner never sees
the prompt or the process — only the output artifacts (their profile, their Guiding Star).
What matters here is *accuracy* (don't invent things not grounded in the profile) rather
than *stance* (Socratic vs. direct).

---

## 3. What's actually shared across every companion (the real consistency check)

Independent of Socratic-or-not, every companion prompt in this file enforces the same
underlying commitments — this is the part that should **never** drift between companions,
regardless of how their specific role differs:

- **Never shame, never rank.** Assessment language is Developing/Proficient/Master, never
  pass/fail; the Assess Companion exists specifically to *replace* a red "wrong" flag with a
  discussion, because (Charbel's own words, filed verbatim in the project record) "the last
  thing we want is for the error to deflate the learner."
- **Assume good faith first.** Ask *why* before judging, in both the default Socratic
  Companion and the Assess Companion.
- **Never hollow-affirm.** "Great question" is explicitly banned in every conversational
  companion's prompt — a small rule, repeated deliberately in each one rather than assumed.
- **Short replies.** 2–4 sentences is the ceiling across every chat companion (Portfolio
  companion excepted — see 2.2 — where "3–5 sentences" is allowed because directness is the
  point there).
- **The MKO frame, not an authority frame.** Even the Portfolio Companion, which answers
  directly, is instructed to speak "as a thoughtful companion who has read their story
  carefully" — not as an evaluator.
- **No fabrication.** Every companion is told not to invent what isn't there — the Portfolio
  Companion explicitly ("never invent things not grounded in the profile"), the Assess
  Companion implicitly (it argues from the actual question/options given, never a different
  question).

**When extending or forking this platform:** if you add a new AI touchpoint, the fast
consistency check is simply — *does it uphold all six of the above, and if it deviates from
"ask, don't tell," is that deviation as deliberately reasoned and documented as the Portfolio
Companion's is in §2.2?* An undocumented exception is drift; a documented one (with a reason,
in writing, in this file) is a design decision.

---

## 4. Quick reference

| Building block | Lives in | Feeds |
|---|---|---|
| Core philosophy block, `ART_LENS`, `phase_guides`, `DOMAIN_GUIDANCE` | `backend/routes/generate.py` (`generate_session`) | `/session` prompt |
| Full "Arts to Be Human" framework detail | `PHILOSOPHY.md` | Human-readable reference; source of truth the prompt blocks above are derived from |
| Continuity block (last 3 sessions) | `backend/prior_session_context.py` | `/session` prompt, appended |
| Circuit breaker / library fallback | `backend/circuit_breaker.py`, `_select_reusable_pool()` / `_serve_from_library()` in `generate.py` | `/session`, pre-generation |
| Default Socratic Companion + Portfolio Companion prompts | `generate.py::scaffold_companion` | `/scaffold` |
| Opt-in media hint parsing (`[[MEDIA: term]]`) | `generate.py::scaffold_companion` | `ScaffoldResponse.media_hint` → `frontend/app.js::mediaHintChipsHTML` |
| Assess Companion prompt + scoring | `generate.py::assess_companion` | `/assess-companion` |
| Profile Distiller prompt | `generate.py::update_learner_profile` | `/profile-update` |
| Guiding Star Distiller prompt | `generate.py::generate_guiding_star` | `/guiding-star` |
| All provider routing/fallback (Groq → Ollama → Gemini → library) | `backend/ai_client.py` | Every call above |

---

*Last written 2026-08-17, from a direct read of `backend/routes/generate.py` at that
commit — not from memory or an earlier summary. If the code has since changed and this
doc hasn't, the code wins; please open a PR updating this file rather than trusting it
as-is.*
