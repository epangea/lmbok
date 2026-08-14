# Philosophy & Framework

LMBoK is built on **["The Arts to Be Human"](https://docs.google.com/document/d/1RFxrO_mzHjTjk5qAg09KZzXIgqBija5F/edit?usp=sharing&ouid=102217663626879191510&rtpof=true&sd=true)** (Charbel Haddad) — the source document for everything below. The influences and reading list further down are drawn from that document's own "Essential Reading" appendix, plus its companion compilation, **[The Alternative Education Master Compendium](https://docs.google.com/document/d/1JR87TBF1IqxzCPks-s3QtUYdXJGGt3GkV1yR-mu7bCQ/edit?usp=sharing)** — an AI-generated summary of the classic alternative-education thinkers and developmental psychologists listed below and their specific contributions. See `README.md` for the project overview; this doc goes one level deeper into the framework itself.

> "Can we identify some universal arts and values that can empower everyone to be their very own best in their own contextual ways?"

## The 15 Arts

### Being (inward awareness)
| # | Art | Core idea |
|---|-----|-----------|
| 1 | Move | inner-connectedness, physical growth |
| 2 | Eat | outer-connectedness, microbiome/nourishment |
| 3 | Feel | inward-awareness, personal growth, emotional growth |
| 4 | Notice | outward-awareness without judgement, exploration, discovery |
| 5 | Express | inward-outward clarity, creative growth, arts, self-determination |

### Becoming (outward awareness)
| # | Art | Core idea |
|---|-----|-----------|
| 6 | Live | personal needs, rights, civil duties, footprint |
| 7 | Listen | empathy, civil discourse, understanding |
| 8 | Give | compassion, care, selfless contribution |
| 9 | Receive | acceptance, humility, equity |
| 10 | Collaborate | shared vision, inclusivity, synergy |

### Connecting (with environments)
| # | Art | Core idea |
|---|-----|-----------|
| 11 | Understand | first principles, science, theory of knowledge |
| 12 | Respect | golden rule extended to all living things, mindful pragmatic utilitarianism |
| 13 | Build | bioconstruction, green design, accessibility |
| 14 | Grow | regenerative agriculture, food sovereignty |
| 15 | Consume | water, resource and energy stewardship |

## The 6 developmental phases

1. **Prenascent** (Mother/Parent) — the caregiver's own developmental stage, since a child's environment starts there
2. **Nascent/Infant** (0~3)
3. **Child** (3~11)
4. **Adolescent**
5. **Adult**
6. **Elder**

*(Corrected 2026-08-13 — earlier internal notes had dropped Nascent/Infant and listed only 5. Confirmed against "The Arts to Be Human," Tables 1-3.)*

## Learning domains

The framework's own top-level domain list — not a fixed count, but this is what's actually named in the source document:

Human · Physiology · Psychology · Medicine & Healthcare · Environmental Biology · Chemistry · Physics · Engineering · Mathematics · Literature & Language · Visual Art & Expression · History & Journalism · Public Policy & Law · Happiness & Finance

*(Corrected 2026-08-13 — earlier internal notes cited "48 learning domains," a figure that doesn't appear anywhere in the source document. This is the actual list.)*

## The Mouseion Skill Map — 8 domains × 6 skills

A separate, deliberately simpler and more backward-intuitive taxonomy from the 14 learning domains above — this is what actually drives the Mouseion UI (`frontend/app.js`, `Mouseion()`), acting as a universal library learners browse directly to find topics/skills they relate to, each domain anchored to one of the 15 arts as its primary art. Confirmed 2026-08-14 by reading `_DOMS` in `app.js` directly — no guessing. (This is very likely also where an old, incorrect "48 learning domains" figure came from: 8 domains × 6 skills = 48 skills, not domains — a mix-up between two different structures, now resolved.)

| Domain | Primary art | Skills |
|---|---|---|
| 🧠 Cognitive & Intellectual | Understand | Critical Thinking · Problem Solving · Systems Thinking · Memory & Retention · Decision Making · Project Management |
| 🎨 Creative & Artistic | Express | Visual Art · Music & Rhythm · Creative Writing · Drama & Theatre · Improvisation & Public Speaking · Craftsmanship & Making |
| 🌿 Physical & Motor | Move | Gross Motor · Fine Motor · Physical Fitness · Dance & Movement · Body Awareness · First Aid & Nursing |
| 🤝 Social & Relational | Collaborate | Collaboration · Conflict Resolution · Empathetic Leadership · Negotiation · Cultural Competence · Parenting & Caregiving |
| 💬 Language & Communication | Listen | Active Reading · Active Listening · Storytelling · Debate & Argumentation · Foreign Language Acquisition · Rhetoric & Persuasion |
| 💙 Emotional & Psychological | Feel | Self-Awareness · Emotional Regulation · Empathy and Compassion · Self-Efficacy · Contemplative Practice · Gratitude & Appreciation |
| ✦ Meta-Learning | Notice | Learning How to Learn · Self-Regulation · Personal Values · Curiosity and Exploration · Vision, Mission and Purpose · Mentorship & Teaching |
| ⚙️ Tools & Systems | Understand | Digital Literacy · Data Analysis & Statistics · Design Thinking · Philosophy & Ethics · Permaculture · Cooking & Nutrition |

## The LECKO concept

Every learning chunk in LMBoK is a **Learning Experience Knowledge Chunk Object**, structured as:
- Art(s) it develops (from the 15 above)
- Developmental phase (from the 6 above)
- Learning domain(s) (from the list above)
- Core/secondary skills (cognitive, affective, psychomotor)
- Assessment type & methodology
- Community need alignment

## Anti-patterns we deliberately avoid

- No standardized tests · No fear of mistakes · No competition-based ranking
- No surveillance or manipulation · No ego-driven teaching
- Anti-gamification in the UI — no day-streak display, no leaderboards
- Growth for growth's sake, decoupled from human wellbeing — rejected as a design goal

## Essential reading

*(Replaces an earlier, much shorter "Key Influences" list that had cherry-picked four titles somewhat arbitrarily. This is the actual reading list from "The Arts to Be Human," Appendix 1b, reproduced in full rather than editorialized — no single title here is meant to stand above the others.)*

**Cognition (and meta-everything), psychomotor & affective domains** — communication, intrinsic motivation, self-regulation, self-efficacy, how to learn/develop:
The Science of Rapid Skill Acquisition (2018) Peter Hollins · Peak (2016) K. Anders Ericsson & Robert Pool · The Whole-Brain Child (2011) Daniel Siegel & Tina Bryson · The Power of Play (2007) / The Hurried Child (1981) David Elkind · Productive Failure (2023) Manu Kapur · Uncommon Sense Teaching (2021) / Learn Like a Pro (2021) Barbara Oakley et al. · Mastery (2025) Tony Wagner & Ulrik Christensen · Mastery (2012) Robert Greene · Micromastery (2017) Robert Twigger · Beginners (2021) Tom Vanderbilt · Out of Our Minds (2001) Ken Robinson · Artificial Intelligence for Learning (2024) Donald Clark · When AI Tutors Fake Critical Thinking (2026) R.J. Purdy & T. Cook · Critical Thinking (2020) R. Paul & L. Elder · Thinking 101 (2022) Woo-Kyoung Ahn · The Art of Logic (2018) Eugenia Cheng · Shape (2021) Jordan Ellenberg · Robin Hood Math (2025) Noah Giansiracusa · Everything is Obvious (2011) Duncan J. Watts · The Beginning of Infinity (2011) David Deutsch · A Brief History of Thought (1996) Luc Ferry · Conscious (2019) Annaka Harris · The Shape of Wonder (2025) Alan Lightman & Martin Rees · Why We Do What We Do (1995) Edward Deci & Richard Flaste · Wisdom Takes Work (2025) Ryan Holiday · Awaken Your Genius (2023) Ozan Varol · Self-Compassion (2011) Kristin Neff · Brain Wash (2020) David Perlmutter et al. · Sleep Drink Breathe (2024) Michael Breus · Breath (2020) James Nestor · The Developing Mind (1999) Daniel J. Siegel · Adventures in Human Being (2015) Gavin Francis · Thinking Fast and Slow (2012) Daniel Kahneman · Principles (2017) Ray Dalio · Process! (2022) Mike Paton & Lisa Gonzalez · The Algorithm (2026) Jon McNeill · Uncompete (2025) Ruchika Malhotra · Lucky by Design (2025) Judd Kessler · Traffic (2008) Tom Vanderbilt · The Genius Myth (2025) Helen Lewis · Toxic Positivity (2022) Whitney Goodman · Shared Wisdom (2025) Alex Pentland · The Genius of Empathy (2024) Judith Orloff · The Art of Insubordination (2022) Todd Kashdan · Ethics of Ambiguity (1947) Simone de Beauvoir · Every Living Thing (2024) Jason Roberts · How to Raise Successful People (2019) Esther Wojcicki · Win Every Argument (2023) Mehdi Hasan · How to Listen (2022) Oscar Trimboli · Good Writing (2026) Neal Allen & Anne Lamott · Presence (2016) Amy Cuddy · The Compass Within (2025) Robert Glazer · Liminal Thinking (2016) Dave Gray

Plus **oral communication** as taught by Vinh Giang (not a book — his lessons on developing confidence through clear, present self-expression).

**Systems, politics & collaboration:**
Talking to My Daughter about the Economy (2018) Yanis Varoufakis · Moral Tribes (2013) Joshua Greene · How to Be an Anticapitalist in the 21st Century (2019) Erik Olin Wright · How Countries Go Broke (2025) Ray Dalio · Profit Over People (1999) / Manufacturing Consent (1988) Noam Chomsky et al. · Travel as a Political Act (2009, 2018) Rick Steves · Junglekeeper (2026) Paul Rosolie · The Story of Stories (2026) Kevin Ashton · Careless People (2025) Sarah Wynn-Williams · Collective Illusions (2022) Todd Rose · The Almightier (2025) Paul Vigna · Mutiny! (2026) Noam Scheiber · Salt (2002) Mark Kurlansky — and the classic texts on political philosophy: Plato's Dialogues and The Republic (~400 BC) · On Liberty (1859) J.S. Mill (the harm principle, contrasted with Feinberg's offense principle) · Groundwork of the Metaphysics of Morals (1785) / Critique of Pure Reason (1781) Immanuel Kant (categorical imperative; reason vs. freedom vs. nature vs. will vs. theology) · The 48 Laws of Power (1998) Robert Greene (describes the greed-driven system this project pushes back against)

**Inspirational:**
What to Make of a Life (2026) Jim Collins, plus biographies local to a given region to leverage familiarity and connection — e.g. Edison (2019) Edmund Morris for Westerners, showing Alva as a home-schooled boy dismissed by his teachers who became "the most famous inventor in history."

### Classic alternative education thinkers
Maria Montessori · Rudolf Steiner (Waldorf) · John Dewey (experiential reflection) · Paulo Freire (critical pedagogy) · Célestin Freinet (cooperative work) · A.S. Neill (Summerhill) · Loris Malaguzzi (Reggio Emilia) · Carl Rogers (student-centered learning) · Ken Robinson (authentic curriculum) · John Taylor Gatto (homeschooling) · Yaacov Hecht (IDEC) · David Sobel (forest school)

### Classic developmental psychologists
Jean Piaget · Lev Vygotsky · Erik Erikson · Friedrich Fröbel · Lawrence Kohlberg · Abraham Maslow · Jerome Bruner · Emmi Pikler · Margaret Mead · Howard Gardner · Daniel Goleman

Full detail on each figure's specific contribution: **[The Alternative Education Master Compendium](https://docs.google.com/document/d/1JR87TBF1IqxzCPks-s3QtUYdXJGGt3GkV1yR-mu7bCQ/edit?usp=sharing)**.
