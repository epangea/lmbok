// ============================================================
// Surfing the Frequencies — app.js
// Complete frontend application logic
//
// SECTIONS:
// 1.  Sound System      — Web Audio API, no external files
// 2.  API Client        — All fetch calls to FastAPI backend
// 3.  State             — Single source of truth
// 4.  Radar Graph       — SVG triangle renderer
// 5.  Auth Pages        — Login and registration
// 6.  Navigation        — Nav bar
// 7.  Dashboard/Agora   — Main learner home
// 8.  Session/Academy   — 5-phase learning session
// 9.  Mouseion          — Skill map
// 10. Peripatos         — Reflection space
// 11. Handlers          — All user interaction handlers
// 12. Onboarding        — 5-screen new user flow
// 13. Render            — Main draw() function and boot
//
// Architecture notes:
//   - No framework — vanilla JS for maximum compatibility (Tier 2/3)
//   - State managed in single S object, draw() rerenders on change
//   - API calls return promises; errors logged but never crash the UI
//   - Sound system degrades gracefully if browser blocks audio
//   - All sessions stored in MariaDB before being served to learner
// ============================================================

'use strict';



// ══════════════════════════════════════════════════
// SOUND SYSTEM
// Web Audio API — no external files needed
// Gracefully disabled if browser blocks autoplay
// ══════════════════════════════════════════════════
var SND = {
  ctx: null,
  muted: localStorage.getItem('fl_muted') === '1',

  init: function() {
    if (SND.ctx) return;
    try {
      SND.ctx = new (window.AudioContext || window.webkitAudioContext)();
    } catch(e) { console.log('Audio not available'); }
  },

  // Core tone generator
  tone: function(freq, type, duration, vol, fadeOut) {
    if (SND.muted || !SND.ctx) return;
    try {
      var osc  = SND.ctx.createOscillator();
      var gain = SND.ctx.createGain();
      osc.connect(gain);
      gain.connect(SND.ctx.destination);
      osc.type = type || 'sine';
      osc.frequency.setValueAtTime(freq, SND.ctx.currentTime);
      gain.gain.setValueAtTime(vol || 0.12, SND.ctx.currentTime);
      if (fadeOut !== false) {
        gain.gain.exponentialRampToValueAtTime(0.001, SND.ctx.currentTime + duration);
      }
      osc.start(SND.ctx.currentTime);
      osc.stop(SND.ctx.currentTime + duration);
    } catch(e) {}
  },

  // Chord: play multiple tones together
  chord: function(freqs, type, duration, vol) {
    freqs.forEach(function(f) { SND.tone(f, type, duration, (vol||0.08)/freqs.length); });
  },

  // ── Named sounds ─────────────────────────────────
  // Session start — rising wave
  sessionStart: function() {
    SND.init();
    setTimeout(function(){ SND.tone(220, 'sine', 0.4, 0.08); }, 0);
    setTimeout(function(){ SND.tone(330, 'sine', 0.4, 0.08); }, 120);
    setTimeout(function(){ SND.tone(440, 'sine', 0.6, 0.10); }, 240);
    setTimeout(function(){ SND.chord([440,550,660], 'sine', 0.8, 0.12); }, 400);
  },

  // Phase complete — soft chime
  phaseComplete: function() {
    SND.init();
    SND.chord([528, 660], 'sine', 0.5, 0.10);
    setTimeout(function(){ SND.tone(792, 'sine', 0.4, 0.07); }, 150);
  },

  // Correct answer — warm affirmation
  correct: function() {
    SND.init();
    SND.tone(523, 'sine', 0.15, 0.08);
    setTimeout(function(){ SND.tone(659, 'sine', 0.15, 0.08); }, 100);
    setTimeout(function(){ SND.tone(784, 'sine', 0.35, 0.10); }, 200);
  },

  // Wrong answer — gentle nudge, not punishing
  wrong: function() {
    SND.init();
    SND.tone(300, 'sine', 0.15, 0.06);
    setTimeout(function(){ SND.tone(260, 'sine', 0.3, 0.06); }, 120);
  },

  // Session complete — resonant resolution
  sessionComplete: function() {
    SND.init();
    setTimeout(function(){ SND.chord([261,329,392], 'sine', 0.3, 0.08); }, 0);
    setTimeout(function(){ SND.chord([329,415,494], 'sine', 0.3, 0.08); }, 200);
    setTimeout(function(){ SND.chord([392,494,587], 'sine', 0.3, 0.09); }, 400);
    setTimeout(function(){ SND.chord([523,659,784,1047], 'sine', 1.2, 0.10); }, 650);
  },

  // Onboard step — gentle progress
  step: function() {
    SND.init();
    SND.tone(440, 'sine', 0.2, 0.07);
    setTimeout(function(){ SND.tone(554, 'sine', 0.25, 0.07); }, 100);
  },

  // UI click — subtle tap
  tap: function() {
    SND.init();
    SND.tone(800, 'sine', 0.06, 0.04);
  },

  toggle: function() {
    SND.muted = !SND.muted;
    localStorage.setItem('fl_muted', SND.muted ? '1' : '0');
    set({});  // redraw to update mute button
  },
};

// ══════════════════════════════════════════════════
// API CLIENT
// Talks to FastAPI backend at /api/*
// ══════════════════════════════════════════════════
// Reads a non-httpOnly cookie by name (used only for the CSRF double-submit
// token — fl_access/fl_refresh are httpOnly and never visible to JS, by
// design, since P-SEC1 2026-07-16).
function getCookie(name) {
  const m = document.cookie.match('(?:^|; )' + name + '=([^;]*)');
  return m ? decodeURIComponent(m[1]) : null;
}

const API = {
  base: '/api',

  async req(method, path, body, isRetry) {
    const opts = {
      method,
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
    };
    if (method !== 'GET' && method !== 'HEAD') {
      const csrf = getCookie('fl_csrf');
      if (csrf) opts.headers['X-CSRF-Token'] = csrf;
    }
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(API.base + path, opts);
    if (res.status === 401 && !isRetry && API.isLoggedIn()) {
      // Access cookie expired — try a silent refresh (cookie-based, no body
      // needed) then retry once.
      try {
        const rr = await fetch('/api/auth/refresh', {
          method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
        });
        if (rr.ok) {
          return API.req(method, path, body, true);  // retry once now that cookies are refreshed
        }
      } catch(e) { /* fall through to logout */ }
      // Can't refresh — log out
      API.logout();
      set({view:'login', authError:'Your session expired — please sign in again', learner:null});
      throw new Error('Session expired');
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'HTTP ' + res.status);
    }
    return res.json();
  },

  get:    (path)       => API.req('GET',    path),
  post:   (path, body) => API.req('POST',   path, body),
  patch:  (path, body) => API.req('PATCH',  path, body),
  delete: (path)       => API.req('DELETE', path),

  async register(username, email, password, display_name, birth_year) {
    // Server sets fl_access/fl_refresh/fl_csrf as httpOnly (resp. readable)
    // cookies directly on this response — nothing token-related to store here.
    const data = await API.post('/auth/register', { username, email, password, display_name, birth_year });
    localStorage.setItem('fl_learner', JSON.stringify({ id: data.learner_id, display_name: data.display_name, onboarding_complete: false }));
    return data;
  },

  async login(email, password) {
    const data = await API.post('/auth/login', { email, password });
    localStorage.setItem('fl_learner', JSON.stringify({ id: data.learner_id, display_name: data.display_name, onboarding_complete: !!data.onboarding_complete }));
    return data;
  },

  logout() {
    API.post('/auth/logout').catch(() => {});
    localStorage.removeItem('fl_learner');
    localStorage.removeItem('fl_artScores');
    localStorage.removeItem('fl_dash_cache');
  },

  // fl_learner is just a display-info cache (id/name/onboarding flag), not a
  // credential — it's fine in localStorage. The actual session lives in the
  // httpOnly cookies and is validated server-side on every request.
  isLoggedIn() { return !!localStorage.getItem('fl_learner'); },
  getLearner() {
    try { return JSON.parse(localStorage.getItem('fl_learner') || 'null'); }
    catch { return null; }
  },
};

// ══════════════════════════════════════════════════
// STATE
// ══════════════════════════════════════════════════
// Restore last-known dashboard state so initial draw shows real data, not defaults.
// Updated on every successful loadDashboard(); cleared on logout.
const _dc = (function(){
  try {
    const raw = JSON.parse(localStorage.getItem('fl_dash_cache') || 'null');
    if (!raw) return null;
    // Invalidate todaySessions if cached on a different calendar day
    const today = new Date().toISOString().slice(0, 10);
    if (raw.cacheDate && raw.cacheDate !== today) {
      raw.todaySessions = null;
    }
    return raw;
  } catch(e) { return null; }
})();

const S = {
  view: API.isLoggedIn() ? (API.getLearner()?.onboarding_complete ? 'dashboard' : 'onboard') : 'login',
  authMode: (location.hash === '#register') ? 'register' : 'login',   // login | register
  authEmail: '',
  regName: '', regUsername: '', regEmail: '', regYear: '',
  onboardStep: 1,      // 1-5
  onboardName: '',
  onboardPhase: '',
  onboardArt: '',
  onboardFamiliarity: {},
  onboardColor: '#00E5C8',
  sessionLoading: false,
  activeSession: null,  // current session data from API
  sessionStartTime: null,
  assessSelectedIndex: null,   // 0-based index of the option the learner picked on the current session's assess; null if not yet answered (added 2026-07-07)
  mouseionThought: '',   // free-text context from Mouseion, woven into sessions
  skillContext: null,    // specific skill name to focus session on (set by startSkillSession)
  skillDomain:  null,    // learning_domain for current skill session (from SKILL_DOMAIN_META)
  skillType:    null,    // skill_type for current skill session (cognitive/affective/psychomotor)
  sandboxMessages: [],   // [{role,content}] current sandbox conversation thread
  sandboxLoading: false, // true while waiting for companion reply
  portfolioMessages: [], // [{role,content}] Portfolio companion thread — kept separate, never triggers profile update
  portfolioLoading: false,
  sandboxOpen: false,    // challenge/reflect companion panel open
  peripatosTab: 'write',          // 'write' | 'journal'
  peripatosEntries: null,         // null=not fetched | [] | [...]
  peripatosEntriesLoading: false,
  peripatosEntryOpen: null,       // {id,title,messages,created_at} when reading
  peripatosSaveStatus: null,      // null | 'saving' | 'saved' | 'error'
  learnerProfile: null,  // accumulated life-CV string (loaded from /learners/me)
  language:    localStorage.getItem('fl_lang') || 'en',
  stoaPrompt:   '',      // prompt used for current entry
  stoaEntries:  null,    // loaded reflection entries (null = not yet fetched)
  stoaSessionId: null,   // session_id to link if coming from Academy
  stoaSaving:   false,
  stoaSaved:    false,
  stoaError:    null,
  showPolisGate: false,
  sessionError: null,
  authError: '',
  authLoading: false,
  phase: 0,
  answered: false,
  challengeText: '',
  lite: false,
  // Live data — seeded from localStorage cache so initial draw shows real data,
  // then refreshed from API in loadDashboard().
  learner: API.getLearner(),
  streak:      _dc ? _dc.streak      : 0,
  level:       _dc ? _dc.level       : 1,
  xp:          _dc ? _dc.xp          : 0,
  xpMax: 100,
  weekMinutes: _dc ? _dc.weekMinutes : 0,
  nextRec:     _dc ? _dc.nextRec     : null,
  radar: (_dc && _dc.radar) ? _dc.radar : { being: 0, becoming: 0, connecting: 0 },
  todaySessions: (_dc && _dc.todaySessions) ? _dc.todaySessions : null,
  topMatch:    (_dc && _dc.topMatch)    ? _dc.topMatch    : null,
  skillsTouched: (_dc && _dc.skillsTouched != null) ? _dc.skillsTouched : null,
  arts: [],
  // artScores — restored from localStorage if available, populated/refreshed from API after login
  artScores: (function(){ try { return JSON.parse(localStorage.getItem('fl_artScores')||'{}'); } catch(e){ return {}; } })(),
  matchLoaded: _dc && _dc.topMatch ? true : false,   // true once /matching/listings/top resolves
  radarTab: 'avatar',   // 'avatar' (15-art) | 'domains' (8-domain)
  domainTab: 'arts', // 'arts' | 'domains'

  // ── Progress page ─────────────────────────────────────────────
  progressHistory:  null,  // [{id,title,art_name,art_slug,xp_earned,duration_seconds,phase_reached,completed_at}]
  progressActivity: null,  // [{date,sessions_done,xp_earned,minutes_spent}] — last 30 days
  progressLoading:  false,
  progressArt:      null,  // slug of expanded art in the skill breakdown, or null
  progressTab:      'chart', // 'chart' | 'history' | 'arts'

  // ── Bioregion page ────────────────────────────────────────────
  bioregionPortraits:     null,   // [{id, cluster_label, contributor_count, summary}]
  bioregionPortrait:      null,   // single expanded portrait with voices
  bioregionLoading:       false,
  bioregionContrib:       null,   // learner's own contribution {id, status, statement, ...}
  bioregionContribLoaded: false,
  bioregionForm:          false,  // show contribution form
  bioregionFormText:      '',
  bioregionFormName:      '',
  bioregionFormError:     '',
  bioregionFormSaving:    false,
  bioregionDraft:         null,   // null=not tried | false=checked,no draft | {…}=draft ready
  bioregionDraftLoading:  false,
  bioregionDraftAccepted: null,   // {summary,watershed,climate,species,vitality} booleans
  bioregionView:          'portraits', // 'portraits' | 'map' | 'table' | 'fieldguide'

};

function set(p) {
  // Trigger profile update when leaving the Mouseion sandbox
  if (p.view && p.view !== 'skills' && S.view === 'skills' && S.sandboxMessages && S.sandboxMessages.length >= 2) {
    triggerProfileUpdate();
    S.sandboxMessages = [];
  }
  // Clear portfolio companion thread when leaving Portfolio
  if (p.view && p.view !== 'portfolio' && S.view === 'portfolio') {
    S.portfolioMessages = [];
  }
  // Reset sandbox thread and open state when entering/leaving session phases
  if (p.phase !== undefined && p.phase !== S.phase) {
    S.sandboxOpen = false;
    // Reset sandbox messages between phases so each phase starts fresh
    S.sandboxMessages = [];
  }
  Object.assign(S, p);
  // ── Bioregion map: destroy when leaving map view or bioregion page
  if ((p.view && p.view !== 'bioregion') ||
      ('bioregionView' in p && p.bioregionView !== 'map')) {
    destroyBioMap();
  }
  if (p.language) applyLang();
  if (p.view === 'reflect' && S.stoaEntries === null) loadStoa();
  if (p.view === 'reflect' && S.reflectText && S.reflectText.trim() && !S.stoaText) {
    S.stoaText = S.reflectText;
    S.stoaSessionId = currentSession && currentSession.session_id || null;
  }
  if (p.view === 'portfolio' && S.progressHistory === null && !S.progressLoading) loadProgress();
  if ((p.peripatosTab === 'journal' || (p.view === 'reflect' && S.peripatosTab === 'journal')) && S.peripatosEntries === null && !S.peripatosEntriesLoading) loadPeripatosEntries();
  draw();
  // ── Bioregion map: init after draw() when map view is active
  if (S.view === 'bioregion' && S.bioregionView === 'map') {
    requestAnimationFrame(function() {
      if (S.bioregionPortraits && S.bioregionPortraits.length) initBioregionMap(S.bioregionPortraits);
    });
  }
  // ── Bioregion Field Guide: lazy-load seed profiles (reuses dashboard cache)
  if (S.view === 'bioregion' && S.bioregionView === 'fieldguide' && _loadedProfiles.length === 0) {
    loadBioregionProfiles();
  }
}

// ══════════════════════════════════════════════════
// FETCH DASHBOARD DATA
// ══════════════════════════════════════════════════
async function loadDashboard() {
  if (!API.isLoggedIn()) return;
  try {
    const [streakData, radarData, artsData, nextRec, todayData, skillsTouchedData] = await Promise.all([
      API.get('/learners/me/streak').catch(() => null),
      API.get('/radar/current').catch(() => null),
      API.get('/arts').catch(() => []),
      API.get('/sessions/next-recommendation').catch(() => null),
      API.get('/sessions/today').catch(() => null),
      API.get('/sessions/skills-touched').catch(() => null),
    ]);
    // Load top match separately (non-blocking — fails gracefully if no listings)
    API.get('/matching/listings/top').then(function(m) {
      set({topMatch: m || null, matchLoaded: true});
      try {
        const _prev = JSON.parse(localStorage.getItem('fl_dash_cache') || '{}');
        localStorage.setItem('fl_dash_cache', JSON.stringify(Object.assign({}, _prev, {topMatch: m || null})));
      } catch(e) {}
    }).catch(function() { set({matchLoaded: true}); });
    // Only add a key to updates when we actually received valid data.
    // If an API call 503'd (null), we leave S untouched so cached values persist.
    const updates = {};
    if (streakData) {
      updates.streak      = streakData.current_streak || 0;
      updates.xp          = streakData.total_xp || 0;
      updates.level       = Math.max(1, Math.floor((streakData.total_xp || 0) / 100) + 1);
      updates.weekMinutes = streakData.total_minutes || 0;
    }
    if (radarData && radarData.group_scores) {
      updates.radar = radarData.group_scores;
    }
    if (radarData && radarData.art_scores) {
      const _scores = radarData.art_scores;
      const _hasData = Object.keys(_scores).some(function(k){ return _scores[k] > 0; });
      if (_hasData) {
        updates.artScores = _scores;
        try { localStorage.setItem('fl_artScores', JSON.stringify(_scores)); } catch(e) {}
      }
    }
    if (artsData && artsData.length) {
      updates.arts = artsData;
    }
    if (nextRec) {
      updates.nextRec = nextRec;
    }
    if (todayData) {
      updates.todaySessions = todayData;
    }
    if (skillsTouchedData && skillsTouchedData.skills_touched != null) {
      updates.skillsTouched = skillsTouchedData.skills_touched;
    }
    set(updates);
    // Only update the cache when we received fresh data — never overwrite with nulls.
    // Merge new values into existing cache so partial responses don't erase good data.
    try {
      const _prev = JSON.parse(localStorage.getItem('fl_dash_cache') || '{}');
      const _next = Object.assign({}, _prev, {
        cacheDate:     new Date().toISOString().slice(0, 10),
        streak:        updates.streak        !== undefined ? updates.streak        : _prev.streak,
        xp:            updates.xp            !== undefined ? updates.xp            : _prev.xp,
        level:         updates.level         !== undefined ? updates.level         : _prev.level,
        weekMinutes:   updates.weekMinutes   !== undefined ? updates.weekMinutes   : _prev.weekMinutes,
        nextRec:       updates.nextRec       !== undefined ? updates.nextRec       : _prev.nextRec,
        radar:         updates.radar         !== undefined ? updates.radar         : _prev.radar,
        todaySessions: updates.todaySessions !== undefined ? updates.todaySessions : _prev.todaySessions,
        skillsTouched: updates.skillsTouched !== undefined ? updates.skillsTouched : _prev.skillsTouched,
      });
      localStorage.setItem('fl_dash_cache', JSON.stringify(_next));
    } catch(e) {}
  } catch(e) {
    console.log('Dashboard load:', e.message);
  }
}

// ══════════════════════════════════════════════════
// FETCH PROGRESS DATA
// Loads session history + activity log for Progress page.
// Triggered by set({view:'progress'}) if not yet loaded.
// ══════════════════════════════════════════════════
async function loadProgress() {
  if (!API.isLoggedIn()) return;
  set({progressLoading: true});
  try {
    const [history, activity] = await Promise.all([
      API.get('/sessions/history?limit=30').catch(() => null),
      API.get('/sessions/activity?days=30').catch(() => null),
    ]);
    set({
      progressHistory:  history  || [],
      progressActivity: activity || [],
      progressLoading:  false,
    });
  } catch(e) {
    console.log('Progress load:', e.message);
    set({progressLoading: false, progressHistory: [], progressActivity: []});
  }
}


// ══════════════════════════════════════════════════
// RADAR — clean triangle
// ══════════════════════════════════════════════════
function radar(being, becoming, connecting) {
  var cx = 150, cy = 155, r = 100;

  function pt(angleDeg, ratio) {
    var a = (angleDeg - 90) * Math.PI / 180;
    return [
      Math.round(cx + r * ratio * Math.cos(a)),
      Math.round(cy + r * ratio * Math.sin(a))
    ];
  }

  function tri(ratio, opacity) {
    var p0=pt(0,ratio), p1=pt(120,ratio), p2=pt(240,ratio);
    return '<polygon points="'+p0+' '+p1+' '+p2+'" fill="none" stroke="rgba(0,229,200,'+opacity+')" stroke-width="0.7"/>';
  }

  function ax(angleDeg) {
    var p=pt(angleDeg,1);
    return '<line x1="'+cx+'" y1="'+cy+'" x2="'+p[0]+'" y2="'+p[1]+'" stroke="rgba(0,229,200,0.10)" stroke-width="0.7"/>';
  }

  var b  = pt(0,   being);
  var bc = pt(120, becoming);
  var c  = pt(240, connecting);

  var lb  = pt(0,   1.38);
  var lbc = pt(120, 1.38);
  var lc  = pt(240, 1.38);

  var grids = tri(0.25,0.05) + tri(0.5,0.06) + tri(0.75,0.08) + tri(1.0,0.12);
  var axes  = ax(0) + ax(120) + ax(240);
  var poly  = b[0]+','+b[1]+' '+bc[0]+','+bc[1]+' '+c[0]+','+c[1];

  var bPct  = Math.round(being*100);
  var bcPct = Math.round(becoming*100);
  var cPct  = Math.round(connecting*100);

  return '<svg width="100%" viewBox="0 0 300 250" style="display:block;max-width:240px;margin:0 auto;overflow:visible">'
    + '<defs><filter id="wg" x="-50%" y="-50%" width="200%" height="200%">'
    + '<feGaussianBlur stdDeviation="3" result="b"/>'
    + '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>'
    + '</filter></defs>'
    + grids + axes
    + '<polygon points="'+poly+'" fill="rgba(0,229,200,0.13)" stroke="var(--wave)" stroke-width="1.8" stroke-linejoin="round" filter="url(#wg)"/>'
    + '<circle cx="'+b[0]+'"  cy="'+b[1]+'"  r="5" fill="var(--wave)" filter="url(#wg)"/>'
    + '<circle cx="'+bc[0]+'" cy="'+bc[1]+'" r="5" fill="var(--wave)" filter="url(#wg)"/>'
    + '<circle cx="'+c[0]+'"  cy="'+c[1]+'"  r="5" fill="var(--wave)" filter="url(#wg)"/>'
    + '<text x="'+lb[0]+'" y="'+(lb[1]-14)+'" text-anchor="middle" font-size="12" font-weight="700" fill="var(--wave)" font-family="sans-serif">Being</text>'
    + '<text x="'+lb[0]+'" y="'+(lb[1]-1)+'"  text-anchor="middle" font-size="10" fill="rgba(0,229,200,0.7)" font-family="sans-serif">'+bPct+'%</text>'
    + '<text x="'+(lbc[0]+14)+'" y="'+(lbc[1]-8)+'" text-anchor="start" font-size="12" font-weight="700" fill="#6AB0FF" font-family="sans-serif">Becoming</text>'
    + '<text x="'+(lbc[0]+14)+'" y="'+(lbc[1]+6)+'" text-anchor="start" font-size="10" fill="rgba(106,176,255,0.7)" font-family="sans-serif">'+bcPct+'%</text>'
    + '<text x="'+(lc[0]-8)+'" y="'+lc[1]+'" text-anchor="end" font-size="12" font-weight="700" fill="var(--gold)" font-family="sans-serif">Connecting</text>'
    + '<text x="'+(lc[0]-8)+'" y="'+(lc[1]+14)+'" text-anchor="end" font-size="10" fill="rgba(255,209,102,0.7)" font-family="sans-serif">'+cPct+'%</text>'
    + '</svg>';
}

// ── 8-domain "What you learn" radar ────────────────────────
function radarDomains(scores) {
  var D = [
    {k:'cognitive', l:'Cognitive',    l2:'& Intellectual'},
    {k:'creative',  l:'Creative',     l2:'& Artistic'},
    {k:'physical',  l:'Physical',     l2:'& Motor'},
    {k:'social',    l:'Social',       l2:'& Relational'},
    {k:'language',  l:'Language',     l2:'& Communication'},
    {k:'emotional', l:'Emotional',    l2:'& Psychological'},
    {k:'meta',      l:'Meta',         l2:'Learning'},
    {k:'technical', l:'Tools',        l2:'& Systems'},
  ];
  var sz=210, cx=105, cy=105, r=68, n=D.length;
  function pt(i,ratio){ var a=(2*Math.PI*i/n)-Math.PI/2; return [cx+r*ratio*Math.cos(a), cy+r*ratio*Math.sin(a)]; }
  var grids=[0.25,0.5,0.75,1.0].map(function(lv){
    return '<polygon points="'+D.map(function(_,i){return pt(i,lv).join(',');}).join(' ')+'" fill="none" stroke="rgba(0,229,200,0.07)" stroke-width="0.6"/>';
  }).join('');
  var axes=D.map(function(_,i){ var p=pt(i,1); return '<line x1="'+cx+'" y1="'+cy+'" x2="'+p[0]+'" y2="'+p[1]+'" stroke="rgba(0,229,200,0.08)" stroke-width="0.6"/>'; }).join('');
  var dpts=D.map(function(d,i){ return pt(i,scores[d.k]||0); });
  var dpoly=dpts.map(function(p){return p.join(',');}).join(' ');
  var dots=dpts.map(function(p){ return '<circle cx="'+p[0]+'" cy="'+p[1]+'" r="3" fill="var(--wave)" opacity="0.85"/>'; }).join('');
  var lbls=D.map(function(d,i){
    var p=pt(i,1.42);
    var anc=p[0]<cx-4?'end':p[0]>cx+4?'start':'middle';
    return '<text x="'+p[0]+'" y="'+p[1]+'" text-anchor="'+anc+'" font-size="8.5" fill="rgba(0,229,200,0.75)" font-family="sans-serif">'
      +'<tspan x="'+p[0]+'" dy="-4">'+d.l+'</tspan>'
      +'<tspan x="'+p[0]+'" dy="10">'+d.l2+'</tspan>'
      +'</text>';
  }).join('');
  return '<svg width="'+sz+'" height="'+sz+'" viewBox="0 0 '+sz+' '+sz+'" style="overflow:visible">'+grids+axes+'<polygon points="'+dpoly+'" fill="rgba(0,229,200,0.10)" stroke="var(--wave)" stroke-width="1.5" stroke-linejoin="round"/>'+dots+lbls+'</svg>';
}

// ── 15-art "Who you are" avatar radar ──────────────────────
// Arts arranged in 3 sectors of 5, each spanning 120°.
// Sector backgrounds show Being / Becoming / Connecting.
function radarArts(artScores) {
  var ARTS_R = [
    // Being sector: 12°–108° (centered at top, 5 arts × 24° spacing)
    {slug:'move',        label:'Move',      group:'being',      angle:12},
    {slug:'eat',         label:'Eat',       group:'being',      angle:36},
    {slug:'feel',        label:'Feel',      group:'being',      angle:60},
    {slug:'notice',      label:'Notice',    group:'being',      angle:84},
    {slug:'express',     label:'Express',   group:'being',      angle:108},
    // Becoming sector: 132°–228°
    {slug:'live',        label:'Live',      group:'becoming',   angle:132},
    {slug:'listen',      label:'Listen',    group:'becoming',   angle:156},
    {slug:'give',        label:'Give',      group:'becoming',   angle:180},
    {slug:'receive',     label:'Receive',   group:'becoming',   angle:204},
    {slug:'collaborate', label:'Collaborate', group:'becoming',   angle:228},
    // Connecting sector: 252°–348°
    {slug:'understand',  label:'Understand',group:'connecting', angle:252},
    {slug:'respect',     label:'Respect',   group:'connecting', angle:276},
    {slug:'build',       label:'Build',     group:'connecting', angle:300},
    {slug:'grow',        label:'Grow',      group:'connecting', angle:324},
    {slug:'consume',     label:'Consume',   group:'connecting', angle:348},
  ];
  var GC = {
    being:      {fill:'rgba(0,229,200,0.07)',  stroke:'rgba(0,229,200,0.9)',   label:'Being'},
    becoming:   {fill:'rgba(61,123,255,0.07)', stroke:'rgba(106,176,255,0.9)', label:'Becoming'},
    connecting: {fill:'rgba(255,209,102,0.07)',stroke:'rgba(255,209,102,0.9)', label:'Connecting'},
  };
  var sz=240, cx=120, cy=120, r=72;
  function toXY(deg,ratio){ var a=(deg-90)*Math.PI/180; return [cx+r*ratio*Math.cos(a), cy+r*ratio*Math.sin(a)]; }
  function sectorPath(s,e){
    var p1=toXY(s,1.05), p2=toXY(e,1.05), steps=16, pts=[[cx,cy]];
    for(var i=0;i<=steps;i++){ var a=s+(e-s)*i/steps; pts.push(toXY(a,1.05)); }
    return pts.map(function(p){return p.join(',');}).join(' ');
  }
  var sectors='<polygon points="'+sectorPath(0,120)+'" fill="'+GC.being.fill+'" stroke="none"/>'
    +'<polygon points="'+sectorPath(120,240)+'" fill="'+GC.becoming.fill+'" stroke="none"/>'
    +'<polygon points="'+sectorPath(240,360)+'" fill="'+GC.connecting.fill+'" stroke="none"/>';
  var grids=[0.25,0.5,0.75,1.0].map(function(lv){
    return '<polygon points="'+ARTS_R.map(function(a){return toXY(a.angle,lv).join(',');}).join(' ')+'" fill="none" stroke="rgba(255,255,255,0.05)" stroke-width="0.5"/>';
  }).join('');
  var axes=ARTS_R.map(function(a){ var p=toXY(a.angle,1); return '<line x1="'+cx+'" y1="'+cy+'" x2="'+p[0]+'" y2="'+p[1]+'" stroke="rgba(255,255,255,0.06)" stroke-width="0.5"/>'; }).join('');
  var dpts=ARTS_R.map(function(a){ return toXY(a.angle, artScores[a.slug]||0); });
  var dpoly=dpts.map(function(p){return p.join(',');}).join(' ');
  var dots=ARTS_R.map(function(a,i){ var c=GC[a.group].stroke; return '<circle cx="'+dpts[i][0]+'" cy="'+dpts[i][1]+'" r="2.5" fill="'+c+'" opacity="0.9"/>'; }).join('');
  var lbls=ARTS_R.map(function(a){ var p=toXY(a.angle,1.36); var anc=p[0]<cx-4?'end':p[0]>cx+4?'start':'middle'; var c=GC[a.group].stroke; return '<text x="'+p[0]+'" y="'+(p[1]+3)+'" text-anchor="'+anc+'" font-size="8.5" fill="'+c+'" font-family="sans-serif">'+a.label+'</text>'; }).join('');
  // Sector arc labels (Being / Becoming / Connecting at midpoint of each sector)
  var gLbls=[{g:'being',mid:60,xOff:0,yOff:0},{g:'becoming',mid:144,xOff:0,yOff:0},{g:'connecting',mid:296,xOff:0,yOff:0}].map(function(x){
    var p=toXY(x.mid,1.85); var px=p[0]+(x.xOff||0); var py=p[1]+(x.yOff||0);
    var c=GC[x.g].stroke; var anc=px<cx-4?'end':px>cx+4?'start':'middle';
    return '<text x="'+px+'" y="'+(py+3)+'" text-anchor="'+anc+'" font-size="10" font-weight="700" font-style="italic" fill="'+c+'" font-family="sans-serif" opacity="0.9">'+GC[x.g].label+'</text>';
  }).join('');
  return '<svg width="'+sz+'" height="218" viewBox="0 15 '+sz+' 218" style="overflow:visible">'+sectors+grids+axes+'<polygon points="'+dpoly+'" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.45)" stroke-width="1.2" stroke-linejoin="round"/>'+dots+lbls+gLbls+'</svg>';
}

// ══════════════════════════════════════════════════
// AUTH PAGES
// ══════════════════════════════════════════════════
function AuthPage() {
  const isLogin = S.authMode === 'login';
  return `
  <div class="auth-wrap">
    <div class="auth-card">
      <div class="auth-logo">
        <div class="logo" style="font-size:clamp(13px,4vw,17px);white-space:nowrap">Surfing the Frequencies</div>
        <div class="auth-tagline">your lifelong learning journey starts here</div>
      </div>

      ${isLogin ? `
      <div class="form-group">
        <label class="form-label">Email</label>
        <input class="form-input" id="auth-email" type="email" placeholder="you@example.com" autocomplete="email" value="${S.authEmail||''}" onkeydown="if(event.key==='Enter')document.getElementById('auth-password').focus()" />
      </div>
      <div class="form-group">
        <label class="form-label">Password</label>
        <input class="form-input" id="auth-password" type="password" placeholder="••••••••" autocomplete="current-password" onkeydown="if(event.key==='Enter')doLogin()"/>
      </div>
      <div class="form-error ${S.authError?'show':''}" id="auth-err">${S.authError}</div>
      <button class="btn btn-wave btn-full btn-lg" style="margin-top:8px" onclick="doLogin()" id="auth-btn">
        ${S.authLoading ? '<div class="spinner"></div>' : 'Paddle in →'}
      </button>
      <div class="auth-switch">
        New here? <a onclick="set({authMode:'register',authError:''})">Create your account</a>
      </div>
      ` : `
      <div class="form-group">
        <label class="form-label">Your name</label>
        <input class="form-input" id="reg-name" type="text" placeholder="What shall we call you?" value="${S.regName||''}" />
      </div>
      <div class="form-group">
        <label class="form-label">Username</label>
        <input class="form-input" id="reg-username" type="text" placeholder="lowercase, no spaces" value="${S.regUsername||''}" />
      </div>
      <div class="form-group">
        <label class="form-label">Email</label>
        <input class="form-input" id="reg-email" type="email" placeholder="you@example.com" value="${S.regEmail||''}" />
      </div>
      <div class="form-group">
        <label class="form-label">Password</label>
        <input class="form-input" id="reg-password" type="password" placeholder="at least 8 characters"/>
      </div>
      <div class="form-group">
        <label class="form-label">Birth year <span style="color:var(--text3)">(optional — helps us personalise)</span></label>
        <input class="form-input" id="reg-year" type="number" placeholder="e.g. 1985" min="1920" max="2024" value="${S.regYear||''}" />
      </div>
      <div class="form-error ${S.authError?'show':''}" id="auth-err">${S.authError}</div>
      <button class="btn btn-wave btn-full btn-lg" style="margin-top:8px" onclick="doRegister()" id="auth-btn">
        ${S.authLoading ? '<div class="spinner"></div>' : 'Begin the journey →'}
      </button>
      <div class="auth-switch">
        Already riding? <a onclick="set({authMode:'login',authError:''})">Sign in</a>
      </div>
      `}
    </div>
    <div style="text-align:center;margin-top:16px;font-size:12px;color:var(--text3)">
      By continuing you agree to our <a href="/privacy.html" target="_blank" style="color:var(--text2)">Privacy Note</a>.
    </div>
    ${S.showPolisGate ? `
    <div style="position:fixed;bottom:24px;left:50%;transform:translateX(-50%);
      background:var(--bg3);border:1px solid var(--polis,#7B5EA7);border-radius:var(--r);
      padding:16px 24px;max-width:400px;text-align:center;z-index:200;
      box-shadow:0 8px 32px rgba(0,0,0,0.4)">
      <div style="font-family:var(--font-display);font-weight:700;margin-bottom:6px">The Polis opens with practice</div>
      <div style="font-size:13px;color:var(--text2);line-height:1.6">
        Complete 5 learning days or earn 50 XP to unlock civic participation.
        The Polis works best when its members have practiced listening, understanding and respect.
      </div>
    </div>` : ''}
  </div>`;
}

// ══════════════════════════════════════════════════
// NAV
// ══════════════════════════════════════════════════
// ── i18n — T(key, vars) translation helper ────────────────────
const LANG = {
  en: {
    // Nav
    'nav.agora':'Agora','nav.academy':'Academy','nav.mouseion':'Mouseion',
    'nav.stoa':'Peripatos','nav.polis':'Polis','nav.contribute':'Contribute',
    'nav.signout':'Sign out',
    // Auth
    'auth.email':'Email','auth.password':'Password','auth.paddle_in':'Paddle in →',
    'auth.create':'Create your account','auth.have_account':'Already have one?',
    'auth.username':'Username','auth.register':'Create account',
    // Agora
    'agora.welcome':'Welcome','agora.day_journey':'Day {n} on your journey · Surfing the Frequencies',
    'agora.paddle_in':'▶ Paddle in','agora.total_xp':'total xp',
    'agora.level':'current level','agora.sessions':'sessions done',
    'agora.streak':'day streak','agora.mouseion':'My Mouseion',
    'agora.rec_next':'Recommended next','agora.start':'Start →',
    'agora.new_match':'New match','agora.match_score':'Match score',
    // Session
    'session.warmup':'Warm up','session.explore':'Explore',
    'session.challenge':'Challenge','session.reflect':'Reflect',
    'session.assess':'Assess','session.complete':'Complete session →',
    'session.calling':'What\'s calling you?','session.resonates':'Choose what resonates right now',
    'session.skip':'Skip — use engine recommendation',
    'session.last_wave':'One last wave. Your honest best — this helps me know where to take you next.',
    'session.still_learning':'🌱 Still learning','session.getting_it':'✓ Getting it',
    'session.knew_this':'🚀 I knew this','session.understand_q':'How well do you feel you understand this concept?',
    'session.explainer':'What\'s this question about?',
    // Stoa
    'stoa.title':'The Peripatos','stoa.tagline':'A walkway for wandering thought. This space is yours — no grades, no performance, just honest reflection.',
    'stoa.todays_prompt':'Today\'s prompt','stoa.save':'Save reflection',
    'stoa.recent':'Recent reflections','stoa.private':'Private by default · yours always',
    // Mouseion
    'mouseion.title':'The Mouseion','mouseion.tagline':'The universal library of human arts · yours to explore at your own pace!',
    'mouseion.thought':'If you care to share what\'s on your mind, I can weave it into our next session together.',
    'mouseion.placeholder':'What are you thinking about, struggling with, or curious about today? (optional)',
    // Prefs
    'prefs.title':'Preferences','prefs.name':'Display name',
    'prefs.avatar':'Avatar','prefs.phase':'Life phase','prefs.language':'Language',
    'prefs.save':'Save changes',
  },
  fr: {
    'nav.agora':'Agora','nav.academy':'Académie','nav.mouseion':'Mouseion',
    'nav.stoa':'Peripatos','nav.polis':'Polis','nav.contribute':'Contribuer',
    'nav.signout':'Se déconnecter',
    'auth.email':'E-mail','auth.password':'Mot de passe','auth.paddle_in':'Commencer →',
    'auth.create':'Créer ton compte','auth.have_account':'Tu as déjà un compte ?',
    'auth.username':'Nom d\'utilisateur','auth.register':'Créer un compte',
    'agora.welcome':'Bienvenue','agora.day_journey':'Jour {n} de ton voyage · Surfing the Frequencies',
    'agora.paddle_in':'▶ Commencer','agora.total_xp':'XP total',
    'agora.level':'niveau actuel','agora.sessions':'sessions faites',
    'agora.streak':'jours consécutifs','agora.mouseion':'Mon Mouseion',
    'agora.rec_next':'Prochaine recommandation','agora.start':'Commencer →',
    'agora.new_match':'Nouvelle correspondance','agora.match_score':'Score de correspondance',
    'session.warmup':'Échauffement','session.explore':'Explorer',
    'session.challenge':'Défi','session.reflect':'Réfléchir',
    'session.assess':'Évaluation','session.complete':'Terminer la session →',
    'session.calling':'Qu\'est-ce qui t\'appelle ?','session.resonates':'Choisis ce qui résonne maintenant',
    'session.skip':'Ignorer — utiliser la recommandation du moteur',
    'session.last_wave':'Une dernière vague. Ton meilleur effort — cela m\'aide à savoir où t\'emmener ensuite.',
    'session.still_learning':'🌱 J\'apprends encore','session.getting_it':'✓ Je comprends',
    'session.knew_this':'🚀 Je le savais déjà','session.understand_q':'À quel point te sens-tu à l\'aise avec ce concept ?',
    'session.explainer':'De quoi parle cette question ?',
    'stoa.title':'Le Péripatos','stoa.tagline':'Un portique pour la pensée solitaire. Cet espace est le tien — sans notes, sans performance, juste une réflexion honnête.',
    'stoa.todays_prompt':'Réflexion du jour','stoa.save':'Sauvegarder',
    'stoa.recent':'Réflexions récentes','stoa.private':'Privé par défaut · toujours à toi',
    'mouseion.title':'Le Mouseion','mouseion.tagline':'La bibliothèque universelle des arts humains · à explorer à ton rythme !',
    'mouseion.thought':'Si tu veux partager ce qui t\'occupe l\'esprit, je peux l\'intégrer dans notre prochaine session.',
    'mouseion.placeholder':'À quoi penses-tu, avec quoi tu luttes, ou de quoi es-tu curieux aujourd\'hui ? (optionnel)',
    'prefs.title':'Préférences','prefs.name':'Nom affiché',
    'prefs.avatar':'Avatar','prefs.phase':'Phase de vie','prefs.language':'Langue',
    'prefs.save':'Sauvegarder',
  },
  es: {
    'nav.agora':'Ágora','nav.academy':'Academia','nav.mouseion':'Mouseion',
    'nav.stoa':'Peripatos','nav.polis':'Polis','nav.contribute':'Contribuir',
    'nav.signout':'Cerrar sesión',
    'auth.email':'Correo electrónico','auth.password':'Contraseña','auth.paddle_in':'Empezar →',
    'auth.create':'Crear tu cuenta','auth.have_account':'¿Ya tienes una cuenta?',
    'auth.username':'Nombre de usuario','auth.register':'Crear cuenta',
    'agora.welcome':'Bienvenido','agora.day_journey':'Día {n} de tu viaje · Surfing the Frequencies',
    'agora.paddle_in':'▶ Empezar','agora.total_xp':'XP total',
    'agora.level':'nivel actual','agora.sessions':'sesiones completadas',
    'agora.streak':'días consecutivos','agora.mouseion':'Mi Mouseion',
    'agora.rec_next':'Siguiente recomendación','agora.start':'Empezar →',
    'agora.new_match':'Nueva coincidencia','agora.match_score':'Puntuación',
    'session.warmup':'Calentamiento','session.explore':'Explorar',
    'session.challenge':'Desafío','session.reflect':'Reflexionar',
    'session.assess':'Evaluación','session.complete':'Completar sesión →',
    'session.calling':'¿Qué te llama hoy?','session.resonates':'Elige lo que resuena ahora',
    'session.skip':'Omitir — usar recomendación del motor',
    'session.last_wave':'Una última ola. Tu mejor esfuerzo — esto me ayuda a saber a dónde llevarte.',
    'session.still_learning':'🌱 Aún aprendiendo','session.getting_it':'✓ Lo estoy entendiendo',
    'session.knew_this':'🚀 Ya lo sabía','session.understand_q':'¿Qué tan bien entiendes este concepto?',
    'session.explainer':'¿De qué trata esta pregunta?',
    'stoa.title':'El Peripatos','stoa.tagline':'Un pórtico para el pensamiento solitario. Este espacio es tuyo — sin calificaciones, sin actuación, solo pensamiento honesto.',
    'stoa.todays_prompt':'Reflexión de hoy','stoa.save':'Guardar reflexión',
    'stoa.recent':'Reflexiones recientes','stoa.private':'Privado por defecto · siempre tuyo',
    'mouseion.title':'El Mouseion','mouseion.tagline':'La biblioteca universal de artes humanas — 15 artes · 78 habilidades · explóralas a tu ritmo',
    'mouseion.thought':'Si quieres compartir lo que tienes en mente, puedo integrarlo en nuestra próxima sesión.',
    'mouseion.placeholder':'¿En qué estás pensando, con qué luchas, o de qué tienes curiosidad hoy? (opcional)',
    'prefs.title':'Preferencias','prefs.name':'Nombre visible',
    'prefs.avatar':'Avatar','prefs.phase':'Fase de vida','prefs.language':'Idioma',
    'prefs.save':'Guardar cambios',
  },
  vi: {
    'nav.agora':'Agora','nav.academy':'Học viện','nav.mouseion':'Mouseion',
    'nav.stoa':'Peripatos','nav.polis':'Polis','nav.contribute':'Đóng góp',
    'nav.signout':'Đăng xuất',
    'auth.email':'Email','auth.password':'Mật khẩu','auth.paddle_in':'Bắt đầu →',
    'auth.create':'Tạo tài khoản','auth.have_account':'Đã có tài khoản?',
    'auth.username':'Tên người dùng','auth.register':'Tạo tài khoản',
    'agora.welcome':'Chào mừng','agora.day_journey':'Ngày {n} trên hành trình · Surfing the Frequencies',
    'agora.paddle_in':'▶ Bắt đầu','agora.total_xp':'Tổng XP',
    'agora.level':'cấp độ hiện tại','agora.sessions':'phiên hoàn thành',
    'agora.streak':'ngày liên tiếp','agora.mouseion':'Mouseion của tôi',
    'agora.rec_next':'Gợi ý tiếp theo','agora.start':'Bắt đầu →',
    'agora.new_match':'Kết hợp mới','agora.match_score':'Điểm phù hợp',
    'session.warmup':'Khởi động','session.explore':'Khám phá',
    'session.challenge':'Thách thức','session.reflect':'Suy ngẫm',
    'session.assess':'Đánh giá','session.complete':'Hoàn thành phiên →',
    'session.calling':'Điều gì đang gọi bạn?','session.resonates':'Chọn điều cộng hưởng với bạn lúc này',
    'session.skip':'Bỏ qua — dùng đề xuất của hệ thống',
    'session.last_wave':'Một sóng cuối. Hết sức của bạn — điều này giúp tôi biết dẫn bạn đến đâu tiếp theo.',
    'session.still_learning':'🌱 Vẫn đang học','session.getting_it':'✓ Đang hiểu',
    'session.knew_this':'🚀 Tôi đã biết rồi','session.understand_q':'Bạn cảm thấy hiểu khái niệm này đến mức nào?',
    'session.explainer':'Câu hỏi này về điều gì?',
    'stoa.title':'Peripatos','stoa.tagline':'Không gian suy nghĩ một mình. Đây là không gian của bạn — không điểm số, không trình diễn.',
    'stoa.todays_prompt':'Câu hỏi hôm nay','stoa.save':'Lưu suy ngẫm',
    'stoa.recent':'Suy ngẫm gần đây','stoa.private':'Riêng tư theo mặc định · luôn là của bạn',
    'mouseion.title':'Mouseion','mouseion.tagline':'Thư viện nghệ thuật nhân loại — 15 nghệ thuật · 78 kỹ năng · khám phá theo nhịp độ của bạn',
    'mouseion.thought':'Nếu bạn muốn chia sẻ điều bạn đang nghĩ, tôi có thể đưa nó vào phiên tiếp theo của chúng ta.',
    'mouseion.placeholder':'Bạn đang nghĩ về điều gì, đang vật lộn với điều gì, hay tò mò về điều gì hôm nay? (tùy chọn)',
    'prefs.title':'Tùy chọn','prefs.name':'Tên hiển thị',
    'prefs.avatar':'Ảnh đại diện','prefs.phase':'Giai đoạn cuộc đời','prefs.language':'Ngôn ngữ',
    'prefs.save':'Lưu thay đổi',
  },
  zh: {
    'nav.agora':'广场','nav.academy':'学院','nav.mouseion':'学馆',
    'nav.stoa':'漫步廊','nav.polis':'公民广场','nav.contribute':'贡献',
    'nav.signout':'退出登录',
    'auth.email':'电子邮件','auth.password':'密码','auth.paddle_in':'开始 →',
    'auth.create':'创建账户','auth.have_account':'已有账户？',
    'auth.username':'用户名','auth.register':'创建账户',
    'agora.welcome':'欢迎','agora.day_journey':'旅程第 {n} 天 · 冲浪频率',
    'agora.paddle_in':'▶ 开始','agora.total_xp':'总经验',
    'agora.level':'当前等级','agora.sessions':'已完成课程',
    'agora.streak':'连续天数','agora.mouseion':'我的学馆',
    'agora.rec_next':'下一步推荐','agora.start':'开始 →',
    'agora.new_match':'新匹配','agora.match_score':'匹配分数',
    'session.warmup':'热身','session.explore':'探索',
    'session.challenge':'挑战','session.reflect':'反思',
    'session.assess':'评估','session.complete':'完成课程 →',
    'session.calling':'什么在召唤你？','session.resonates':'选择现在最能引起共鸣的',
    'session.skip':'跳过 — 使用引擎推荐',
    'session.last_wave':'最后一波。你最诚实的回答 — 这帮助我知道接下来带你去哪里。',
    'session.still_learning':'🌱 仍在学习','session.getting_it':'✓ 正在理解',
    'session.knew_this':'🚀 我早就知道了','session.understand_q':'你对这个概念理解得有多好？',
    'session.explainer':'这道题在考什么？',
    'stoa.title':'漫步廊','stoa.tagline':'独处思考的空间。这是你的地方 — 没有评分，没有表演，只有真实的思考。',
    'stoa.todays_prompt':'今日思考','stoa.save':'保存反思',
    'stoa.recent':'近期反思','stoa.private':'默认私密 · 永远属于你',
    'mouseion.title':'学馆','mouseion.tagline':'人类艺术的普世图书馆 — 15项艺术 · 78项技能 · 按你的节奏探索',
    'mouseion.thought':'如果你想分享心中所想，我可以将其融入我们的下一次课程。',
    'mouseion.placeholder':'今天你在想什么，正在挣扎什么，或者对什么感到好奇？（可选）',
    'prefs.title':'偏好设置','prefs.name':'显示名称',
    'prefs.avatar':'头像','prefs.phase':'人生阶段','prefs.language':'语言',
    'prefs.save':'保存更改',
  },
  ar: {
    'nav.agora':'الأغورا','nav.academy':'الأكاديمية','nav.mouseion':'الموسيون',
    'nav.stoa':'بيريباتوس','nav.polis':'بوليس','nav.contribute':'المساهمة',
    'nav.signout':'تسجيل الخروج',
    'auth.email':'البريد الإلكتروني','auth.password':'كلمة المرور','auth.paddle_in':'ابدأ →',
    'auth.create':'إنشاء حساب','auth.have_account':'لديك حساب بالفعل؟',
    'auth.username':'اسم المستخدم','auth.register':'إنشاء حساب',
    'agora.welcome':'مرحباً','agora.day_journey':'اليوم {n} في رحلتك · ركوب الأمواج',
    'agora.paddle_in':'▶ ابدأ','agora.total_xp':'إجمالي النقاط',
    'agora.level':'المستوى الحالي','agora.sessions':'الجلسات المكتملة',
    'agora.streak':'أيام متتالية','agora.mouseion':'موسيوني',
    'agora.rec_next':'التوصية التالية','agora.start':'ابدأ →',
    'agora.new_match':'مطابقة جديدة','agora.match_score':'درجة التطابق',
    'session.warmup':'الإحماء','session.explore':'استكشاف',
    'session.challenge':'التحدي','session.reflect':'التأمل',
    'session.assess':'التقييم','session.complete':'إتمام الجلسة →',
    'session.calling':'ماذا يناديك؟','session.resonates':'اختر ما يتردد صداه الآن',
    'session.skip':'تخطي — استخدام توصية المحرك',
    'session.last_wave':'موجة أخيرة. أفضل ما لديك — هذا يساعدني على معرفة أين أأخذك بعد ذلك.',
    'session.still_learning':'🌱 لا أزال أتعلم','session.getting_it':'✓ أفهم',
    'session.knew_this':'🚀 كنت أعرف هذا','session.understand_q':'كيف تشعر بفهمك لهذا المفهوم؟',
    'session.explainer':'عم تدور هذه السؤال؟',
    'stoa.title':'بيريباتوس','stoa.tagline':'مكان للتفكير المنفرد. هذه المساحة لك — بلا درجات، بلا أداء، مجرد تفكير صادق.',
    'stoa.todays_prompt':'تأمل اليوم','stoa.save':'حفظ التأمل',
    'stoa.recent':'التأملات الأخيرة','stoa.private':'خاص بشكل افتراضي · لك دائماً',
    'mouseion.title':'الموسيون','mouseion.tagline':'المكتبة العالمية للفنون الإنسانية — 15 فناً · 78 مهارة · استكشفها بوتيرتك',
    'mouseion.thought':'إذا أردت مشاركة ما يدور في ذهنك، يمكنني نسجه في جلستنا القادمة.',
    'mouseion.placeholder':'ماذا تفكر، بماذا تصارع، أو عم تتساءل اليوم؟ (اختياري)',
    'prefs.title':'التفضيلات','prefs.name':'الاسم المعروض',
    'prefs.avatar':'الصورة الرمزية','prefs.phase':'مرحلة الحياة','prefs.language':'اللغة',
    'prefs.save':'حفظ التغييرات',
  },
  de: {
    'nav.agora':'Agora','nav.academy':'Akademie','nav.mouseion':'Mouseion',
    'nav.stoa':'Peripatos','nav.polis':'Polis','nav.contribute':'Beitragen',
    'nav.signout':'Abmelden',
    'auth.email':'E-Mail','auth.password':'Passwort','auth.paddle_in':'Einstieg →',
    'auth.create':'Konto erstellen','auth.have_account':'Bereits ein Konto?',
    'auth.username':'Benutzername','auth.register':'Konto erstellen',
    'agora.welcome':'Willkommen','agora.day_journey':'Tag {n} deiner Reise · Surfing the Frequencies',
    'agora.paddle_in':'▶ Einstieg','agora.total_xp':'Gesamt-XP',
    'agora.level':'Aktuelles Level','agora.sessions':'Abgeschlossene Sessions',
    'agora.streak':'Tage in Serie','agora.mouseion':'Mein Mouseion',
    'agora.rec_next':'Nächste Empfehlung','agora.start':'Starten →',
    'agora.new_match':'Neue Übereinstimmung','agora.match_score':'Match-Score',
    'session.warmup':'Aufwärmen','session.explore':'Erkunden',
    'session.challenge':'Herausforderung','session.reflect':'Reflektieren',
    'session.assess':'Bewerten','session.complete':'Session abschließen →',
    'session.calling':'Was ruft dich?','session.resonates':'Wähle was jetzt resoniert',
    'session.skip':'Überspringen — Engine-Empfehlung nutzen',
    'session.last_wave':'Eine letzte Welle. Dein ehrlichstes — das hilft mir zu wissen, wohin ich dich als Nächstes führe.',
    'session.still_learning':'🌱 Lerne noch','session.getting_it':'✓ Verstehe es',
    'session.knew_this':'🚀 Das wusste ich','session.understand_q':'Wie gut verstehst du dieses Konzept?',
    'session.explainer':'Worum geht diese Frage?',
    'stoa.title':'Peripatos','stoa.tagline':'Ein Ort für wandernde Gedanken. Dies ist dein Raum — keine Noten, keine Performance, nur ehrliche Reflexion.',
    'stoa.todays_prompt':'Heutige Prompt','stoa.save':'Reflexion speichern',
    'stoa.recent':'Letzte Reflexionen','stoa.private':'Standardmäßig privat · immer deins',
    'mouseion.title':'Das Mouseion','mouseion.tagline':'Die universelle Bibliothek der menschlichen Künste — 15 Künste · 78 Fertigkeiten · in deinem Tempo erkunden',
    'mouseion.thought':'Wenn du teilen möchtest, was dir durch den Kopf geht, kann ich es in unsere nächste Session einweben.',
    'mouseion.placeholder':'Worüber denkst du nach, womit kämpfst du, oder was interessiert dich heute? (optional)',
    'prefs.title':'Einstellungen','prefs.name':'Anzeigename',
    'prefs.avatar':'Avatar','prefs.phase':'Lebensphase','prefs.language':'Sprache',
    'prefs.save':'Änderungen speichern',
    'common.back_agora':'Back to Agora','stoa.save':'Save to Peripatos','session.paddle':'Paddle in','session.unlock_arts':'Complete sessions to see your strongest arts','session.unlock_domains':'Complete sessions to unlock your domain profile',
    'dash.progress':'Your Progress','onboard.where_life':'Where are you in life?','onboard.what_pulls':'What pulls you right now?','onboard.choose_wave':'Choose your wave','onboard.choose_colour':'Choose your colour','bio.where':'Where on this earth are you surfing from?','bio.locate':'Locate my bioregion','bio.locating':'Locating your bioregion…','bio.city_notice':'City-level only · never stored · your data stays on your device','bio.your':'Your Bioregion','session.paddle':'Paddle in','session.unlock_arts':'Complete sessions to see your strongest arts','session.unlock_domains':'Complete sessions to unlock your domain profile',
    'bio.where':'Where on this earth are you surfing from?','bio.locate':'Locate my bioregion','bio.locating':'Locating your bioregion…','bio.city_notice':'City-level only · never stored · your data stays on your device','bio.your':'Your Bioregion','common.loading':'Loading',
    'common.continue':'Continue',
    'common.lets_go':'Let us go',
    'common.learner':'Learner',
    'stat.points':'Points',
    'stat.learning':'Learning',
    'stat.skills':'Skills',
    'stat.arts':'Arts',
    'dash.domain_tab':'Domains',
    'dash.avatar_tab':'Human Signature',
    'auth.birth_year':'Birth year <span style="color:var(--text3)">(optional — helps us personalise)</span>',
    'auth.google':'Register with Google',
    'auth.or_email':'Or continue with email',
    'auth.verify_sent':'Verification email sent! Please check your inbox.',
    'auth.verify_click_link':'Click the link in your email to verify your account.',
    'auth.verify_resend':'Resend verification email',
    'admin.no_learners':'No learners yet.',
    'onboard.what_call':'What shall we call you?',
    'onboard.name_desc':'This is how you will appear on your journey.',
    'nav.outreach':'Outreach',
    'nav.ai':'AI Engine',
    'auth.verify_sent':'Verifizierungs-E-Mail gesendet! Bitte prüfe deinen Posteingang.',
    'auth.verify_click_link':'Klicke den Link in der E-Mail, um deinen Account zu verifizieren.',
    'auth.verify_resend':'Verifizierungs-E-Mail erneut senden',
  },
  ru: {
    'nav.agora':'Агора','nav.academy':'Академия','nav.mouseion':'Музей',
    'nav.stoa':'Перипат','nav.polis':'Полис','nav.contribute':'Вклад',
    'nav.signout':'Выход',
    'auth.email':'Email','auth.password':'Пароль','auth.paddle_in':'Начать →',
    'auth.create':'Создать аккаунт','auth.have_account':'Уже есть аккаунт?',
    'auth.username':'Имя пользователя','auth.register':'Создать аккаунт',
    'agora.welcome':'Добро пожаловать','agora.day_journey':'День {n} твоего пути · Surfing the Frequencies',
    'agora.paddle_in':'▶ Начать','agora.total_xp':'всего XP',
    'agora.level':'текущий уровень','agora.sessions':'завершено сессий',
    'agora.streak':'дней подряд','agora.mouseion':'Мой Mouseion',
    'agora.rec_next':'Следующая рекомендация','agora.start':'Старт →',
    'agora.new_match':'Новое совпадение','agora.match_score':'Оценка совпадения',
    'session.warmup':'Разогрев','session.explore':'Исследовать',
    'session.challenge':'Вызов','session.reflect':'Размышление',
    'session.assess':'Оценка','session.complete':'Завершить сессию →',
    'session.calling':'Что тебя зовёт?','session.resonates':'Выбери что резонирует сейчас',
    'session.skip':'Пропустить — рекомендация движка',
    'session.last_wave':'Последняя волна. Твоё лучшее — это помогает мне понять, куда вести тебя дальше.',
    'session.still_learning':'🌱 Учусь','session.getting_it':'✓ Понимаю',
    'session.knew_this':'🚀 Я знал это','session.understand_q':'Насколько хорошо ты понимаешь эту концепцию?',
    'session.explainer':'О чём этот вопрос?',
    'stoa.title':'Перипат','stoa.tagline':'Место для блуждающих мыслей. Это твоё пространство — нет оценок, нет выступлений, только честное размышление.',
    'stoa.todays_prompt':'Промпт дня','stoa.save':'Сохранить размышление',
    'stoa.recent':'Последние размышления','stoa.private':'Приватно по умолчанию · всегда твоё',
    'mouseion.title':'Музей','mouseion.tagline':'Универсальная библиотека человеческих искусств — 15 искусств · 78 навыков · исследуй в своём темпе',
    'mouseion.thought':'Если хочешь поделиться тем, что у тебя на уме, я weaving это в нашу следующую сессию.',
    'mouseion.placeholder':'О чём ты думаешь, с чем борешься, или что тебя интересует сегодня? (опционально)',
    'prefs.title':'Настройки','prefs.name':'Отображаемое имя',
    'prefs.avatar':'Аватар','prefs.phase':'Жизненная фаза','prefs.language':'Язык',
    'prefs.save':'Сохранить изменения',
    'common.back_agora':'Back to Agora','stoa.save':'Save to Peripatos','session.paddle':'Paddle in','session.unlock_arts':'Complete sessions to see your strongest arts','session.unlock_domains':'Complete sessions to unlock your domain profile',
    'dash.progress':'Your Progress','onboard.where_life':'Where are you in life?','onboard.what_pulls':'What pulls you right now?','onboard.choose_wave':'Choose your wave','onboard.choose_colour':'Choose your colour','bio.where':'Where on this earth are you surfing from?','bio.locate':'Locate my bioregion','bio.locating':'Locating your bioregion…','bio.city_notice':'City-level only · never stored · your data stays on your device','bio.your':'Your Bioregion','session.paddle':'Paddle in','session.unlock_arts':'Complete sessions to see your strongest arts','session.unlock_domains':'Complete sessions to unlock your domain profile',
    'bio.where':'Where on this earth are you surfing from?','bio.locate':'Locate my bioregion','bio.locating':'Locating your bioregion…','bio.city_notice':'City-level only · never stored · your data stays on your device','bio.your':'Your Bioregion','common.loading':'Loading',
    'common.continue':'Continue',
    'common.lets_go':'Let us go',
    'common.learner':'Learner',
    'stat.points':'Points',
    'stat.learning':'Learning',
    'stat.skills':'Skills',
    'stat.arts':'Arts',
    'dash.domain_tab':'Domains',
    'dash.avatar_tab':'Human Signature',
    'auth.birth_year':'Birth year <span style="color:var(--text3)">(optional — helps us personalise)</span>',
    'auth.google':'Register with Google',
    'auth.or_email':'Or continue with email',
    'auth.verify_sent':'Verification email sent! Please check your inbox.',
    'auth.verify_click_link':'Click the link in your email to verify your account.',
    'auth.verify_resend':'Resend verification email',
    'admin.no_learners':'No learners yet.',
    'onboard.what_call':'What shall we call you?',
    'onboard.name_desc':'This is how you will appear on your journey.',
    'nav.outreach':'Outreach',
    'nav.ai':'AI Engine',
    'auth.verify_sent':'Письмо с подтверждением отправлено! Проверьте свою почту.',
    'auth.verify_click_link':'Нажмите на ссылку в письме, чтобы подтвердить аккаунт.',
    'auth.verify_resend':'Отправить повторно',
  },
};

function T(key, vars) {
  var dict = LANG[S.language] || LANG.en;
  var str  = dict[key] || LANG.en[key] || key;
  if (vars) Object.keys(vars).forEach(function(k){ str = str.replace('{'+k+'}', vars[k]); });
  return str;
}

// RTL languages
var RTL_LANGS = ['ar'];
function applyLang() {
  var isRTL = RTL_LANGS.includes(S.language);
  document.documentElement.lang = S.language || 'en';
  document.documentElement.dir  = isRTL ? 'rtl' : 'ltr';
  localStorage.setItem('fl_lang', S.language || 'en');
}


// ── Mobile nav toggle ─────────────────────────────────────────
window.toggleMobileNav = function() {
  var burger = document.getElementById('nav-burger');
  var panel  = document.getElementById('nav-mobile-panel');
  if (!burger || !panel) return;
  var open = panel.classList.toggle('open');
  burger.classList.toggle('open', open);
  if (open) {
    setTimeout(function() {
      document.addEventListener('click', function closeMobileNav(e) {
        var p = document.getElementById('nav-mobile-panel');
        var b = document.getElementById('nav-burger');
        if (p && !p.contains(e.target) && b && !b.contains(e.target)) {
          p.classList.remove('open');
          b.classList.remove('open');
        }
        document.removeEventListener('click', closeMobileNav);
      });
    }, 10);
  }
};

// Action map keyed by tab id — avoids quoting hell in onclick attributes
var _mobileNavActions = {};
window.mobileNavGo = function(id) {
  var panel  = document.getElementById('nav-mobile-panel');
  var burger = document.getElementById('nav-burger');
  if (panel)  panel.classList.remove('open');
  if (burger) burger.classList.remove('open');
  var action = _mobileNavActions[id];
  if (action) setTimeout(function(){ eval(action); }, 50);
};

function Nav() {
  const tabs = [
    {id:'dashboard', label:T('nav.agora'),    icon:'✦',  action:"set({view:'dashboard',phase:0,answered:false})"},
    {id:'session',   label:T('nav.academy'),  icon:'🎓', action:"(currentSession||S.sessionLoading)?set({view:'session',phase:0,answered:false}):startRecommendedSession()"},
    {id:'skills',    label:T('nav.mouseion'), icon:'🗺️', action:"set({view:'skills',phase:0,answered:false})"},
    {id:'reflect',   label:T('nav.stoa'),     icon:'✍️', action:"set({view:'reflect',phase:0,answered:false})"},
    {id:'portfolio', label:'Portfolio',        icon:'🧭', action:"set({view:'portfolio',phase:0,answered:false})"},
    {id:'bioregion',  label:'Bioregion',         icon:'🌍', action:"loadBioregionPage()"},
    {id:'contribute',label:'Syneisféro',       icon:'📖', href:'/contribute'},
    {id:'ekklesia',  label:'Ekklesia',         icon:'🪏', href:'/org'},
    {id:'polis',     label:T('nav.polis'),     icon:'🗳️', action:"goToPolis()"},
  ];

  const learner  = S.learner;
  const navLabel = (learner && learner.avatar_emoji) ? learner.avatar_emoji
    : (learner && learner.display_name ? learner.display_name[0].toUpperCase() : '?');

  const currentTab   = tabs.find(t => t.id === S.view) || tabs[0];
  const currentLabel = currentTab.icon + ' ' + currentTab.label;

  const desktopTabs = tabs.map(t => {
    if (t.href) return `<a href="${t.href}" class="nav-tab" style="text-decoration:none">${t.icon} ${t.label}</a>`;
    return `<button class="nav-tab${S.view===t.id?' on':''}" onclick="${t.action}">${t.icon} ${t.label}</button>`;
  }).join('');

  // Populate action map so onclick just passes a safe id string
  _mobileNavActions = {};
  tabs.forEach(t => { if (t.action) _mobileNavActions[t.id] = t.action; });

  const mobileItems = tabs.map(t => {
    const isOn = S.view === t.id;
    const cls  = 'nav-mobile-item' + (isOn ? ' on' : '');
    if (t.href) return `<a href="${t.href}" class="${cls}"><span class="nav-mobile-icon">${t.icon}</span>${t.label}</a>`;
    return `<button class="${cls}" onclick="mobileNavGo('${t.id}')"><span class="nav-mobile-icon">${t.icon}</span>${t.label}</button>`;
  }).join('');

  return `
  <nav class="nav">
    <a href="/" style="font-size:11px;color:var(--text3);text-decoration:none;white-space:nowrap;padding:4px 8px;border:1px solid var(--border);border-radius:20px;margin-right:4px;transition:color .15s" onmouseover="this.style.color='var(--wave)'" onmouseout="this.style.color='var(--text3)'">← LMBoK</a><div class="logo" style="white-space:nowrap;flex-shrink:0">Surfing the Frequencies</div>
    <div class="nav-tabs">${desktopTabs}</div>
    <div class="nav-current-view">${currentLabel}</div>
    <div class="nav-av" onclick="showProfileMenu(event)"
      style="cursor:pointer;font-size:${(learner && learner.avatar_emoji)?'18px':'14px'}"
      title="${learner?.display_name||'You'}">${navLabel}</div>
    <button id="nav-burger" class="nav-burger" onclick="toggleMobileNav()" aria-label="Menu">
      <span></span><span></span><span></span>
    </button>
  </nav>
  <div id="nav-mobile-panel" class="nav-mobile-panel">
    <div class="nav-mobile-grid">${mobileItems}</div>
  </div>`;
}
// ── Profile dropdown ──────────────────────────────────────────
window.showProfileMenu = function(e) {
  e.stopPropagation();
  var old = document.getElementById('profile-menu');
  if (old) { old.remove(); return; }
  var l = S.learner || {};
  var menu = document.createElement('div');
  menu.id = 'profile-menu';
  menu.style.cssText = 'position:fixed;top:56px;right:16px;background:var(--card);border:1px solid var(--border);border-radius:var(--r);z-index:9999;min-width:210px;box-shadow:0 8px 32px rgba(0,0,0,0.5);overflow:hidden';
  menu.innerHTML =
    '<div style="padding:14px 16px;border-bottom:1px solid var(--border)">'
    + '<div style="font-weight:700;color:var(--text1);font-size:14px">' + (l.display_name||l.username||'Learner') + '</div>'
    + '<div style="color:var(--text3);font-size:12px;margin-top:3px">Lv ' + (S.level||1) + ' · ' + (S.xp||0) + ' XP</div>'
    + '</div>'
    + '<button onclick="showPreferences()" style="width:100%;padding:11px 16px;text-align:left;background:none;border:none;color:var(--text2);font-size:13px;cursor:pointer;border-bottom:1px solid var(--border);display:block">⚙ Preferences</button>'
    + '<button onclick="doLogout()" style="width:100%;padding:11px 16px;text-align:left;background:none;border:none;color:var(--coral);font-size:13px;cursor:pointer;display:block">↪ Sign out</button>';
  document.body.appendChild(menu);
  setTimeout(function() {
    document.addEventListener('click', function close(ev) {
      var m = document.getElementById('profile-menu');
      if (m && !m.contains(ev.target)) { m.remove(); }
      document.removeEventListener('click', close);
    });
  }, 10);
};

// ══════════════════════════════════════════════════
// AVATAR STAGE
// Evolutionary path: Seed→Sprout→Sapling→Grove→Forest→Ecosystem
// Based on XP + breadth across Being/Becoming/Connecting
// ══════════════════════════════════════════════════
function computeAvatarStage(xp, artScores) {
  // Breadth: how many arts have score > 0.05
  var arts = artScores || {};
  var touched = Object.values(arts).filter(function(v){ return v > 0.05; }).length;
  // Domain breadth: at least one art touched in each of the three domains
  var beingArts    = ['move','eat','feel','notice','express'];
  var becomingArts = ['live','listen','give','receive','collaborate'];
  var connectArts  = ['understand','respect','build','grow','consume'];
  var hasBeing    = beingArts.some(function(a){ return (arts[a]||0) > 0.05; });
  var hasBecoming = becomingArts.some(function(a){ return (arts[a]||0) > 0.05; });
  var hasConnect  = connectArts.some(function(a){ return (arts[a]||0) > 0.05; });
  var domainsBreadth = (hasBeing?1:0) + (hasBecoming?1:0) + (hasConnect?1:0);

  if (xp >= 500 && touched >= 12 && domainsBreadth === 3) return { stage:'Ecosystem', icon:'🌍', level:6,
    desc:'A living system in full expression — Being, Becoming and Connecting flow as one.',
    polis:'Global Polis — planetary proposals and cross-bioregion dialogue' };
  if (xp >= 200 && touched >= 9  && domainsBreadth === 3) return { stage:'Forest',    icon:'🌲', level:5,
    desc:'Deep roots, wide canopy — your growth shelters others and reaches across regions.',
    polis:'Regional Polis — watershed and climate-zone level discussion' };
  if (xp >= 100 && touched >= 6  && domainsBreadth >= 2) return { stage:'Grove',      icon:'🌳', level:4,
    desc:'Interconnected and thriving — you support and are supported by your learning community.',
    polis:'Community Polis — local bioregion discussion and proposals' };
  if (xp >= 50  && touched >= 4)                         return { stage:'Sapling',    icon:'🌿', level:3,
    desc:'Growing steadily toward the light — your roots are finding their depth.',
    polis:'Polis: view only — keep growing to unlock discussion' };
  if (xp >= 18  && touched >= 2)                         return { stage:'Sprout',     icon:'🌱', level:2,
    desc:'Breaking through — the first signs of a pattern are emerging.',
    polis:'Polis: view only — keep growing to unlock discussion' };
  return                                                 { stage:'Seed',        icon:'🫘', level:1,
    desc:'Everything begins here — potential in its purest form.',
    polis:'Polis: view only — keep growing to unlock discussion' };
}

// ══════════════════════════════════════════════════
// BIOREGION — seed profiles loaded async from DB
// Profiles were previously hardcoded (BIOREGION_PROFILES constant).
// P17d: moved to bioregion_seed_profiles table; fetched on boot with 24h localStorage cache.
// ══════════════════════════════════════════════════

var _loadedProfiles = [];   // populated by loadBioregionProfiles()

function getBioregionProfile(lat, lng) {
  // Simple bounding-box match — replaces the old per-profile match() functions
  for (var i = 0; i < _loadedProfiles.length; i++) {
    var p = _loadedProfiles[i];
    if (lat >= p.min_lat && lat <= p.max_lat && lng >= p.min_lng && lng <= p.max_lng) {
      return p;
    }
  }
  return null;
}

function _reattachBioregionProfile() {
  // Called after profiles load to wire up profile on a cached bioregion fix
  if (_bioregionState.status === 'done' &&
      _bioregionState.lat != null && _bioregionState.lng != null) {
    _bioregionState.profile = getBioregionProfile(_bioregionState.lat, _bioregionState.lng);
  }
}

function loadBioregionProfiles(onDone) {
  // Check 24h localStorage cache first (instant on return visits)
  try {
    var _cached = localStorage.getItem('fl_bioregion_profiles');
    if (_cached) {
      var _c = JSON.parse(_cached);
      if (_c && _c.ts && (Date.now() - _c.ts) < 86400000 &&
          Array.isArray(_c.profiles) && _c.profiles.length > 0) {
        _loadedProfiles = _c.profiles;
        _reattachBioregionProfile();
        draw();   // update card immediately — cache hit is synchronous so this is safe
        if (onDone) onDone();
        return;
      }
    }
  } catch(e) {}
  // Fetch from server
  fetch('/api/bioregions/seed-profiles')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data && Array.isArray(data.profiles) && data.profiles.length > 0) {
        _loadedProfiles = data.profiles;
        try {
          localStorage.setItem('fl_bioregion_profiles',
            JSON.stringify({ts: Date.now(), profiles: _loadedProfiles}));
        } catch(e) {}
        _reattachBioregionProfile();
        draw();
      }
      if (onDone) onDone();
    })
    .catch(function() {
      // Profiles unavailable — card shows without ecological detail until next load
      if (onDone) onDone();
    });
}

// State for bioregion card — module-level, persists during session
var _bioregionState = (function() {
  // Restore from localStorage if available.
  // Profile object NOT re-attached here — loadBioregionProfiles() does that after
  // seed profiles arrive from DB (or cache). This avoids a sync dependency on DB data.
  try {
    var _stored = localStorage.getItem('fl_bioregion');
    if (_stored) {
      var _parsed = JSON.parse(_stored);
      _parsed.profile = null;   // will be set by _reattachBioregionProfile()
      return _parsed;
    }
  } catch(e) {}
  return { status: 'idle', lat: null, lng: null, placeName: null, profile: null };
})();

function _saveBioregion() {
  try {
    var toSave = { status: _bioregionState.status, lat: _bioregionState.lat,
      lng: _bioregionState.lng, placeName: _bioregionState.placeName, profile: null };
    localStorage.setItem('fl_bioregion', JSON.stringify(toSave));
  } catch(e) {}
}

function resetBioregion() {
  _bioregionState = { status: 'idle', lat: null, lng: null, placeName: null, profile: null };
  try { localStorage.removeItem('fl_bioregion'); } catch(e) {}
  draw();
}

function _saveBioregionToProfile() {
  // Fire-and-forget — writes a BIOREGION line into learner_profile server-side.
  // Builds a compact note from whatever the matched profile contains.
  var bs = _bioregionState;
  if (!bs || bs.status !== 'done') return;
  var parts = [];
  if (bs.profile && bs.profile.name) parts.push(bs.profile.name);
  if (bs.profile && bs.profile.watershed) parts.push(bs.profile.watershed + ' watershed');
  if (bs.profile && bs.profile.climate)   parts.push(bs.profile.climate);
  if (bs.profile && bs.profile.vitality)  parts.push(bs.profile.vitality + ' vitality');
  if (bs.placeName) parts.push(bs.placeName);
  if (parts.length === 0) return;
  var note = parts.join(' · ');
  // Persist canonical bioregion name to learners.bioregion for server-side matching.
  // Use named profile (e.g. "Red River Delta") when available, else city-level placeName.
  var bioregionName = (bs.profile && bs.profile.name) ? bs.profile.name : (bs.placeName || null);
  if (bioregionName) {
    API.patch('/auth/me', { bioregion: bioregionName }).catch(function(){});
  }
  API.post('/generate/profile-update', {
    messages:         [],
    existing_profile: S.learnerProfile || null,
    bioregion_note:   note,
  }).then(function(res){
    if (res && res.status === 'ok') {
      // Reload profile silently so My Story reflects the new bioregion line
      API.get('/learners/me').then(function(me){
        if (me && me.learner_profile) S.learnerProfile = me.learner_profile;
      }).catch(function(){});
    }
  }).catch(function(){});
}

function initBioregion() {
  if (_bioregionState.status === 'loading') return;
  _bioregionState.status = 'loading';
  draw();
  if (!navigator.geolocation) {
    _bioregionState.status = 'denied';
    _saveBioregion();
    draw(); return;
  }
  navigator.geolocation.getCurrentPosition(
    function(pos) {
      var lat = Math.round(pos.coords.latitude  * 10) / 10;  // ~11km precision only
      var lng = Math.round(pos.coords.longitude * 10) / 10;
      _bioregionState.lat = lat;
      _bioregionState.lng = lng;
      _bioregionState.profile = getBioregionProfile(lat, lng);
      // Reverse geocode — city level only, no street
      fetch('https://nominatim.openstreetmap.org/reverse?lat='+lat+'&lon='+lng+'&zoom=10&format=json')
        .then(function(r){ return r.json(); })
        .then(function(d){
          var a = d.address || {};
          _bioregionState.placeName = [a.city||a.town||a.village, a.country].filter(Boolean).join(', ');
          _bioregionState.status = 'done';
          _saveBioregion();
          _saveBioregionToProfile();
          draw();
        })
        .catch(function(){
          _bioregionState.status = 'done';
          _saveBioregion();
          _saveBioregionToProfile();
          draw();
        });
    },
    function() {
      _bioregionState.status = 'denied';
      _saveBioregion();
      draw();
    },
    { enableHighAccuracy: false, timeout: 8000, maximumAge: 3600000 }
  );
}

function renderBioregionCard(avatarStage) {
  var bs = _bioregionState;
  var cardStyle = 'background:linear-gradient(135deg,var(--bg2) 0%,rgba(0,229,200,0.04) 100%);border:1px solid rgba(0,229,200,0.2);border-radius:var(--r);padding:16px;margin-bottom:12px;';

  // ── Avatar stage strip (always shown) ──
  var guidingStarHtml = S.guidingStar
    ? '<div style="font-size:12px;font-style:italic;color:var(--text2);text-align:center;padding:6px 10px;margin-bottom:10px;line-height:1.5;border-bottom:1px solid var(--border)">✦ '+S.guidingStar+'</div>'
    : '';
  var stageBar = '<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--border)">'
    + '<span style="font-size:22px">'+avatarStage.icon+'</span>'
    + '<div style="flex:1">'
    + '<div style="font-size:13px;font-weight:700;color:var(--wave);font-family:var(--font-display)">'+avatarStage.stage+'</div>'
    + '<div style="font-size:11px;color:var(--text3);line-height:1.5;margin-top:2px">'+avatarStage.desc+'</div>'
    + '</div>'
    + '<div style="font-size:10px;color:var(--text3);background:var(--bg3);border-radius:20px;padding:3px 9px;white-space:nowrap">Lv '+avatarStage.level+' / 6</div>'
    + '</div>'
    + '<div style="font-size:10px;color:var(--text3);margin-bottom:10px;line-height:1.5;padding:6px 10px;background:var(--bg3);border-radius:6px;border-left:2px solid var(--wave)">'
    + '<span style="font-weight:600;color:var(--wave)">Polis access · </span>'+avatarStage.polis
    + '</div>';

  // ── Bioregion section ──
  var bioHtml = '';
  if (bs.status === 'idle') {
    bioHtml = '<div style="text-align:center;padding:8px 0">'
      + '<div style="font-size:12px;color:var(--text2);margin-bottom:10px">Where on this earth are you surfing from?</div>'
      + '<button onclick="initBioregion()" style="font-size:12px;padding:7px 18px;background:rgba(0,229,200,0.12);border:1px solid rgba(0,229,200,0.3);color:var(--wave);border-radius:20px;cursor:pointer">Locate my bioregion</button>'
      + '<div style="font-size:10px;color:var(--text3);margin-top:6px">City-level only · never stored · your data stays on your device</div>'
      + '</div>';
  } else if (bs.status === 'loading') {
    bioHtml = '<div style="font-size:12px;color:var(--text3);text-align:center;padding:10px 0">Locating your bioregion…</div>';
  } else if (bs.status === 'denied') {
    bioHtml = '<div style="font-size:11px;color:var(--text3);line-height:1.6;padding:6px 0">'
      + 'Location access declined — that\'s fine. You can describe your bioregion below when learner profiles open up.'
      + '</div>';
  } else if (bs.status === 'done') {
    var p = bs.profile;
    if (p) {
      bioHtml = '<div style="margin-bottom:6px">'
        + '<div style="font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text3);margin-bottom:8px">Your Bioregion</div>'
        // Name row
        + '<div style="font-size:14px;font-weight:700;color:var(--text);font-family:var(--font-display);margin-bottom:2px">'+p.name+'</div>'
        + (bs.placeName ? '<div style="font-size:11px;color:var(--text3);margin-bottom:6px">'+bs.placeName+'</div>' : '')
        // Colonial / archaic
        + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:10px">'
        + '<div style="background:var(--bg3);border-radius:6px;padding:7px 9px">'
        + '<div style="font-size:9px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--text3);margin-bottom:3px">Current construct</div>'
        + '<div style="font-size:11px;color:var(--text2)">'+p.colonial+'</div>'
        + '</div>'
        + '<div style="background:rgba(0,229,200,0.06);border:1px solid rgba(0,229,200,0.15);border-radius:6px;padding:7px 9px">'
        + '<div style="font-size:9px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--wave);margin-bottom:3px">Deeper roots</div>'
        + '<div style="font-size:11px;color:var(--text)">'+p.archaic+'</div>'
        + '</div>'
        + '</div>'
        // Natural identity rows
        + '<div style="font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--text3);margin-bottom:6px">Natural identity</div>'
        + _bioRow('🌦','Climate', p.climate)
        + _bioRow('💧','Watershed', p.watershed)
        + _bioRow('🌋','Tectonic', p.tectonic)
        + _bioRow('🦅','Keystone species', p.species)
        + _bioRow('🌱','Soil', p.soil)
        + _bioRow('⛏','Natural resources', p.resources || '—')
        + _bioRow('💚','Vitality', p.vitality, p.vitality.startsWith('Critical')?'#E88080':p.vitality.startsWith('Stressed')?'#E8A87C':p.vitality.startsWith('At risk')?'#E8A87C':'var(--wave)')
        + _bioRow('🔗','Connections', p.connections)
        + _refreshBtn()
        + '</div>';
    } else {
      // Location found but no seed profile yet
      bioHtml = '<div style="font-size:11px;color:var(--text2);line-height:1.6;padding:4px 0">'
        + (bs.placeName ? '<div style="font-size:13px;font-weight:600;color:var(--text);margin-bottom:6px">'+bs.placeName+'</div>' : '')
        + 'No seed profile yet for this bioregion. '
        + 'You know this land — its rhythms, its waters, its living systems. '
        + '<span onclick="loadBioregionPage()" style="color:var(--wave);cursor:pointer;text-decoration:underline">Add your voice to the Bioregion page →</span>'
        + '<div style="font-size:10px;color:var(--text3);margin-top:6px">~'+bs.lat+'° N, '+Math.abs(bs.lng)+'° '+(bs.lng>=0?'E':'W')+'</div>'
        + _refreshBtn()
        + '</div>';
    }
  }

  return '<div style="'+cardStyle+'">'
    + '<div style="font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text3);margin-bottom:12px;text-align:center">Avatar</div>'
    + stageBar
    + guidingStarHtml
    + bioHtml
    + '</div>';
}

function _bioRow(icon, label, value, valueColor) {
  return '<div style="display:flex;gap:7px;padding:4px 0;border-bottom:1px solid var(--border);align-items:flex-start">'
    + '<span style="font-size:12px;flex-shrink:0;margin-top:1px">'+icon+'</span>'
    + '<div style="flex:1">'
    + '<span style="font-size:10px;font-weight:600;color:var(--text3)">'+label+' · </span>'
    + '<span style="font-size:11px;color:'+(valueColor||'var(--text2)')+'">'+value+'</span>'
    + '</div></div>';
}

function _refreshBtn() {
  return '<div style="text-align:right;margin-top:10px">'
    + '<button onclick="resetBioregion()" style="font-size:10px;padding:4px 12px;background:transparent;border:1px solid var(--border2);color:var(--text3);border-radius:20px;cursor:pointer">↺ Refresh my bioregion</button>'
    + '</div>';
}

// ══════════════════════════════════════════════════
// DASHBOARD (Agora)
// 3-column layout: [Radar+Stats] | [Journey+Rec+Domains] | [Match+Achievements]
// ══════════════════════════════════════════════════
function Dashboard() {
  const learner = S.learner || {};
  const name    = learner.display_name || 'Learner';

  // Skills touched — from backend /sessions/skills-touched; falls back to client-side estimate
  const skillsTouched = S.skillsTouched != null
    ? S.skillsTouched
    : Object.keys(SKILL_ART_WEIGHTS || {}).filter(function(sk){ return computeSkillScore(sk, S.artScores||{}) > 0; }).length;

  // Arts touched — arts with score > 0.05
  const artsTouched = Object.values(S.artScores||{}).filter(function(v){ return v > 0.05; }).length;

  // Hours — total_minutes from backend (via weekMinutes state field)
  const _hoursRaw = Math.round((S.weekMinutes||0) / 60);
  const hoursStr  = _hoursRaw > 0 ? _hoursRaw + 'h' : '0h';

  // Today's journey — real session data from /sessions/today
  var _td = S.todaySessions;
  var journeySteps;
  if (_td && _td.sessions) {
    journeySteps = _td.sessions.map(function(s) {
      var mins = s.duration_seconds ? Math.round(s.duration_seconds/60) : 0;
      return {
        i: '✓',
        l: s.title || ('The Art of ' + s.art_name),
        s: s.art_name + (mins ? ' · ' + mins + 'min' : '') + ' · +' + (s.xp_earned||0) + ' XP',
        done: true,
      };
    });
    // Append next recommended session as the upcoming step
    if (S.nextRec) {
      journeySteps.push({
        i: String(journeySteps.length + 1),
        l: S.nextRec.title || ('The Art of ' + S.nextRec.art_name),
        s: (S.nextRec.subcategory || S.nextRec.skill_name || '') + ' · ~' + (S.nextRec.duration_min||15) + 'min',
        done: false,
      });
    }
    if (journeySteps.length === 0) {
      journeySteps.push({i:'①', l:'Start your first wave', s:'Pick any art to begin', done: false});
    }
  } else {
    // Fallback proxy while loading
    var _sessionsDone = Math.floor((S.xp||0) / 18);
    journeySteps = [
      {i:'✓', l:'First session',  s:'Explore an art',       done: _sessionsDone >= 1},
      {i:'▶', l:'Second wave',    s:'Deepen the practice',  done: _sessionsDone >= 2},
      {i:'○', l:'Reflect',        s:'Journal your insight', done: false},
    ];
  }

  // Strongest 4 domains for bar chart
  const _domScores = computeDomainScores(S.artScores||{});
  const _domEntries = Object.keys(_domScores)
    .map(function(k){ return [k, _domScores[k]]; })
    .sort(function(a,b){ return b[1]-a[1]; })
    .slice(0,4);
  const _domColors = {
    cognitive:'#5B8DD9', creative:'#E8A87C', physical:'#6DB97A', social:'#9B8EC4',
    language:'#4FC3C3',  emotional:'#E88080', meta:'#D4C14A',   technical:'#7BADB8',
  };
  const _domLabels = {
    cognitive:'Cognitive & Intellectual', creative:'Creative & Artistic', physical:'Physical & Motor', social:'Social & Relational',
    language:'Language & Communication', emotional:'Emotional & Psychological', meta:'Meta-Learning', technical:'Technical & Digital',
  };

  // Strongest Arts — for the domains/arts toggle (reuses _domColors/_domLabels above)
  const _artEmojis = {
    move:'🏃', eat:'🍎', feel:'💙', notice:'👁️', express:'🎨',
    live:'🌍', listen:'👂', give:'🎁', receive:'📥', collaborate:'🤝',
    understand:'🔍', respect:'🙏', build:'🔨', grow:'🌱', consume:'📚',
  };
  const _topArts = Object.keys(S.artScores||{})
    .filter(function(k){ return (S.artScores[k]||0) > 0; })
    .sort(function(a,b){ return (S.artScores[b]||0)-(S.artScores[a]||0); })
    .slice(0,5);

  // Avatar stage — computed from XP + art breadth
  const _avatarStage = computeAvatarStage(S.xp || 0, S.artScores || {});

  return `
  <div class="page">
    <!-- ── Page header — title | stat bar | paddle in ──────────────────────── -->
    <div class="dash-header" style="display:flex;align-items:center;gap:16px;margin-bottom:14px">
      <div style="flex-shrink:0">
        <h1 style="font-size:clamp(18px,2.5vw,30px);line-height:1.2">${name}'s Waves</h1>
        <p style="margin-top:4px;font-size:12px;color:var(--text2)">
          <span onclick="showLMBoKInfo()" style="color:var(--wave);cursor:pointer;border-bottom:1px dashed rgba(0,229,200,0.5);white-space:nowrap" title="Click to learn more">Your Very Own Life Management Body of Knowledge (LMBoK)</span>
        </p>
      </div>
      <!-- Stat bar — inline center -->
      <div class="stat-box" style="flex:1;display:grid;grid-template-columns:1fr 1fr 1fr;gap:0;padding:8px 6px">
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;border-right:1px solid var(--border)">
          <span class="stat-v" style="color:var(--deep);font-size:17px;line-height:1">${S.xp||0}</span>
          <span style="font-size:12px;font-weight:700;color:var(--text2)">Points</span>
        </div>
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;border-right:1px solid var(--border)">
          <span class="stat-v" style="color:var(--coral);font-size:17px;line-height:1">${hoursStr}</span>
          <span style="font-size:12px;font-weight:700;color:var(--text2)">Learning</span>
        </div>
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;padding:3px 0">
          <div style="display:flex;align-items:center;gap:6px">
            <span class="stat-v" style="color:var(--wave);font-size:17px;line-height:1">${artsTouched}</span>
            <span style="font-size:12px;font-weight:700;color:var(--text2)">Arts</span>
          </div>
          <div style="display:flex;align-items:center;gap:6px">
            <span class="stat-v" style="color:var(--wave);font-size:17px;line-height:1">${skillsTouched}</span>
            <span style="font-size:12px;font-weight:700;color:var(--text2)">Skills</span>
          </div>
        </div>
      </div>
      <button class="btn btn-wave btn-lg" style="flex-shrink:0" onclick="startRecommendedSession()">▶ Paddle in</button>
    </div>

    <!-- ── 3-column grid ─────────────────────────────────────────
         LEFT (order-1):   Radar + Strongest Arts/Domains + Today's Journey
         MIDDLE (order-2): Level/XP + Hours · Recommended Next · New Match
         RIGHT (order-3):  Where I Stand (Avatar · Bioregion)
         Responsive: columns stack in order 1→2→3 on narrow viewports
    ──────────────────────────────────────────────────────────── -->
    <div class="dash-grid" style="display:grid;grid-template-columns:minmax(0,1.08fr) minmax(0,1fr) minmax(0,0.88fr);gap:14px;align-items:start">

      <!-- ══ COL 1: Radar → Strongest Domains/Arts ══ -->
      <div class="dash-col-1" style="display:flex;flex-direction:column;gap:12px;order:1">

        <!-- Radar — entire card navigates to Mouseion; toggles stop propagation -->
        <div class="dash-card-radar card card-wave" style="padding:12px 12px 16px;cursor:pointer;transition:box-shadow .2s"
          onclick="set({view:'skills'})"
          onmouseover="this.style.boxShadow='0 0 28px rgba(0,229,200,0.28)'"
          onmouseout="this.style.boxShadow='var(--glow-wave)'">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <h4>${S.radarTab==='avatar' ? 'Human Signature' : 'Learning Domains'}</h4>
            <div style="display:flex;gap:3px" onclick="event.stopPropagation()">
              <button onclick="set({radarTab:'avatar'})"
                style="padding:2px 8px;border-radius:10px;border:1px solid ${S.radarTab==='avatar'?'var(--wave)':'var(--border2)'};background:${S.radarTab==='avatar'?'rgba(0,229,200,0.12)':'transparent'};color:${S.radarTab==='avatar'?'var(--wave)':'var(--text3)'};font-size:10px;cursor:pointer;font-family:var(--font-body)">Arts</button>
              <button onclick="set({radarTab:'domains'})"
                style="padding:2px 8px;border-radius:10px;border:1px solid ${S.radarTab==='domains'?'var(--wave)':'var(--border2)'};background:${S.radarTab==='domains'?'rgba(0,229,200,0.12)':'transparent'};color:${S.radarTab==='domains'?'var(--wave)':'var(--text3)'};font-size:10px;cursor:pointer;font-family:var(--font-body)">Domains</button>
            </div>
          </div>
          <div style="display:flex;justify-content:center">
            ${S.radarTab==='avatar' ? radarArts(S.artScores||{}) : radarDomains(computeDomainScores(S.artScores||{}))}
          </div>
        </div>

        <!-- Strongest Arts / Domains — tabbed toggle -->
        <div class="dash-card-domains card">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
            <h4>${S.domainTab==='domains' ? 'Strongest domains' : 'Strongest arts'}</h4>
            <div style="display:flex;gap:3px">
              <button onclick="set({domainTab:'arts'})"
                style="padding:2px 8px;border-radius:10px;border:1px solid ${S.domainTab!=='domains'?'var(--wave)':'var(--border2)'};background:${S.domainTab!=='domains'?'rgba(0,229,200,0.12)':'transparent'};color:${S.domainTab!=='domains'?'var(--wave)':'var(--text3)'};font-size:10px;cursor:pointer;font-family:var(--font-body)">Arts</button>
              <button onclick="set({domainTab:'domains'})"
                style="padding:2px 8px;border-radius:10px;border:1px solid ${S.domainTab==='domains'?'var(--wave)':'var(--border2)'};background:${S.domainTab==='domains'?'rgba(0,229,200,0.12)':'transparent'};color:${S.domainTab==='domains'?'var(--wave)':'var(--text3)'};font-size:10px;cursor:pointer;font-family:var(--font-body)">Domains</button>
            </div>
          </div>
          ${(function(){
            if (S.domainTab === 'arts') {
              if (_topArts.length === 0) return '<div style="font-size:12px;color:var(--text3);text-align:center;padding:8px 0">Complete sessions to see your strongest arts</div>';
              return _topArts.map(function(slug){
                var score = S.artScores[slug]||0;
                var pct   = Math.round(score*100);
                var datum = (ARTS_DATA||[]).find(function(x){return x.slug===slug;});
                var lbl   = datum ? datum.name : (slug.charAt(0).toUpperCase()+slug.slice(1));
                var emoji = (_artEmojis||{})[slug]||'🌊';
                var col   = datum && datum.group==='Being' ? 'var(--wave)' : datum && datum.group==='Becoming' ? 'var(--deep)' : 'var(--gold)';
                return '<div style="margin-bottom:10px">'
                  +'<div style="display:flex;justify-content:space-between;margin-bottom:4px;align-items:center">'
                  +'<span style="font-size:12px;color:var(--text2)">'+emoji+' '+lbl+'</span>'
                  +'<span style="font-size:12px;font-weight:600;color:'+col+'">'+pct+'%</span>'
                  +'</div>'
                  +'<div class="bar-bg" style="height:4px">'
                  +'<div class="bar-f" style="width:'+Math.max(pct,3)+'%;background:'+col+'"></div>'
                  +'</div></div>';
              }).join('');
            }
            // Domains tab (default)
            if (_domEntries.every(function(e){return e[1]===0;}))
              return '<div style="font-size:12px;color:var(--text3);text-align:center;padding:8px 0">Complete sessions to unlock your domain profile</div>';
            return _domEntries.map(function(entry){
              var key=entry[0], val=entry[1];
              var col = _domColors[key]||'var(--wave)';
              var lbl = _domLabels[key]||key;
              var pct = Math.round(val*100);
              return '<div style="margin-bottom:10px">'
                +'<div style="display:flex;justify-content:space-between;margin-bottom:4px">'
                +'<span style="font-size:12px;color:var(--text2)">'+lbl+'</span>'
                +'<span style="font-size:12px;font-weight:600;color:'+col+'">'+pct+'%</span>'
                +'</div>'
                +'<div class="bar-bg" style="height:4px">'
                +'<div class="bar-f" style="width:'+Math.max(pct,3)+'%;background:'+col+'"></div>'
                +'</div></div>';
            }).join('');
          })()}
        </div>

      </div>

      <!-- ══ COL 2: Recommended Next → Today's Journey → New Match ══ -->
      <div class="dash-col-2" style="display:flex;flex-direction:column;gap:12px;order:2">

        <!-- Recommended next — entire card clickable, no Start button -->
        <div class="dash-card-rec card" style="background:linear-gradient(135deg,rgba(0,229,200,0.07),rgba(61,123,255,0.08));border-color:rgba(0,229,200,0.2);cursor:pointer;transition:border-color .2s,box-shadow .2s"
          onclick="startDirectSession(S.nextRec && S.nextRec.art_slug)"
          onmouseover="this.style.borderColor='rgba(0,229,200,0.4)';this.style.boxShadow='0 0 24px rgba(0,229,200,0.15)'"
          onmouseout="this.style.borderColor='rgba(0,229,200,0.2)';this.style.boxShadow='none'">
          <h4 style="margin-bottom:6px">Recommended next</h4>
          <div style="font-family:var(--font-display);font-size:17px;font-weight:700;margin-bottom:4px;color:var(--text)">
            ${S.nextRec ? 'The Art of ' + S.nextRec.art_name : 'The Art of Growing'}
          </div>
          <div style="font-size:12px;color:var(--text2);margin-bottom:6px">
            ${(function(){ if(!S.nextRec) return 'Regenerative agriculture · Connecting'; var _g=(ARTS_DATA||[]).find(function(x){return x.slug===S.nextRec.art_slug;}); return (S.nextRec.subcategory||S.nextRec.skill_name||S.nextRec.art_name||'')+' · '+((_g&&_g.group)||'Connecting'); })()}
          </div>
          ${S.nextRec && S.nextRec.reasoning ? `<div style="font-size:11px;color:var(--text3);font-style:italic;margin-bottom:8px;line-height:1.5">${S.nextRec.reasoning}</div>` : ''}
          <div style="display:flex;gap:6px;flex-wrap:wrap">
            <span class="pill pw">▲ ${S.nextRec ? S.nextRec.skill_name : 'Grow'}</span>
            <span class="pill pgr">~${S.nextRec ? S.nextRec.duration_min : 20} min</span>
            ${S.nextRec ? `<span class="pill pgr">Lv ${S.nextRec.current_level}→${S.nextRec.target_level}</span>` : ''}
          </div>
        </div>

        <!-- Today's journey -->
        <div class="dash-card-journey card">
          <h4 style="margin-bottom:12px">Today's journey</h4>
          ${journeySteps.map(t=>`
          <div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);opacity:${t.done?0.5:1}">
            <div style="width:28px;height:28px;border-radius:50%;flex-shrink:0;
              background:${t.done?'var(--wave-dim)':'var(--bg4)'};
              display:flex;align-items:center;justify-content:center;
              color:${t.done?'var(--wave)':'var(--text3)'};font-size:11px">${t.i}</div>
            <div style="flex:1">
              <div style="font-size:13px;font-weight:${!t.done?600:400};color:var(--text)">${t.l}</div>
              <div style="font-size:11px;color:var(--text3)">${t.s}</div>
            </div>
          </div>`).join('')}
        </div>

        <!-- New Match ✦ -->
        <div class="dash-card-match">${(function() {
          var m = S.topMatch;
          if (!m) return '<div style="background:linear-gradient(135deg,rgba(155,114,255,0.10),rgba(61,123,255,0.08));'
            +'border:1px solid rgba(155,114,255,0.25);border-radius:var(--r);padding:15px;'
            +'cursor:pointer;opacity:0.7" onclick="window.location.href=\'/org\'">'
            +'<div style="font-size:10px;font-weight:700;color:#9B72FF;margin-bottom:5px;text-transform:uppercase;letter-spacing:1px">New Match \u2726</div>'
            +'<div style="font-size:13px;color:var(--text2)">'+(S.matchLoaded ? 'Browse opportunities \u2192' : 'Loading matches\u2026')+'</div>'
            +'</div>';
          var artName = function(slug) {
            var a = (ARTS_DATA||[]).find(function(x){return x.slug===slug;});
            return a ? a.name : (slug.charAt(0).toUpperCase()+slug.slice(1));
          };
          var metPills = (m.arts_met||[]).map(function(s){ return '<span class="pill pw">\u2713 '+artName(s)+'</span>'; }).join('');
          var gapPills = (m.arts_gap||[]).map(function(s){ return '<span class="pill pa">\u223c '+artName(s)+'</span>'; }).join('');
          return '<div style="background:linear-gradient(135deg,rgba(155,114,255,0.12),rgba(61,123,255,0.10));'
            +'border:1px solid rgba(155,114,255,0.3);border-radius:var(--r);padding:15px;cursor:pointer;transition:box-shadow .2s" '
            +'onclick="window.location.href=\'/org\'" '
            +'onmouseover="this.style.boxShadow=\'0 0 24px rgba(155,114,255,0.25)\'" '
            +'onmouseout="this.style.boxShadow=\'\'">'
            +'<div style="font-size:10px;font-weight:700;color:#9B72FF;margin-bottom:5px;text-transform:uppercase;letter-spacing:1px">New Match \u2726</div>'
            +'<div style="font-family:var(--font-display);font-weight:600;margin-bottom:3px;color:var(--text)">'+m.title+'</div>'
            +'<div style="font-size:12px;color:var(--text2);margin-bottom:9px;line-height:1.5">'+m.description.slice(0,80)+(m.description.length>80?'\u2026':'')+'</div>'
            +'<div style="display:flex;gap:5px;flex-wrap:wrap">'+metPills+gapPills+'</div>'
            +'<div style="font-size:11px;color:var(--text3);margin-top:8px">Match score: '+m.match_score+'%</div>'
            +'</div>';
        })()} </div>

      </div>

      <!-- ══ COL 3: Where I Stand (Avatar · Bioregion) ══ -->
      <div class="dash-col-3 dash-col-r" style="display:flex;flex-direction:column;gap:12px;order:3">

        <!-- Avatar + Bioregion card -->
        <div class="dash-card-avatar">${renderBioregionCard(_avatarStage)}</div>

      </div>

    </div>
    ${S.showPolisGate ? `
    <div style="position:fixed;bottom:24px;left:50%;transform:translateX(-50%);
      background:var(--bg3);border:1px solid var(--polis,#7B5EA7);border-radius:var(--r);
      padding:16px 24px;max-width:400px;text-align:center;z-index:200;
      box-shadow:0 8px 32px rgba(0,0,0,0.4)">
      <div style="font-family:var(--font-display);font-weight:700;margin-bottom:6px">The Polis opens with practice</div>
      <div style="font-size:13px;color:var(--text2);line-height:1.6">
        Complete 5 learning days or earn 50 XP to unlock civic participation.
        The Polis works best when its members have practiced listening, understanding and respect.
      </div>
    </div>` : ''}
  </div>`;
}

// ══════════════════════════════════════════════════
// SESSION (Academy) — 5-phase learning session
// ══════════════════════════════════════════════════
const phaseNames = ['Warm-up','Explore','Challenge','Reflect','Assess'];

function phaseBody(p) {
  if(p===0) {
    var warmup = currentSession ? currentSession.warmup_prompt
      : 'Welcome to the Academy. Today we explore <strong>the art of growing</strong> — learning to work with the land, not against it. Permaculture teaches us that healthy systems are diverse, connected and self-renewing. So are healthy humans. Ready to surf this frequency?';
    var artName = currentSession ? currentSession.art_name : 'Growing';
    var title   = currentSession ? currentSession.title : 'The Art of Growing';
    var _aSlug  = (currentSession && currentSession.art_slug) || (S.nextRec && S.nextRec.art_slug) || 'grow';
    var _aDatum = (ARTS_DATA || []).find(function(x){ return x.slug === _aSlug; });
    var artGroup     = _aDatum ? _aDatum.group : 'Connecting';
    var artGroupPill = artGroup === 'Being' ? 'pw' : artGroup === 'Becoming' ? 'pd' : 'pa';
    return `
    <div class="tutor-row"><div class="tutor-icon">🌊</div>
    <div class="tutor-bubble">${warmup}</div></div>
    <div class="card" style="margin-bottom:14px">
      <h3 style="margin-bottom:8px">${title}</h3>
      <p style="line-height:1.7;color:var(--text2)">The art of ${artName} · ${artGroup} · reflection</p>
    </div>
    <div style="display:flex;gap:7px;flex-wrap:wrap">
      <span class="pill ${artGroupPill}">${artGroup}</span>
      <span class="pill pw">${artName}</span>
      <span class="pill pgr">~20 min</span>
    </div>`;
  }
  if(false && p===0) return `
    <div class="tutor-row"><div class="tutor-icon">🌊</div>
    <div class="tutor-bubble">
      Welcome to the Academy. Today we explore <strong>the art of growing</strong> — learning to work with the land,
      not against it. Permaculture teaches us that healthy systems are diverse, connected and self-renewing.
      So are healthy humans. Ready to surf this frequency?
    </div></div>
    <div class="card" style="margin-bottom:14px">
      <h3 style="margin-bottom:8px">Today's session</h3>
      <p style="line-height:1.7">Regenerative agriculture · ecosystems as teachers · designing for abundance · reflection on your relationship with food and land</p>
    </div>
    <div style="display:flex;gap:7px;flex-wrap:wrap">
      <span class="pill pa">Connecting</span>
      <span class="pill pw">Grow</span>
      <span class="pill pgr">~20 min</span>
    </div>`;

  if(p===1) {
    // FIX: was showing hardcoded permaculture quiz below the AI content —
    // removed the static cards so only the AI explore_content renders.
    var explore = currentSession ? currentSession.explore_content
      : 'In permaculture there is a principle: <em>observe and interact</em>. Before you change anything, you watch. A skilled farmer doesn&#39;t fight their land — they listen to it. The same is true of learning. The most important thing you can do right now is notice what&#39;s already here.';
    return `
    <div class="tutor-row"><div class="tutor-icon">🌊</div>
    <div class="tutor-bubble">${explore}</div></div>
    <p style="font-size:12px;color:var(--text3);margin-top:12px">Take a moment to sit with this. The next phase will invite you to put it into practice.</p>`;
  }
  if(false && p===1) return `
    <div class="tutor-row"><div class="tutor-icon">🌊</div>
    <div class="tutor-bubble">
      In permaculture there is a principle: <em>observe and interact</em>. Before you change anything,
      you watch. A skilled farmer doesn't fight their land — they listen to it.
      The same is true of learning. The most important thing you can do right now is notice what's already here.
    </div></div>
    <div class="card" style="margin-bottom:12px">
      <p style="font-size:13px;color:var(--text2);margin-bottom:12px">Which of these best describes a healthy ecosystem?</p>
      <button class="choice-btn" id="r0" onclick="tapR('r0',false)">One dominant species that controls all others</button>
      <button class="choice-btn" id="r1" onclick="tapR('r1',true)">Many diverse species in interdependent relationships</button>
      <button class="choice-btn" id="r2" onclick="tapR('r2',false)">A system that requires constant human intervention</button>
      <div id="rfb" style="font-size:13px;margin-top:6px;min-height:18px;color:var(--text2)"></div>
    </div>
    <p style="font-size:12px;color:var(--text3)">The answer is the same for human communities.</p>`;

  if(p===2) {
    var challenge = currentSession ? currentSession.challenge_prompt
      : 'Design a small growing space using at least three permaculture principles. Describe what you&#39;d plant, why, and how each element supports the others.';
    return `
    <div class="tutor-row"><div class="tutor-icon">🌊</div>
    <div class="tutor-bubble">${challenge}</div></div>
    <div class="card">
      <p style="font-size:13px;color:var(--text2);margin-bottom:8px">Your response:</p>
      <textarea id="ctxt" rows="5"
        placeholder="Write freely — there is no single right answer..." oninput="S.challengeText=this.value"></textarea>
    </div>
    <div class="card" style="margin-top:12px;border-left:3px solid var(--wave)">
      <div style="display:flex;align-items:center;gap:8px;cursor:pointer;user-select:none"
           onclick="S.sandboxOpen=!S.sandboxOpen;S.sandboxMessages=S.sandboxOpen?S.sandboxMessages:[];set({})">
        <span style="font-size:15px">🌊</span>
        <span style="font-size:13px;font-weight:600;color:var(--wave);font-family:var(--font-display)">Explore with the companion</span>
        <span style="font-size:11px;color:var(--text3);margin-left:auto">${S.sandboxOpen?'▲ close':'▼ open'}</span>
      </div>
      ${S.sandboxOpen ? '<div style="margin-top:12px">'+renderSandboxThread('sandbox-challenge-input','Challenge',false)+'</div>' : ''}
    </div>`;
  }
  if(false && p===2) return `
    <div class="tutor-row"><div class="tutor-icon">🌊</div>
    <div class="tutor-bubble">
      Your challenge: design a small growing space — a windowsill, a balcony corner, a backyard patch —
      using at least three permaculture principles. Describe what you'd plant, why, and how each element
      supports the others.
    </div></div>
    <div class="card">
      <p style="font-size:13px;font-weight:500;color:var(--text2);margin-bottom:5px">Three permaculture principles to consider:</p>
      <p style="font-size:12px;color:var(--text3);margin-bottom:14px;line-height:1.7">
        <strong style="color:var(--wave)">Diversity</strong> — multiple species support each other ·
        <strong style="color:var(--wave)">Edge effect</strong> — the most life happens at boundaries ·
        <strong style="color:var(--wave)">Closed loops</strong> — waste from one element feeds another
      </p>
      <p style="font-size:13px;color:var(--text2);margin-bottom:8px">Describe your growing space:</p>
      <textarea id="ctxt" rows="4"
        placeholder="e.g. A windowsill herb garden: basil, mint and chives together because..."
        oninput="S.challengeText=this.value"></textarea>
    </div>`;

  if(p===3) {
    // FIX: reflectQ was defined but never used — hardcoded Grow question and
    // preset buttons were rendered instead. Now uses AI reflect_prompt and
    // gives the learner a free-text textarea for genuine introspection.
    var reflectQ = currentSession ? currentSession.reflect_prompt
      : 'What connection do you notice between growing food and building community?';
    const w = S.challengeText || '"A small herb garden where each plant supports the others — the way a good community works."';
    return `
    <div class="tutor-row"><div class="tutor-icon">🌊</div>
    <div class="tutor-bubble">
      Beautiful. You just created something real. Now let's go deeper — reflection is where the real roots form.
    </div></div>
    <div class="card" style="margin-bottom:14px">
      <p style="font-size:13px;color:var(--text2);margin-bottom:6px">Your response:</p>
      <p style="font-size:15px;font-style:italic;line-height:1.8;border-left:3px solid var(--wave);padding-left:13px">${w}</p>
    </div>
    <div class="card">
      <p style="font-size:13px;font-weight:500;margin-bottom:11px">${reflectQ}</p>
      <textarea id="rtxt" rows="4"
        placeholder="Write freely — there is no wrong answer here..." oninput="S.reflectText=this.value"></textarea>
    </div>
    <div class="card" style="margin-top:12px;border-left:3px solid var(--deep)">
      <div style="display:flex;align-items:center;gap:8px;cursor:pointer;user-select:none"
           onclick="S.sandboxOpen=!S.sandboxOpen;S.sandboxMessages=S.sandboxOpen?S.sandboxMessages:[];set({})">
        <span style="font-size:15px">🌊</span>
        <span style="font-size:13px;font-weight:600;color:var(--deep);font-family:var(--font-display)">Go deeper with the companion</span>
        <span style="font-size:11px;color:var(--text3);margin-left:auto">${S.sandboxOpen?'▲ close':'▼ open'}</span>
      </div>
      ${S.sandboxOpen ? '<div style="margin-top:12px">'+renderSandboxThread('sandbox-reflect-input','Reflect',false)+'</div>' : ''}
    </div>`;
  }

  if(p===4) {
    var aq = currentSession && currentSession.assess_question ? currentSession.assess_question : {
      question: 'What does "closed loop" mean in permaculture?',
      options: [
        'Keeping a garden fenced off from animals',
        'Designing so waste from one element becomes food for another',
        'Planting in rows with no gaps between plants',
        'Using only seeds from the same plant each year',
      ],
      correct_index: 1,
    };
    return `
    <div class="tutor-row"><div class="tutor-icon">🌊</div>
    <div class="tutor-bubble">One last wave. Your honest best — this helps me know where to take you next.</div></div>
    <div class="card" style="margin-bottom:14px">
      <p style="font-size:15px;font-weight:500;margin-bottom:13px">${aq.question}</p>
      ${aq.options.map((opt,i) => `<button class="choice-btn" id="a${i}" onclick="chkA('a${i}',${i===aq.correct_index},${i})">${opt}</button>`).join('')}
      <div id="afb" style="font-size:13px;margin-top:9px;min-height:18px"></div>
      <details style="margin-top:12px">
        <summary style="font-size:12px;color:var(--wave);cursor:pointer;list-style:none;display:flex;align-items:center;gap:5px">
          <span style="border:1px solid var(--wave);border-radius:50%;width:16px;height:16px;display:inline-flex;align-items:center;justify-content:center;font-size:10px">i</span>
          What's this question about?
        </summary>
        <div style="font-size:13px;color:var(--text2);margin-top:8px;padding:10px;background:rgba(0,229,200,0.05);border-left:2px solid var(--wave);border-radius:0 6px 6px 0;line-height:1.7">
          ${currentSession ? currentSession.explore_content : ''}
        </div>
      </details>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px">
      <div class="stat-box"><div class="stat-v" style="color:var(--wave)">+18 xp</div><div class="stat-l">this session</div></div>
      <div class="stat-box"><div class="stat-v" style="font-size:16px;color:var(--gold);font-family:var(--font-display)">${currentSession ? currentSession.art_name : 'Grow'}</div><div class="stat-l">art progressing</div></div>
    </div>
    <div id="complete-btn-wrap" style="display:none"><button class="btn btn-wave btn-full" onclick="finishSession()">Complete session \u2192</button></div>`;
  }
  return '';
}

// ── AI Session state ─────────────────────────────────────────
var currentSession = null;  // stores generated session data
var sessionLoading = false;
var lastSessionArtSlug = null;  // saved for retry — preserves skill context on Groq failure

async function loadAISession(artSlug) {
  if (sessionLoading) return;
  sessionLoading = true;
  set({sessionLoading: true});

  // Determine art slug — prefer engine recommendation, then onboarding choice
  var slug = artSlug
    || (S.nextRec && S.nextRec.art_slug)
    || S.onboardArt
    || 'grow';
  lastSessionArtSlug = slug;  // save so retryLastSession() can replay without clearing skill context

  // Build learner context for personalisation
  var learnerInterests = '';
  if (S.learner && S.learner.display_name) {
    learnerInterests = 'Learner name: ' + S.learner.display_name + '. ';
  }
  if (S.mouseionThought && S.mouseionThought.trim()) {
    learnerInterests += 'On their mind today: ' + S.mouseionThought.trim() + '. ';
  }
  if (S.skillContext && S.skillContext.trim()) {
    learnerInterests += 'Focus this session specifically on the learning skill: ' + S.skillContext.trim() + '. Weave the challenge and reflection directly around this skill. ';
  }

  try {
    var res = await API.post('/generate/session', {
      art_slug:          slug,
      phase_slug:        S.onboardPhase || 'adult',
      learner_interests: learnerInterests || null,
      // Only pass skill_id from engine recommendation when NOT in a skill-click session
      skill_id:          (!S.skillContext && S.nextRec) ? S.nextRec.skill_id : null,
      skill_context:     S.skillContext || null,   // skill name for AI focus + future backend routing
      language:          S.language || 'en',
    });
    currentSession = res;
    sessionLoading = false;
    set({sessionLoading: false, phase: 0, answered: false});
    S.assessSelectedIndex = null;   // 2026-07-07: reset pick state for the new session
  } catch(e) {
    console.error('AI generation failed — full error:', e);
    console.error('Error message:', e.message);
    // Try to get more detail from the response
    if (e.response) {
      e.response.text().then(function(t){ console.error('Server response:', t); });
    }
    currentSession = null;
    sessionLoading = false;
    set({sessionLoading: false, phase: 0, answered: false, view: 'session',
         sessionError: e.message || 'Unknown error'});
  }
}

function Session() {
  const p = S.phase;

  // In-session browser translation using native Translation API
  window.translateSessionContent = async function(targetLang) {
    const container = document.getElementById('pc');
    if (!container) return;
    
    // Check if browser supports Translation API
    if (!('Translator' in window)) {
      // Fallback: use Google Translate
      var t = targetLang || (S.learner && S.learner.language || 'en');
      window.open('https://translate.google.com/translate?sl=en&tl=' + t + '&u=' + encodeURIComponent(window.location.href), '_blank');
      return;
    }
    
    try {
      // Create translator from English to target language
      const translator = await window.Translator.create({
        sourceLanguage: 'en',
        targetLanguage: targetLang || (S.learner && S.learner.language) || 'en',
      });
      
      // Get all text nodes in the session content
      const walker = document.createTreeWalker(
        container,
        NodeFilter.SHOW_TEXT,
        { acceptNode: node => node.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT }
      );
      
      const textNodes = [];
      let node;
      while (node = walker.nextNode()) {
        textNodes.push(node);
      }
      
      // Translate each text node
      for (const textNode of textNodes) {
        const originalText = textNode.nodeValue.trim();
        if (originalText) {
          try {
            const translated = await translator.translate(originalText);
            textNode.nodeValue = translated;
          } catch (e) {
            console.warn('Translation failed for:', originalText, e);
          }
        }
      }
      
      // Mark as translated
      container.dataset.translated = targetLang || (S.learner && S.learner.language) || 'en';
      console.log('Session content translated to:', container.dataset.translated);
    } catch (e) {
      console.error('Browser translation failed:', e);
      // Fallback to Google Translate
      var t = targetLang || (S.learner && S.learner.language || 'en');
      window.open('https://translate.google.com/translate?sl=en&tl=' + t + '&u=' + encodeURIComponent(window.location.href), '_blank');
    }
  };

  // Show spinner while AI generates
  if (S.sessionLoading) {
    return '<div class="page" style="display:flex;align-items:center;justify-content:center;min-height:70vh">'
      + '<div style="text-align:center">'
      + '<div style="font-size:48px;margin-bottom:16px;animation:xpp 1.5s infinite">🌊</div>'
      + '<div style="font-family:var(--font-display);font-size:18px;font-weight:700;color:var(--wave);margin-bottom:8px">Preparing your session...</div>'
      + '<div style="font-size:13px;color:var(--text3)">Reading your frequency</div>'
      + '</div></div>';
  }

  // Generation failed or timed out — offer retry
  if (!currentSession) {
    return '<div class="page" style="display:flex;align-items:center;justify-content:center;min-height:70vh">'
      + '<div style="text-align:center;max-width:400px;padding:0 20px">'
      + '<div style="font-size:48px;margin-bottom:16px">🌊</div>'
      + '<div style="font-family:var(--font-display);font-size:18px;font-weight:700;color:var(--text);margin-bottom:8px">Session not loaded yet</div>'
      + '<div style="font-size:13px;color:var(--text2);margin-bottom:20px;line-height:1.6">The session engine is warming up. This can take a few seconds on first use.</div>'
      + '<div style="display:flex;gap:10px;justify-content:center">'
      + '<button class="btn btn-wave" onclick="retryLastSession()">Try again →</button>'
      + '<button class="btn btn-ghost" onclick="goHome()">Back to Agora</button>'
      + '</div></div></div>';
  }

  return `
  <div class="page">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px">
      <div>
        <h2>${currentSession ? currentSession.title : 'The Art of Growing'}</h2>
        <p style="font-size:12px;margin-top:2px">${currentSession ? (currentSession.art_name || 'Connecting') : 'Connecting · Permaculture &amp; regenerative systems'}</p>
      </div>
      <div style="display:flex;gap:6px;align-items:center">
        <button class="btn btn-ghost btn-sm" onclick="window._translateTarget=S.language==='en'?(S.learner&&S.learner.language||'en'):'en';set({language:window._translateTarget})" title="Toggle UI language">🌐</button>
        <button class="btn btn-ghost btn-sm" onclick="translateSessionContent(S.learner&&S.learner.language||'en')" title="Translate session content in-place">🌍 Translate</button>
        <button class="btn btn-ghost btn-sm" onclick="var t=(S.learner&&S.learner.language||'en');window.open('https://translate.google.com/translate?sl=en&tl='+t+'&u='+encodeURIComponent(window.location.href),'_blank')" title="Translate full page with browser">Translate page ↗</button>
        <button class="btn btn-ghost btn-sm" onclick="goHome()">✕</button>
      </div>
    </div>
    <div class="phase-strip">
      ${phaseNames.map((n,i)=>`
        <div class="pnode${i<p?' done':i===p?' act':''}">
          ${i<p?'✓ ':''}${n}
        </div>`).join('')}
    </div>
    <div class="bar-bg" style="height:3px;margin-bottom:22px">
      <div class="bar-f" style="width:${Math.round((p/5)*100)}%;background:linear-gradient(90deg,var(--wave),var(--deep))"></div>
    </div>
    <div id="pc">${phaseBody(p)}</div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:22px">
      <button class="btn btn-ghost" ${p===0?'disabled style="opacity:.4"':''}
        onclick="set({phase:${Math.max(0,p-1)},answered:false})">← Back</button>
      <span style="font-size:12px;color:var(--text3);font-family:var(--font-display)">Phase ${p+1} of 5</span>
      <button class="btn btn-wave" ${p===4?'style="visibility:hidden"':''}
        onclick="set({phase:${Math.min(4,p+1)},answered:false})">Next →</button>
    </div>
    ${S.showPolisGate ? `
    <div style="position:fixed;bottom:24px;left:50%;transform:translateX(-50%);
      background:var(--bg3);border:1px solid var(--polis,#7B5EA7);border-radius:var(--r);
      padding:16px 24px;max-width:400px;text-align:center;z-index:200;
      box-shadow:0 8px 32px rgba(0,0,0,0.4)">
      <div style="font-family:var(--font-display);font-weight:700;margin-bottom:6px">The Polis opens with practice</div>
      <div style="font-size:13px;color:var(--text2);line-height:1.6">
        Complete 5 learning days or earn 50 XP to unlock civic participation.
        The Polis works best when its members have practiced listening, understanding and respect.
      </div>
    </div>` : ''}
  </div>`;
}


// ══════════════════════════════════════════════════
// SANDBOX — Socratic companion shared component
// Used in: Mouseion (free exploration) + Challenge + Reflect phases
// ══════════════════════════════════════════════════

function buildSandboxContext(phaseLabel) {
  var _av = computeAvatarStage(S.xp || 0, S.artScores || {});
  var _bs = _bioregionState;
  var ctx = {
    phase_label:     phaseLabel,
    learner_name:    S.learner ? S.learner.display_name : null,
    learner_profile: S.learnerProfile || null,
    art_name:        currentSession ? currentSession.art_name : null,
    art_slug:        currentSession ? currentSession.art_slug : null,
    skill_name:      S.skillContext || null,
    challenge_text:  (phaseLabel === 'Reflect' && S.challengeText) ? S.challengeText : null,
    mouseion_intent: (phaseLabel === 'Mouseion' && S.mouseionThought) ? S.mouseionThought : null,
    avatar_stage:    _av ? _av.stage : null,
    bioregion_name:  (_bs && _bs.status === 'done' && _bs.profile) ? _bs.profile.name : null,
    learning_domain: S.skillDomain || null,
    skill_type:      S.skillType   || null,
  };
  return ctx;
}

async function sendSandboxMessage(inputId, phaseLabel) {
  var inputEl = document.getElementById(inputId);
  if (!inputEl) return;
  var text = inputEl.value.trim();
  if (!text || S.sandboxLoading) return;
  inputEl.value = '';

  // Append user message
  S.sandboxMessages = S.sandboxMessages.concat([{role:'user', content:text}]);
  set({sandboxLoading: true});

  try {
    var res = await API.post('/generate/scaffold', {
      messages: S.sandboxMessages,
      context:  buildSandboxContext(phaseLabel),
    });
    S.sandboxMessages = S.sandboxMessages.concat([{role:'assistant', content:res.reply}]);

    // Autosave every 4 exchanges (2 user + 2 assistant = 4 messages)
    if (S.sandboxMessages.length % 4 === 0) triggerProfileUpdate();

  } catch(e) {
    S.sandboxMessages = S.sandboxMessages.concat([
      {role:'assistant', content:"I'm having trouble connecting right now. Try again in a moment."}
    ]);
  }
  set({sandboxLoading: false});

  // Scroll thread to bottom
  setTimeout(function(){
    var t = document.getElementById('sandbox-thread');
    if (t) t.scrollTop = t.scrollHeight;
  }, 60);
}

function renderSandboxThread(inputId, phaseLabel, showGenerateBtn) {
  var msgs = S.sandboxMessages;
  var threadHTML = msgs.length === 0
    ? '<div style="font-size:12px;color:var(--text3);padding:10px 0;font-style:italic">Start the conversation — write anything you\'re thinking, wondering, or stuck on.</div>'
    : msgs.map(function(m) {
        var isUser = m.role === 'user';
        return '<div style="display:flex;gap:8px;margin-bottom:10px;align-items:flex-start'+(isUser?';flex-direction:row-reverse':'')+'">'
          + '<div style="flex-shrink:0;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;background:'+(isUser?'var(--bg4)':'var(--bg3)')+'">'
          + (isUser ? '👤' : '🌊') + '</div>'
          + '<div style="max-width:85%;font-size:13px;line-height:1.65;padding:8px 12px;border-radius:12px;'+(isUser?'border-radius:12px 4px 12px 12px;background:var(--bg4);color:var(--text)':'border-radius:4px 12px 12px 12px;background:var(--bg3);color:var(--text2)')+'">'
          + m.content + '</div></div>';
      }).join('');

  if (S.sandboxLoading) {
    threadHTML += '<div style="display:flex;gap:8px;align-items:center;padding:4px 0">'
      + '<div style="flex-shrink:0;width:26px;height:26px;border-radius:50%;background:var(--bg3);display:flex;align-items:center;justify-content:center;font-size:13px">🌊</div>'
      + '<div style="font-size:12px;color:var(--text3);font-style:italic">thinking...</div></div>';
  }

  var generateBtn = (showGenerateBtn && msgs.length >= 2)
    ? '<button class="btn btn-wave btn-full" style="margin-top:12px;font-size:13px" onclick="launchSessionFromSandbox()">🌊 Generate a session from this exploration →</button>'
    : '';

  return '<div id="sandbox-thread" style="max-height:260px;overflow-y:auto;margin-bottom:10px;padding-right:4px">'
    + threadHTML + '</div>'
    + '<div style="display:flex;gap:8px">'
    + '<input id="'+inputId+'" type="text" placeholder="What\'s on your mind..." '
    + 'style="flex:1;font-size:13px;background:var(--bg4);border:1px solid var(--border);border-radius:var(--r);padding:8px 12px;color:var(--text)" '
    + 'onkeydown="if(event.key===\'Enter\'&&!event.shiftKey){event.preventDefault();sendSandboxMessage(\''+inputId+'\',\''+phaseLabel+'\')}" />'
    + '<button class="btn" style="padding:8px 14px;font-size:13px;background:var(--wave);color:#000;border-radius:var(--r);cursor:pointer;font-weight:700" '
    + 'onclick="sendSandboxMessage(\''+inputId+'\',\''+phaseLabel+'\')" disabled="'+S.sandboxLoading+'">→</button>'
    + '</div>'
    + generateBtn
    + (msgs.length >= 2
        ? '<button onclick="saveToPeripatos(\'sandbox\')" '+(S.peripatosSaveStatus==='saving'?'disabled ':'')
          +'style="margin-top:8px;width:100%;padding:7px;font-size:12px;font-weight:600;border-radius:var(--r);'
          +'border:1px solid var(--border);cursor:pointer;'
          +(S.peripatosSaveStatus==='saved'?'background:rgba(0,229,200,0.08);color:var(--wave)':'background:var(--bg3);color:var(--text3)')+';">'
          +(S.peripatosSaveStatus==='saving'?'Saving…'
            :S.peripatosSaveStatus==='saved'?'✓ Saved to Peripatos'
            :S.peripatosSaveStatus==='error'?'✗ Save failed — retry'
            :'&#128220; Save to Peripatos')
          +'</button>'
        : '');
}

function launchSessionFromSandbox() {
  // Weave the sandbox conversation into learner_interests for session generation
  var summary = S.sandboxMessages
    .filter(function(m){ return m.role === 'user'; })
    .map(function(m){ return m.content; })
    .join(' | ');
  if (summary) S.mouseionThought = summary;
  // Trigger profile update before leaving
  if (S.sandboxMessages.length >= 2) triggerProfileUpdate();
  // Reset sandbox, launch session
  S.sandboxMessages = [];
  set({view:'session', sandboxOpen:false});
  loadAISession(null);
}

function triggerProfileUpdate() {
  if (!S.sandboxMessages || S.sandboxMessages.length < 2) return;
  var msgs = S.sandboxMessages.slice(); // snapshot
  // Fire-and-forget — no await, no UI feedback
  API.post('/generate/profile-update', {
    messages:         msgs,
    existing_profile: S.learnerProfile || null,
  }).then(function(res){
    if (res && res.status === 'ok') {
      // Reload profile into state silently
      API.get('/learners/me').then(function(me){
        if (me && me.learner_profile) {
          S.learnerProfile = me.learner_profile;
          // Regenerate Guiding Star from the updated profile
          API.post('/generate/guiding-star', {
            learner_profile: me.learner_profile,
          }).then(function(gs){
            if (gs && gs.guiding_star) {
              S.guidingStar = gs.guiding_star;
              try { localStorage.setItem('fl_guiding_star', gs.guiding_star); } catch(e) {}
            }
          }).catch(function(){});
        }
      }).catch(function(){});
    }
  }).catch(function(){});
}

// ══════════════════════════════════════════════════
// PERIPATOS JOURNAL
// Save & load companion exchange threads.
// Second tab inside Stoa (view:'reflect').
// ══════════════════════════════════════════════════

async function loadPeripatosEntries() {
  set({peripatosEntriesLoading: true});
  try {
    var data = await API.get('/peripatos/');
    set({peripatosEntries: data.entries || [], peripatosEntriesLoading: false});
  } catch(e) {
    set({peripatosEntries: [], peripatosEntriesLoading: false});
  }
}

async function saveToPeripatos(source) {
  var msgs = (source === 'portfolio') ? S.portfolioMessages : S.sandboxMessages;
  if (!msgs || msgs.length < 2 || S.peripatosSaveStatus === 'saving') return;

  var firstUser = msgs.find(function(m) { return m.role === 'user'; });
  var title = firstUser ? firstUser.content.slice(0, 80).trim() : 'Companion exchange';
  if (firstUser && firstUser.content.length > 80) title += '…';

  set({peripatosSaveStatus: 'saving'});
  try {
    var result = await API.post('/peripatos/', {title: title, messages: msgs.slice()});
    // Prepend to cached list so Journal tab updates immediately without reload
    if (S.peripatosEntries !== null) {
      S.peripatosEntries = [{
        id: result.id, title: title,
        turn_count: msgs.length,
        created_at: new Date().toISOString(),
      }].concat(S.peripatosEntries);
    }
    set({peripatosSaveStatus: 'saved'});
    setTimeout(function() { set({peripatosSaveStatus: null}); }, 3000);
  } catch(e) {
    set({peripatosSaveStatus: 'error'});
    setTimeout(function() { set({peripatosSaveStatus: null}); }, 4000);
  }
}

async function openPeripatosEntry(id) {
  var stub = S.peripatosEntries && S.peripatosEntries.find(function(e){ return e.id === id; });
  set({peripatosEntryOpen: {
    id: id,
    title: stub ? stub.title : '…',
    messages: null,
    created_at: stub ? stub.created_at : null,
  }});
  try {
    var entry = await API.get('/peripatos/' + id);
    set({peripatosEntryOpen: entry});
  } catch(e) {
    set({peripatosEntryOpen: null});
  }
}

async function deletePeripatosEntry(id) {
  try {
    await API.delete('/peripatos/' + id);
    if (S.peripatosEntries) {
      S.peripatosEntries = S.peripatosEntries.filter(function(e) { return e.id !== id; });
    }
    if (S.peripatosEntryOpen && S.peripatosEntryOpen.id === id) {
      set({peripatosEntryOpen: null});
    } else {
      set({});
    }
  } catch(e) { /* silent — entry may already be gone */ }
}

function peripatosRelativeTime(iso) {
  if (!iso) return '';
  var d = new Date(iso);
  var diff = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Yesterday';
  if (diff < 7)  return diff + ' days ago';
  return d.toLocaleDateString('en-US', {month: 'short', day: 'numeric'});
}

function renderPeripatosJournal() {
  // Single-entry reader
  if (S.peripatosEntryOpen) return renderPeripatosEntry(S.peripatosEntryOpen);

  // Loading / not yet fetched
  if (S.peripatosEntriesLoading || S.peripatosEntries === null) {
    return '<div style="text-align:center;padding:40px;color:var(--text3)">'
      + '<div class="spinner" style="margin:0 auto 12px"></div>'
      + '<div style="font-size:13px">Loading your journal…</div>'
      + '</div>';
  }

  // Empty state
  if (S.peripatosEntries.length === 0) {
    return '<div class="card" style="text-align:center;padding:32px">'
      + '<div style="font-size:32px;margin-bottom:10px">&#128172;</div>'
      + '<div style="font-size:14px;color:var(--text2);font-weight:600;margin-bottom:6px">No saved conversations yet</div>'
      + '<div style="font-size:13px;color:var(--text3);line-height:1.7">Start a conversation with the Companion<br>'
      + 'and tap <strong style="color:var(--text2)">Save to Peripatos</strong> to journal it here.</div>'
      + '</div>';
  }

  // Entry list
  return '<div style="display:flex;flex-direction:column;gap:10px">'
    + S.peripatosEntries.map(function(e) {
        return '<div onclick="openPeripatosEntry(' + e.id + ')" '
          + 'style="background:var(--card);border:1px solid var(--border);border-left:3px solid var(--wave);'
          + 'border-radius:var(--r);padding:14px 16px;cursor:pointer;display:flex;align-items:flex-start;gap:12px">'
          + '<div style="flex:1;min-width:0">'
          + '<div style="font-size:14px;font-weight:600;color:var(--text1);margin-bottom:5px;line-height:1.4">' + _esc(e.title) + '</div>'
          + '<div style="font-size:11px;color:var(--text3)">'
          + peripatosRelativeTime(e.created_at) + ' · ' + e.turn_count + ' turn' + (e.turn_count !== 1 ? 's' : '')
          + '</div>'
          + '</div>'
          + '<button onclick="event.stopPropagation();if(confirm(\'Delete this exchange?\'))deletePeripatosEntry(' + e.id + ')" '
          + 'style="flex-shrink:0;background:none;border:none;color:var(--text3);font-size:18px;cursor:pointer;padding:0;line-height:1;opacity:0.5" '
          + 'title="Delete">×</button>'
          + '</div>';
      }).join('')
    + '</div>';
}

function renderPeripatosEntry(entry) {
  // Loading stub (messages not yet fetched from API)
  if (!entry || !entry.messages) {
    return '<div style="text-align:center;padding:40px;color:var(--text3)">'
      + '<div class="spinner" style="margin:0 auto 12px"></div>'
      + '<div style="font-size:13px">Loading conversation…</div>'
      + '</div>';
  }

  var dateStr = entry.created_at
    ? new Date(entry.created_at).toLocaleDateString('en-US', {year: 'numeric', month: 'long', day: 'numeric'})
    : '';

  var header = '<div style="display:flex;align-items:flex-start;gap:10px;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid var(--border)">'
    + '<button onclick="set({peripatosEntryOpen:null})" class="btn" '
    + 'style="flex-shrink:0;padding:6px 12px;font-size:12px;border:1px solid var(--border);background:var(--bg3);color:var(--text3)">'
    + '← Back</button>'
    + '<div style="flex:1;min-width:0">'
    + '<div style="font-size:14px;font-weight:700;color:var(--text1);line-height:1.3;margin-bottom:2px">' + _esc(entry.title) + '</div>'
    + (dateStr ? '<div style="font-size:11px;color:var(--text3)">' + dateStr + '</div>' : '')
    + '</div>'
    + '<button onclick="if(confirm(\'Delete this exchange?\'))deletePeripatosEntry(' + entry.id + ')" '
    + 'style="flex-shrink:0;background:none;border:none;color:var(--text3);font-size:18px;cursor:pointer;padding:0 2px;opacity:0.5" '
    + 'title="Delete">×</button>'
    + '</div>';

  var convMsgs = (entry.messages || []).map(function(m) {
    var isUser = m.role === 'user';
    return '<div style="display:flex;gap:8px;margin-bottom:12px;align-items:flex-start'
      + (isUser ? ';flex-direction:row-reverse' : '') + '">'
      + '<div style="flex-shrink:0;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;'
      + 'justify-content:center;font-size:13px;background:' + (isUser ? 'var(--bg4)' : 'var(--bg3)') + '">'
      + (isUser ? '&#128100;' : '&#127754;') + '</div>'
      + '<div style="max-width:85%;font-size:13px;line-height:1.65;padding:8px 12px;'
      + (isUser
          ? 'border-radius:12px 4px 12px 12px;background:var(--bg4);color:var(--text)'
          : 'border-radius:4px 12px 12px 12px;background:var(--bg3);color:var(--text2)')
      + '">' + m.content + '</div></div>';
  }).join('');

  return header + '<div>' + convMsgs + '</div>';
}

// ══════════════════════════════════════════════════
// PORTFOLIO COMPANION
// Reflective mirror — speaks from learner_profile.
// Uses phase_label:'Portfolio' for a different system prompt.
// Never triggers profile update — conversation is meta, not learning content.
// ══════════════════════════════════════════════════
window.sendPortfolioMessage = async function sendPortfolioMessage() {
  var inputEl = document.getElementById('portfolio-input');
  if (!inputEl) return;
  var text = inputEl.value.trim();
  if (!text || S.portfolioLoading) return;
  inputEl.value = '';

  S.portfolioMessages = S.portfolioMessages.concat([{role:'user', content:text}]);
  set({portfolioLoading: true});

  try {
    var res = await API.post('/generate/scaffold', {
      messages: S.portfolioMessages,
      context: {
        phase_label:     'Portfolio',
        learner_name:    S.learner ? S.learner.display_name : null,
        learner_profile: S.learnerProfile || null,
        avatar_stage:    (function(){ var av = computeAvatarStage(S.xp||0, S.artScores||{}); return av ? av.stage : null; })(),
        bioregion_name:  (_bioregionState && _bioregionState.status === 'done' && _bioregionState.profile) ? _bioregionState.profile.name : null,
      },
    });
    S.portfolioMessages = S.portfolioMessages.concat([{role:'assistant', content:res.reply}]);
  } catch(e) {
    S.portfolioMessages = S.portfolioMessages.concat([
      {role:'assistant', content:"I'm having trouble connecting right now. Try again in a moment."}
    ]);
  }
  set({portfolioLoading: false});

  setTimeout(function(){
    var t = document.getElementById('portfolio-thread');
    if (t) t.scrollTop = t.scrollHeight;
  }, 60);
}

function renderPortfolioThread() {
  var msgs = S.portfolioMessages;
  var threadHTML = msgs.length === 0
    ? '<div style="font-size:12px;color:var(--text3);padding:10px 0;font-style:italic">Ask anything about what your story reveals — patterns, recurring themes, what you might be avoiding…</div>'
    : msgs.map(function(m) {
        var isUser = m.role === 'user';
        return '<div style="display:flex;gap:8px;margin-bottom:10px;align-items:flex-start'+(isUser?';flex-direction:row-reverse':'')+'">'
          + '<div style="flex-shrink:0;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;background:'+(isUser?'var(--bg4)':'var(--bg3)')+'">'
          + (isUser ? '👤' : '🧭') + '</div>'
          + '<div style="max-width:85%;font-size:13px;line-height:1.65;padding:8px 12px;border-radius:12px;'+(isUser?'border-radius:12px 4px 12px 12px;background:var(--bg4);color:var(--text)':'border-radius:4px 12px 12px 12px;background:var(--bg3);color:var(--text2)')+'">'
          + m.content + '</div></div>';
      }).join('');

  if (S.portfolioLoading) {
    threadHTML += '<div style="display:flex;gap:8px;align-items:center;padding:4px 0">'
      + '<div style="flex-shrink:0;width:26px;height:26px;border-radius:50%;background:var(--bg3);display:flex;align-items:center;justify-content:center;font-size:13px">🧭</div>'
      + '<div style="font-size:12px;color:var(--text3);font-style:italic">reflecting…</div></div>';
  }

  return '<div id="portfolio-thread" style="max-height:260px;overflow-y:auto;margin-bottom:10px;padding-right:4px">'
    + threadHTML + '</div>'
    + '<div style="display:flex;gap:8px">'
    + '<input id="portfolio-input" type="text" placeholder="What does my story tell you?" '
    + 'style="flex:1;font-size:13px;background:var(--bg4);border:1px solid var(--border);border-radius:var(--r);padding:8px 12px;color:var(--text)" '
    + 'onkeydown="if(event.key===\'Enter\'&&!event.shiftKey){event.preventDefault();sendPortfolioMessage()}" />'
    + '<button class="btn" style="padding:8px 14px;font-size:13px;background:var(--wave);color:#000;border-radius:var(--r);cursor:pointer;font-weight:700" '
    + 'onclick="sendPortfolioMessage()">→</button>'
    + '</div>'
    + (msgs.length >= 2
        ? '<button onclick="saveToPeripatos(\'portfolio\')" '+(S.peripatosSaveStatus==='saving'?'disabled ':'')
          +'style="margin-top:8px;width:100%;padding:7px;font-size:12px;font-weight:600;border-radius:var(--r);'
          +'border:1px solid var(--border);cursor:pointer;'
          +(S.peripatosSaveStatus==='saved'?'background:rgba(0,229,200,0.08);color:var(--wave)':'background:var(--bg3);color:var(--text3)')+';">'
          +(S.peripatosSaveStatus==='saving'?'Saving…'
            :S.peripatosSaveStatus==='saved'?'✓ Saved to Peripatos'
            :S.peripatosSaveStatus==='error'?'✗ Save failed — retry'
            :'&#128220; Save to Peripatos')
          +'</button>'
        : '');
}
function Mouseion() {
  const groups = [
    {label:'Being',      color:'var(--wave)',  arts:[
      ['move','Moving','🏃'],['eat','Eating','🍎'],['feel','Feeling','💙'],
      ['notice','Noticing','👁️'],['express','Expressing','🎨'],
    ]},
    {label:'Becoming',   color:'var(--deep)',  arts:[
      ['live','Living','🌍'],['listen','Listening','👂'],['give','Giving','🎁'],
      ['receive','Receiving','📥'],['collaborate','Collaborating','🤝'],
    ]},
    {label:'Connecting', color:'var(--gold)',  arts:[
      ['understand','Understanding','🔍'],['respect','Respecting','🙏'],
      ['build','Building','🔨'],['grow','Growing','🌱'],['consume','Consuming','📚'],
    ]},
  ];
  const _ds = computeDomainScores(S.artScores || {});
  const _DOMS = [
    {key:'cognitive', label:'Cognitive & Intellectual', icon:'🧠', color:'#5B8DD9', primaryArt:'understand', skills:[
      'Critical Thinking','Problem Solving','Systems Thinking','Memory & Retention','Decision Making','Project Management',
    ]},
    {key:'creative',  label:'Creative & Artistic',      icon:'🎨', color:'#E8A87C', primaryArt:'express', skills:[
      'Visual Art','Music & Rhythm','Creative Writing','Drama & Theatre','Improvisation & Public Speaking','Craftsmanship & Making',
    ]},
    {key:'physical',  label:'Physical & Motor',         icon:'🌿', color:'#6DB97A', primaryArt:'move', skills:[
      'Gross Motor','Fine Motor','Physical Fitness','Dance & Movement','Body Awareness','First Aid & Nursing',
    ]},
    {key:'social',    label:'Social & Relational',      icon:'🤝', color:'#9B8EC4', primaryArt:'collaborate', skills:[
      'Collaboration','Conflict Resolution','Empathetic Leadership','Negotiation','Cultural Competence','Parenting & Caregiving',
    ]},
    {key:'language',  label:'Language & Communication', icon:'💬', color:'#4FC3C3', primaryArt:'listen', skills:[
      'Active Reading','Active Listening','Storytelling','Debate & Argumentation','Foreign Language Acquisition','Rhetoric & Persuasion',
    ]},
    {key:'emotional', label:'Emotional & Psychological',icon:'💙', color:'#E88080', primaryArt:'feel', skills:[
      'Self-Awareness','Emotional Regulation','Empathy and Compassion','Self-Efficacy','Contemplative Practice','Gratitude & Appreciation',
    ]},
    {key:'meta',      label:'Meta-Learning',            icon:'✦',  color:'#D4C14A', primaryArt:'notice', skills:[
      'Learning How to Learn','Self-Regulation','Personal Values','Curiosity and Exploration','Vision, Mission and Purpose','Mentorship & Teaching',
    ]},
    {key:'technical', label:'Tools & Systems',          icon:'⚙️', color:'#7BADB8', primaryArt:'understand', skills:[
      'Digital Literacy','Data Analysis & Statistics','Design Thinking','Philosophy & Ethics','Permaculture','Cooking & Nutrition',
    ]},
  ];
  return `
  <div class="page">
    <div style="margin-bottom:18px">
      <h2>The Mouseion</h2>
      <p style="margin-top:4px">The universal library of human arts · yours to explore at your own pace!</p>
    </div>

    <div class="card card-wave" style="margin-bottom:20px">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
        <span style="font-size:18px">🌊</span>
        <span style="font-family:var(--font-display);font-size:14px;font-weight:700;color:var(--wave)">The Companion</span>
        <span style="font-size:11px;color:var(--text3);margin-left:auto">Socratic · free exploration · your curiosity leads</span>
      </div>
      <p style="font-size:12px;color:var(--text2);margin-bottom:10px;line-height:1.65">
        Explore anything freely. The companion asks questions, not answers. When you're ready, generate a session from your exploration.
      </p>
      <div style="background:var(--bg2);border-radius:var(--r);padding:12px;margin-bottom:10px">
        ${renderSandboxThread('sandbox-mouseion-input', 'Mouseion', true)}
      </div>
      <details style="margin-top:6px">
        <summary style="font-size:11px;color:var(--text3);cursor:pointer;list-style:none;display:flex;align-items:center;gap:5px">
          <span style="border:1px solid var(--border);border-radius:50%;width:14px;height:14px;display:inline-flex;align-items:center;justify-content:center;font-size:9px">+</span>
          Also weave a specific thought into your next session (optional)
        </summary>
        <textarea id="mouseion-thought" rows="2"
          placeholder="A specific struggle, question, or context to weave into the generated session..."
          oninput="S.mouseionThought=this.value"
          style="font-size:12px;margin-top:8px">${S.mouseionThought||''}</textarea>
      </details>
    </div>

    <div style="margin-bottom:10px">
      <span style="font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text3)">Human Signature</span>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin-bottom:28px">
      ${groups.map(g => `
        <div class="card" style="border-left:3px solid ${g.color}">
          <h3 style="color:${g.color};font-family:var(--font-display);margin-bottom:12px">${g.label}</h3>
          ${g.arts.map(([slug, label, emoji]) => {
            const score = S.artScores && S.artScores[slug] ? S.artScores[slug] : 0;
            return `
            <div class="art-row" onclick="startDirectSession('${slug}')">
              <span style="font-size:16px;width:22px;text-align:center;flex-shrink:0">${emoji}</span>
              <div style="flex:1;font-size:13px;color:var(--text)">${label}</div>
              <div class="bar-bg" style="width:60px;height:4px">
                <div class="bar-f" style="width:${score*100}%;background:${g.color}"></div>
              </div>
              <span style="font-size:11px;color:var(--text3);min-width:28px;text-align:right">${Math.round(score*100)}%</span>
            </div>`;
          }).join('')}
        </div>`).join('')}
    </div>
    <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:14px">
      <span style="font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text3)">Learning Domains</span>
      <span style="font-size:11px;color:var(--text3)">· how your arts translate into universal competencies</span>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px;margin-bottom:24px">
      ${_DOMS.map(function(_d){
        var _pct = Math.round((_ds[_d.key]||0)*100);
        var _skillRows = _d.skills.map(function(sk){
          var _sPct = Math.round(computeSkillScore(sk, S.artScores||{})*100);
          var _lv = _sPct === 0 ? 0 : _sPct <= 25 ? 1 : _sPct <= 50 ? 2 : _sPct <= 75 ? 3 : 4;
          var _indicator = _lv === 0
            ? '<span style="font-size:10px;color:var(--text3)">—</span>'
            : '<span style="font-size:10px;font-weight:600;color:'+_d.color+';background:'+_d.color+'18;padding:2px 8px;border-radius:20px">Lv '+_lv+'</span>';
          return '<div onclick="startSkillSession(\''+sk.replace(/&/g,'&amp;')+'\',\''+_d.primaryArt+'\')" '
            +'style="display:flex;align-items:center;justify-content:space-between;gap:8px;'
            +'font-size:12px;padding:3px 0;border-bottom:1px solid var(--border);'
            +'cursor:pointer;transition:background .15s;border-radius:4px;margin:0 -4px;padding-left:4px;padding-right:4px" '
            +'onmouseover="this.style.background=\'var(--bg3)\'" onmouseout="this.style.background=\'transparent\'">'
            +'<span style="color:var(--text2)">'+sk+'</span>'
            +_indicator
            +'</div>';
        }).join('');
        return '<div class="card" '
          +'style="padding:14px 16px;border-left:3px solid '+_d.color+';border-radius:var(--r);cursor:pointer;transition:transform .18s,border-color .18s" '
          +'onmouseenter="this.style.transform=\'translateY(-2px)\'" onmouseleave="this.style.transform=\'\'">'
          +'<div style="display:flex;align-items:center;gap:8px;margin-bottom:7px">'
          +'<span style="font-size:16px;flex-shrink:0">'+_d.icon+'</span>'
          +'<span style="font-size:13px;font-weight:700;color:var(--text);flex:1;font-family:var(--font-display)">'+_d.label+'</span>'
          +'<span style="font-size:11px;font-weight:700;color:'+_d.color+';background:'+_d.color+'18;padding:2px 8px;border-radius:20px">'+_pct+'%</span>'
          +'</div>'
          +'<div style="height:4px;background:var(--bg5);border-radius:4px;overflow:hidden;margin-bottom:11px">'
          +'<div style="height:4px;border-radius:4px;width:'+_pct+'%;background:'+_d.color+';transition:width .7s cubic-bezier(.4,0,.2,1)"></div>'
          +'</div>'
          +'<div style="border-top:1px solid var(--border);padding-top:6px">'
          +_skillRows
          +'</div>'
          +'</div>';
      }).join('')}
    </div>
    ${S.showPolisGate ? `
    <div style="position:fixed;bottom:24px;left:50%;transform:translateX(-50%);
      background:var(--bg3);border:1px solid var(--polis,#7B5EA7);border-radius:var(--r);
      padding:16px 24px;max-width:400px;text-align:center;z-index:200;
      box-shadow:0 8px 32px rgba(0,0,0,0.4)">
      <div style="font-family:var(--font-display);font-weight:700;margin-bottom:6px">The Polis opens with practice</div>
      <div style="font-size:13px;color:var(--text2);line-height:1.6">
        Complete 5 learning days or earn 50 XP to unlock civic participation.
        The Polis works best when its members have practiced listening, understanding and respect.
      </div>
    </div>` : ''}
  </div>`;
}

// ══════════════════════════════════════════════════
// STOA (Reflect)
// ══════════════════════════════════════════════════
// ── Stoa daily prompts (rotate by day, no API call needed) ───
const STOA_PROMPTS = [
  "What in your life is already growing well — and what might need more tending?",
  "What have you noticed today that you might normally walk past?",
  "When did you last change your mind about something important? What shifted?",
  "What would you do differently if you weren't afraid of looking foolish?",
  "Who taught you something without meaning to? What was it?",
  "What does 'enough' look like for you right now?",
  "What are you pretending not to know?",
  "What would you create if no one would ever see it?",
  "What practice, if you did it daily, would change everything?",
  "What does your body know that your mind hasn't caught up with yet?",
  "Where in your life are you consuming more than you're contributing?",
  "What question are you most afraid to ask yourself?",
  "What is the smallest thing that made you feel most alive this week?",
  "If your life were a garden, what season is it in right now?",
  "What have you been given that you haven't yet learned to receive?",
  "What are you building that will outlast you?",
  "What truth are you circling without landing on?",
  "Where do you feel most like yourself? Why not more of the time?",
  "What would you say to the person you were five years ago?",
  "What does rest mean to you — and when did you last truly have it?",
];

function stoaDailyPrompt() {
  const day = Math.floor(Date.now() / 86400000);
  return STOA_PROMPTS[day % STOA_PROMPTS.length];
}

function stoaRelativeTime(iso) {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const mins  = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days  = Math.floor(diff / 86400000);
  if (mins < 2)   return 'Just now';
  if (mins < 60)  return `${mins} min ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days === 1) return 'Yesterday';
  if (days < 7)  return `${days} days ago`;
  return new Date(iso).toLocaleDateString();
}

window.loadStoa = async function() {
  try {
    const entries = await API.get('/reflections/');
    set({stoaEntries: entries, stoaError: null});
  } catch(e) {
    set({stoaError: 'Could not load reflections'});
  }
};

window.saveReflection = async function() {
  const body = S.stoaText && S.stoaText.trim();
  if (!body) return;
  set({stoaSaving: true});
  try {
    await API.post('/reflections/', {
      body,
      prompt:     S.stoaPrompt || stoaDailyPrompt(),
      session_id: S.stoaSessionId || null,
      art_id:     null,
      is_private: true,
    });
    set({stoaText:'', stoaSessionId:null, stoaSaving:false, stoaSaved:true});
    await loadStoa();
    setTimeout(function(){ set({stoaSaved:false}); }, 2500);
  } catch(e) {
    set({stoaSaving:false, stoaError:'Could not save — please try again'});
  }
};

window.deleteReflection = async function(id) {
  try {
    await API.delete('/reflections/' + id);
    set({stoaEntries: (S.stoaEntries||[]).filter(e => e.id !== id)});
  } catch(e) { console.log('Delete error:', e.message); }
};

function Stoa() {
  // Auto-populate from session if coming from Academy
  const sessionCarryOver = S.reflectText && S.reflectText.trim();
  const prompt = sessionCarryOver
    ? (currentSession && currentSession.reflect_prompt ? currentSession.reflect_prompt : stoaDailyPrompt())
    : stoaDailyPrompt();

  const entries = S.stoaEntries || [];
  const tab = S.peripatosTab || 'write';
  const journalCount = S.peripatosEntries !== null ? S.peripatosEntries.length : null;
  const tabBar = [['write', '\u270d\ufe0f Write'], ['journal', '\ud83d\udcdc Journal' + (journalCount !== null ? ' (' + journalCount + ')' : '')]].map(function(t) {
    var active = tab === t[0];
    return '<button onclick="set({peripatosTab:\'' + t[0] + '\',peripatosEntryOpen:null})" '
      + 'style="flex:1;padding:7px 4px;font-size:12px;font-weight:' + (active ? '700' : '400') + ';border-radius:7px;border:none;cursor:pointer;'
      + 'background:' + (active ? 'var(--card)' : 'transparent') + ';color:' + (active ? 'var(--text1)' : 'var(--text3)') + ';'
      + 'transition:all .15s;box-shadow:' + (active ? '0 1px 6px rgba(0,0,0,0.3)' : 'none') + '">' + t[1] + '</button>';
  }).join('');

  return `
  <div class="page" style="max-width:680px">
    <div style="margin-bottom:24px">
      <h2>The Peripatos</h2>
      <p style="margin-top:4px">A colonnade for solitary thinking. This space is yours — no grades, no performance, just honest thought.</p>
    </div>

    <div style="display:flex;gap:4px;margin-bottom:20px;background:var(--bg3);border-radius:10px;padding:4px;border:1px solid var(--border)">
      ${tabBar}
    </div>

    ${tab === 'journal' ? renderPeripatosJournal() : `
    <div class="card card-wave" style="margin-bottom:14px">
      <h4 style="margin-bottom:12px">${sessionCarryOver ? 'Continue your reflection' : "Today's prompt"}</h4>
      <p style="font-size:15px;font-style:italic;line-height:1.8;border-left:3px solid var(--wave);padding-left:14px;margin-bottom:18px;color:var(--text)">
        "${prompt}"
      </p>
      <textarea id="stoa-body" rows="6"
        placeholder="Write freely. No one reads this unless you choose to share it."
        oninput="S.stoaText=this.value;S.stoaPrompt='${prompt.replace(/'/g,"\\'").replace(/\n/g,' ')}';"
      >${sessionCarryOver ? sessionCarryOver : (S.stoaText||'')}</textarea>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px">
        <span style="font-size:11px;color:var(--text3)">Private by default · yours always</span>
        <div style="display:flex;gap:8px;align-items:center">
          ${S.stoaSaved ? '<span style="font-size:12px;color:var(--wave)">✓ Saved</span>' : ''}
          ${S.stoaError ? '<span style="font-size:12px;color:var(--coral)">${S.stoaError}</span>' : ''}
          <button class="btn btn-wave btn-sm" onclick="saveReflection()"
            ${S.stoaSaving ? 'disabled' : ''}>
            ${S.stoaSaving ? 'Saving…' : 'Save reflection'}
          </button>
        </div>
      </div>
    </div>

    ${entries.length > 0 ? `
    <div class="card">
      <h4 style="margin-bottom:14px">Recent reflections</h4>
      ${entries.map(e => `
        <div style="padding:13px 0;border-bottom:1px solid var(--border);position:relative">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px">
            <div style="font-size:11px;color:var(--text3);font-family:var(--font-display)">${stoaRelativeTime(e.created_at)}</div>
            <button onclick="deleteReflection(${e.id})"
              style="background:none;border:none;color:var(--text3);font-size:14px;cursor:pointer;padding:0;line-height:1;opacity:0.5"
              title="Delete">×</button>
          </div>
          ${e.prompt ? `<div style="font-size:12px;font-style:italic;color:var(--text3);margin-bottom:5px;line-height:1.5">"${e.prompt}"</div>` : ''}
          <div style="font-size:14px;color:var(--text2);line-height:1.7;white-space:pre-wrap">${e.body}</div>
        </div>`).join('')}
    </div>` : `
    <div class="card" style="text-align:center;padding:32px">
      <div style="font-size:32px;margin-bottom:10px">🌊</div>
      <div style="color:var(--text3);font-size:13px;line-height:1.7">
        Your journal is empty — write your first reflection above.<br>
        Every wave caught is worth recording.
      </div>
    </div>`}
    `}

    ${S.showPolisGate ? `
    <div style="position:fixed;bottom:24px;left:50%;transform:translateX(-50%);
      background:var(--bg3);border:1px solid var(--polis,#7B5EA7);border-radius:var(--r);
      padding:16px 24px;max-width:400px;text-align:center;z-index:200;
      box-shadow:0 8px 32px rgba(0,0,0,0.4)">
      <div style="font-family:var(--font-display);font-weight:700;margin-bottom:6px">The Polis opens with practice</div>
      <div style="font-size:13px;color:var(--text2);line-height:1.6">
        Complete 5 learning days or earn 50 XP to unlock civic participation.
      </div>
    </div>` : ''}
  </div>`;
}

// ══════════════════════════════════════════════════
// PROGRESS PAGE
// Three-tab view: XP Chart · Session History · Per-Art Skill Breakdown
// Data from GET /sessions/activity and GET /sessions/history
// ══════════════════════════════════════════════════
function Portfolio() {
  // ── Loading state ─────────────────────────────
  if (S.progressLoading || S.progressHistory === null) {
    return `<div class="page" style="display:flex;align-items:center;justify-content:center;min-height:60vh">
      <div style="text-align:center;color:var(--text3)">
        <div class="spinner" style="margin:0 auto 12px"></div>
        <div style="font-size:13px">Loading your journey…</div>
      </div>
    </div>`;
  }

  const history  = S.progressHistory  || [];
  const activity = S.progressActivity || [];
  const tab      = S.progressTab || 'chart';

  // ── Aggregate lifetime totals ──────────────────
  const totalXP   = S.xp || 0;
  const totalSess = history.length; // may be capped at 30, so use streak data for sessions count
  const totalMins = S.weekMinutes || 0;

  // ── Tab content builders ───────────────────────

  // 1. XP CHART — 30-day bar chart (SVG, no library)
  function xpChart() {
    if (activity.length === 0) {
      return `<div style="text-align:center;padding:48px 0;color:var(--text3)">
        <div style="font-size:32px;margin-bottom:10px">🌊</div>
        <div style="font-size:13px;line-height:1.7">No activity yet — complete a session to see your XP chart.</div>
      </div>`;
    }

    // Build a dense 30-day map (oldest → newest), filling gaps with 0
    var dayMap = {};
    activity.forEach(function(r) { dayMap[r.date] = r; });
    var days = [];
    for (var i = 29; i >= 0; i--) {
      var d = new Date(); d.setDate(d.getDate() - i);
      var key = d.toISOString().slice(0, 10);
      days.push({
        date:    key,
        label:   d.getDate() === 1 ? d.toLocaleString('default',{month:'short'}) : (i % 7 === 0 ? d.getDate() : ''),
        xp:      (dayMap[key] && dayMap[key].xp_earned)     || 0,
        sess:    (dayMap[key] && dayMap[key].sessions_done)  || 0,
        mins:    (dayMap[key] && dayMap[key].minutes_spent)  || 0,
      });
    }
    var maxXP = Math.max.apply(null, days.map(function(d){ return d.xp; })) || 1;

    // SVG bar chart — 30 bars, responsive via viewBox
    var W = 560, H = 130, PAD_L = 28, PAD_B = 22, barW = 13, gap = 5;
    var chartW = days.length * (barW + gap) - gap;
    var startX = PAD_L;

    var bars = days.map(function(d, i) {
      var barH = Math.max(2, Math.round((d.xp / maxXP) * (H - PAD_B - 8)));
      var x    = startX + i * (barW + gap);
      var y    = H - PAD_B - barH;
      var fill = d.xp > 0 ? 'var(--wave)' : 'rgba(255,255,255,0.06)';
      var tip  = d.date + ': ' + d.xp + ' XP · ' + d.sess + ' sess · ' + d.mins + 'min';
      var lbl  = d.label ? '<text x="'+(x+barW/2)+'" y="'+(H-4)+'" text-anchor="middle" font-size="8" fill="rgba(255,255,255,0.35)" font-family="sans-serif">'+d.label+'</text>' : '';
      return '<rect x="'+x+'" y="'+y+'" width="'+barW+'" height="'+barH
        +'" fill="'+fill+'" rx="2" opacity="0.85"><title>'+tip+'</title></rect>'
        + (d.xp > 0 ? '<rect x="'+x+'" y="'+y+'" width="'+barW+'" height="2" fill="rgba(0,229,200,0.9)" rx="2"/>' : '')
        + lbl;
    }).join('');

    // Y-axis tick labels (3 ticks)
    var ticks = [0, Math.round(maxXP / 2), maxXP].map(function(v) {
      var ty = H - PAD_B - Math.round((v / maxXP) * (H - PAD_B - 8));
      return '<text x="'+(PAD_L-4)+'" y="'+(ty+3)+'" text-anchor="end" font-size="8" fill="rgba(255,255,255,0.3)" font-family="sans-serif">'+v+'</text>'
        + '<line x1="'+PAD_L+'" y1="'+ty+'" x2="'+(startX+chartW)+'" y2="'+ty+'" stroke="rgba(255,255,255,0.05)" stroke-width="0.7"/>';
    }).join('');

    var totalChartXP = activity.reduce(function(s, r){ return s + (r.xp_earned||0); }, 0);
    var activeDays   = activity.filter(function(r){ return r.xp_earned > 0; }).length;
    var avgXP        = activeDays > 0 ? Math.round(totalChartXP / activeDays) : 0;

    return `
    <div style="margin-bottom:10px;display:flex;gap:20px;flex-wrap:wrap">
      <div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 16px;min-width:90px">
        <div style="font-size:20px;font-weight:700;color:var(--wave)">${totalChartXP}</div>
        <div style="font-size:11px;color:var(--text3);margin-top:2px">XP this month</div>
      </div>
      <div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 16px;min-width:90px">
        <div style="font-size:20px;font-weight:700;color:#6AB0FF">${activeDays}</div>
        <div style="font-size:11px;color:var(--text3);margin-top:2px">active days</div>
      </div>
      <div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 16px;min-width:90px">
        <div style="font-size:20px;font-weight:700;color:var(--gold)">${avgXP}</div>
        <div style="font-size:11px;color:var(--text3);margin-top:2px">avg XP / active day</div>
      </div>
    </div>
    <div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 14px 6px;overflow:hidden">
      <div style="font-size:11px;color:var(--text3);margin-bottom:10px">XP earned — last 30 days</div>
      <svg width="100%" viewBox="0 0 ${W} ${H}" style="overflow:visible;display:block">
        ${ticks}${bars}
      </svg>
    </div>`;
  }

  // 2. SESSION HISTORY — scrollable card list
  function sessionHistory() {
    if (history.length === 0) {
      return `<div style="text-align:center;padding:48px 0;color:var(--text3)">
        <div style="font-size:32px;margin-bottom:10px">🎓</div>
        <div style="font-size:13px;line-height:1.7">No completed sessions yet.<br>Head to the Academy to start your first wave.</div>
        <button class="btn btn-wave btn-sm" style="margin-top:14px" onclick="set({view:'session',phase:0,answered:false})">Go to Academy →</button>
      </div>`;
    }

    var _artEmojis = {
      move:'🏃', eat:'🍎', feel:'💙', notice:'👁️', express:'🎨',
      live:'🌍', listen:'👂', give:'🎁', receive:'📥', collaborate:'🤝',
      understand:'🔍', respect:'🙏', build:'🔨', grow:'🌱', consume:'📚',
    };

    return `<div style="display:flex;flex-direction:column;gap:8px">
      ${history.map(function(s) {
        var dt   = s.completed_at ? new Date(s.completed_at) : null;
        var dateStr = dt ? dt.toLocaleDateString('default',{month:'short',day:'numeric'}) : '';
        var timeStr = dt ? dt.toLocaleTimeString('default',{hour:'2-digit',minute:'2-digit'}) : '';
        var mins    = s.duration_seconds ? Math.round(s.duration_seconds / 60) : 0;
        var emoji   = _artEmojis[s.art_slug] || '🌊';
        var phases  = ['','●','●●','●●●','●●●●','●●●●●'];
        var phaseDots = phases[Math.min(s.phase_reached||0, 5)] || '';
        return `<div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px 14px;display:flex;align-items:center;gap:12px">
          <div style="font-size:24px;flex-shrink:0">${emoji}</div>
          <div style="flex:1;min-width:0">
            <div style="font-weight:600;font-size:14px;color:var(--text1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${s.title}</div>
            <div style="font-size:11px;color:var(--text3);margin-top:3px">${s.art_name} · ${mins ? mins+'min' : ''}</div>
          </div>
          <div style="text-align:right;flex-shrink:0">
            <div style="font-size:13px;font-weight:700;color:var(--wave)">+${s.xp_earned} XP</div>
            <div style="font-size:10px;color:var(--text3);margin-top:2px">${phaseDots}</div>
            <div style="font-size:10px;color:var(--text3)">${dateStr} ${timeStr}</div>
          </div>
        </div>`;
      }).join('')}
      <div style="text-align:center;padding:8px 0;font-size:11px;color:var(--text3)">Showing last ${history.length} sessions</div>
    </div>`;
  }

  // 3. PER-ART SKILL BREAKDOWN — arts list; click to expand skill levels
  function artBreakdown() {
    // Arts ordered by score descending (touched first, then alphabetical)
    var _artScores = S.artScores || {};
    var ARTS_META = [
      {slug:'move',label:'Move',emoji:'🏃',group:'being'},
      {slug:'eat',label:'Eat',emoji:'🍎',group:'being'},
      {slug:'feel',label:'Feel',emoji:'💙',group:'being'},
      {slug:'notice',label:'Notice',emoji:'👁️',group:'being'},
      {slug:'express',label:'Express',emoji:'🎨',group:'being'},
      {slug:'live',label:'Live',emoji:'🌍',group:'becoming'},
      {slug:'listen',label:'Listen',emoji:'👂',group:'becoming'},
      {slug:'give',label:'Give',emoji:'🎁',group:'becoming'},
      {slug:'receive',label:'Receive',emoji:'📥',group:'becoming'},
      {slug:'collaborate',label:'Collaborate',emoji:'🤝',group:'becoming'},
      {slug:'understand',label:'Understand',emoji:'🔍',group:'connecting'},
      {slug:'respect',label:'Respect',emoji:'🙏',group:'connecting'},
      {slug:'build',label:'Build',emoji:'🔨',group:'connecting'},
      {slug:'grow',label:'Grow',emoji:'🌱',group:'connecting'},
      {slug:'consume',label:'Consume',emoji:'📚',group:'connecting'},
    ];
    var GC = {
      being:      {color:'var(--wave)',    label:'Being'},
      becoming:   {color:'#6AB0FF',       label:'Becoming'},
      connecting: {color:'var(--gold)',   label:'Connecting'},
    };

    // Build per-art skill list from SKILL_ART_WEIGHTS (skills that contribute to each art)
    var artSkillMap = {};
    Object.keys(SKILL_ART_WEIGHTS).forEach(function(skill) {
      var weights = SKILL_ART_WEIGHTS[skill];
      Object.keys(weights).forEach(function(slug) {
        if (!artSkillMap[slug]) artSkillMap[slug] = [];
        artSkillMap[slug].push({skill: skill, weight: weights[slug]});
      });
    });
    // Sort each art's skills by weight descending
    Object.keys(artSkillMap).forEach(function(slug) {
      artSkillMap[slug].sort(function(a,b){ return b.weight-a.weight; });
    });

    var sorted = ARTS_META.slice().sort(function(a,b){
      return (_artScores[b.slug]||0) - (_artScores[a.slug]||0);
    });

    return `<div style="display:flex;flex-direction:column;gap:6px">
      ${sorted.map(function(art) {
        var score    = _artScores[art.slug] || 0;
        var pct      = Math.round(score * 100);
        var isOpen   = S.progressArt === art.slug;
        var gc       = GC[art.group];
        var skills   = artSkillMap[art.slug] || [];
        var skillRows = isOpen ? skills.slice(0,8).map(function(sk) {
          // Rough skill score — art score * weight, mapped to 0–4 levels
          var rawLevel = score * sk.weight * 20; // scale to 0–4 range
          var lv = Math.min(4, Math.floor(rawLevel));
          var lvColors = ['var(--text3)','#5B8DD9','#6DB97A','var(--gold)','var(--wave)'];
          var lvLabels = ['Untouched','Lv 1','Lv 2','Lv 3','Lv 4'];
          return `<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border)">
            <div style="font-size:12px;color:var(--text2)">${sk.skill}</div>
            <div style="display:flex;align-items:center;gap:6px">
              <div style="font-size:10px;font-weight:600;color:${lvColors[lv]};background:rgba(255,255,255,0.06);padding:2px 6px;border-radius:4px">${lvLabels[lv]}</div>
              <button onclick="startSkillSession('${sk.skill.replace(/'/g,"\\'")}')" style="font-size:10px;background:rgba(0,229,200,0.1);border:1px solid rgba(0,229,200,0.3);color:var(--wave);border-radius:4px;padding:2px 7px;cursor:pointer">Practice →</button>
            </div>
          </div>`;
        }).join('') : '';

        return `<div style="background:var(--card);border:1px solid var(--border);border-radius:10px;overflow:hidden">
          <div onclick="toggleProgressArt('${art.slug}')" style="display:flex;align-items:center;gap:10px;padding:11px 14px;cursor:pointer;user-select:none">
            <div style="font-size:20px;flex-shrink:0">${art.emoji}</div>
            <div style="flex:1">
              <div style="font-size:13px;font-weight:600;color:var(--text1)">${art.label}</div>
              <div style="margin-top:5px;background:rgba(255,255,255,0.07);border-radius:4px;height:4px;overflow:hidden">
                <div style="height:4px;border-radius:4px;background:${gc.color};width:${pct}%;transition:width .4s ease"></div>
              </div>
            </div>
            <div style="text-align:right;flex-shrink:0">
              <div style="font-size:13px;font-weight:700;color:${gc.color}">${pct}%</div>
              <div style="font-size:9px;color:var(--text3);margin-top:2px">${gc.label}</div>
            </div>
            <div style="color:var(--text3);font-size:12px;margin-left:4px">${isOpen ? '▲' : '▼'}</div>
          </div>
          ${isOpen ? `<div style="padding:4px 14px 12px;border-top:1px solid var(--border)">${skillRows}</div>` : ''}
        </div>`;
      }).join('')}
    </div>`;
  }

  // ── Render ─────────────────────────────────────
  return `<div class="page">
    <div style="margin-bottom:20px">
      <h2 style="font-size:clamp(18px,3vw,26px)">Your Progress</h2>
      <p style="margin-top:4px;font-size:13px;color:var(--text2)">XP earned · sessions completed · skills growing</p>
    </div>

    <!-- Lifetime stat row -->
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px">
      <div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 16px;flex:1;min-width:80px">
        <div style="font-size:22px;font-weight:700;color:var(--wave)">${totalXP}</div>
        <div style="font-size:11px;color:var(--text3);margin-top:2px">lifetime XP</div>
      </div>
      <div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 16px;flex:1;min-width:80px">
        <div style="font-size:22px;font-weight:700;color:#6AB0FF">${S.streak||0}</div>
        <div style="font-size:11px;color:var(--text3);margin-top:2px">day streak</div>
      </div>
      <div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 16px;flex:1;min-width:80px">
        <div style="font-size:22px;font-weight:700;color:var(--gold)">${Math.round((totalMins||0)/60*10)/10}h</div>
        <div style="font-size:11px;color:var(--text3);margin-top:2px">time invested</div>
      </div>
      <div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 16px;flex:1;min-width:80px">
        <div style="font-size:22px;font-weight:700;color:#E88080">${S.skillsTouched||0}</div>
        <div style="font-size:11px;color:var(--text3);margin-top:2px">skills touched</div>
      </div>
    </div>

    <!-- Tab switcher -->
    <div style="display:flex;gap:4px;margin-bottom:16px;background:var(--bg3);border-radius:10px;padding:4px;border:1px solid var(--border)">
      ${[['chart','📊 XP Chart'],['history','🎓 Sessions'],['arts','🗺️ Arts & Skills']].map(function(t){
        var active = tab === t[0];
        return '<button onclick="set({progressTab:\''+t[0]+'\'})" style="flex:1;padding:7px 4px;font-size:12px;font-weight:'+(active?'700':'400')+';border-radius:7px;border:none;cursor:pointer;background:'+(active?'var(--card)':'transparent')+';color:'+(active?'var(--text1)':'var(--text3)')+';transition:all .15s;box-shadow:'+(active?'0 1px 6px rgba(0,0,0,0.3)':'none')+'">'+t[1]+'</button>';
      }).join('')}
    </div>

    <!-- Tab content -->
    ${tab === 'chart'   ? xpChart()       : ''}
    ${tab === 'history' ? sessionHistory() : ''}
    ${tab === 'arts'    ? artBreakdown()   : ''}

    <!-- ══ MY STORY ══ -->
    <div style="margin-top:32px;padding-top:24px;border-top:1px solid var(--border)">

      <!-- Section header -->
      <div style="margin-bottom:20px">
        <h2 style="font-size:20px;font-weight:700;margin-bottom:4px">My Story</h2>
        <p style="font-size:13px;color:var(--text3);line-height:1.6">What the platform has learned about you through your learning conversations. This grows quietly in the background every time you talk with the companion.</p>
      </div>

      <!-- Guiding Star -->
      ${S.guidingStar ? `
      <div style="text-align:center;padding:24px 16px;margin-bottom:20px;background:linear-gradient(135deg,rgba(0,229,200,0.06),rgba(61,123,255,0.06));border:1px solid rgba(0,229,200,0.2);border-radius:var(--r)">
        <div style="font-size:10px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--text3);margin-bottom:10px">Guiding Star</div>
        <div style="font-size:22px;font-style:italic;color:var(--wave);font-family:var(--font-display);line-height:1.4">✦ ${S.guidingStar}</div>
      </div>` : ''}

      <!-- Life-CV card -->
      <div style="background:var(--bg2);border:1px solid var(--border);border-radius:var(--r);padding:20px;margin-bottom:20px">
        ${S.learnerProfile ? `
        <div style="font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text3);margin-bottom:14px">Life Profile</div>
        <div style="font-size:13px;color:var(--text2);line-height:1.8;white-space:pre-wrap">${S.learnerProfile.trim()}</div>
        ` : `
        <div style="text-align:center;padding:24px 0;color:var(--text3)">
          <div style="font-size:28px;margin-bottom:10px">🌱</div>
          <div style="font-size:13px;line-height:1.7">Your story hasn't started growing yet.<br>Talk with the companion during a session — it listens and remembers.</div>
        </div>
        `}
      </div>

      <!-- Portfolio companion -->
      <div style="background:var(--bg2);border:1px solid rgba(0,229,200,0.2);border-radius:var(--r);padding:18px">
        <div style="font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text3);margin-bottom:4px">Companion · My Story</div>
        <div style="font-size:12px;color:var(--text3);margin-bottom:14px;line-height:1.5">Ask about what your story reveals — patterns, strengths, blind spots. This conversation doesn't change your profile.</div>
        ${renderPortfolioThread()}
      </div>

    </div>
  </div>`;
}


// ══════════════════════════════════════════════════
// HANDLERS
// ══════════════════════════════════════════════════
window.doLogin = async function() {
  const email = document.getElementById('auth-email')?.value?.trim();
  const pass  = document.getElementById('auth-password')?.value;
  if (!email || !pass) { set({authError:'Please fill in all fields'}); return; }
  // Save values to state before re-render wipes DOM
  S.authEmail = email;
  set({authLoading:true, authError:''});
  try {
    await API.login(email, pass);
    const learnerData = API.getLearner();
    set({authLoading:false, view: learnerData?.onboarding_complete ? 'dashboard' : 'onboard', learner:learnerData});
    if (learnerData?.onboarding_complete) loadDashboard();
  } catch(e) {
    var msg = 'Something went wrong — please try again';
    if (e.message) {
      var c = parseInt(e.message, 10) || 0;
      var m = e.message.toLowerCase();
      if (c === 401 || c === 403 || c === 400 || c === 422
          || m.includes('invalid') || m.includes('credentials') || m.includes('incorrect') || m.includes('unauthorized'))
        msg = 'Wrong email or password — please try again';
      else if (c === 404 || m.includes('not found'))
        msg = 'Account not found — check your email or create an account';
      else if (c === 429 || m.includes('too many'))
        msg = 'Too many attempts — please wait a moment and try again';
      else if (c >= 500)
        msg = 'Server is taking a moment — please try again in a few seconds';
    }
    set({authLoading:false, authError: msg});
  }
};

window.doRegister = async function() {
  const name  = document.getElementById('reg-name')?.value?.trim();
  const uname = document.getElementById('reg-username')?.value?.trim();
  const email = document.getElementById('reg-email')?.value?.trim();
  const pass  = document.getElementById('reg-password')?.value;
  const year  = parseInt(document.getElementById('reg-year')?.value) || null;
  // Save values to state so they survive re-render on error
  if (name)  S.regName     = name;
  if (uname) S.regUsername = uname;
  if (email) S.regEmail    = email;
  if (year)  S.regYear     = year;
  if (!name || !uname || !email || !pass) { set({authError:'Please fill in all required fields'}); return; }
  if (pass.length < 8) { set({authError:'Password must be at least 8 characters — please go back and try again'}); return; }
  set({authLoading:true, authError:''});
  try {
    await API.register(uname, email, pass, name, year);
    set({authLoading:false, view:'onboard', learner:API.getLearner()});
  } catch(e) {
    set({authLoading:false, authError: e.message || 'Registration failed'});
  }
};

// ── Civic readiness check for Polis access ───────────────────
// Learner must show minimum engagement across civic arts:
// Listen, Understand, Respect, Collaborate — at least level 1 each
// OR have completed at least 5 sessions total (grace period for new learners)
window.canAccessPolis = function() {
  if (!API.isLoggedIn()) return false;
  if ((S.streak || 0) >= 5) return true;  // 5+ day streak = good faith
  if ((S.xp || 0) >= 50)   return true;  // 50+ XP = meaningful engagement
  return false;  // default: not yet
};

window.goToPolis = function() {
  if (window.canAccessPolis()) {
    window.location.href = '/polis';
  } else {
    // Show a friendly explanation rather than a hard block
    set({showPolisGate: true});
    setTimeout(function() { set({showPolisGate: false}); }, 4000);
  }
};

window.goHome = function() { set({view:'dashboard'}); };
window.initBioregion = initBioregion;
window.resetBioregion = resetBioregion;

window.toggleProgressArt = function(slug) {
  // Toggle: clicking the open art collapses it; clicking another opens it
  set({progressArt: S.progressArt === slug ? null : slug});
};

window.doLogout = function() {
  API.logout();
  set({view:'login', authMode:'login', learner:null, streak:0, xp:0});
};

window.tapR = function(id, ok) {
  ['r0','r1','r2'].forEach(r=>{const e=document.getElementById(r);if(e){e.className='choice-btn';e.disabled=false;}});
  const el=document.getElementById(id); if(!el) return;
  el.className='choice-btn '+(ok?'ok':'no');
  ['r0','r1','r2'].forEach(r=>{const b=document.getElementById(r);if(b)b.disabled=true;});
  const fb=document.getElementById('rfb');
  if(fb){fb.style.color=ok?'var(--wave)':'var(--coral)';fb.textContent=ok?'✓ Exactly — diversity and interdependence are the foundation of all living systems.':'Think about a forest — does one species dominate, or do many coexist?';}
};

window.pickR = function(btn, resp) {
  document.querySelectorAll('.choice-btn').forEach(b=>b.className='choice-btn');
  btn.className='choice-btn ok';
  const el=document.getElementById('rfr'); if(el) el.textContent=resp;
};

window.setSelfScore = function(score, el) {
  S.selfScore = score;
  // Visual feedback — highlight selected, dim siblings
  var btns = el.parentElement.querySelectorAll('button');
  btns.forEach(function(b) {
    b.style.background   = 'var(--card)';
    b.style.borderColor  = 'var(--border)';
    b.style.color        = 'var(--text2)';
  });
  el.style.background  = 'rgba(0,229,200,0.15)';
  el.style.borderColor = 'var(--wave)';
  el.style.color       = 'var(--wave)';
  // Reveal the Complete button now that a self-score has been chosen
  var wrap = document.getElementById('complete-btn-wrap');
  if (wrap) wrap.style.display = 'block';
};

window.chkA = function(id, ok, pickedIndex) {
  if(S.answered) return; S.answered=true;
  // 2026-07-07: capture which option the learner picked so the backend
  // can persist it and the LEARNER CONTINUITY block in future prompts can
  // show "learner chose B 'X', correct was D 'Y'" — especially useful when
  // the wrong answer is close to the correct one.
  S.assessSelectedIndex = (typeof pickedIndex === 'number') ? pickedIndex : null;
  // Disable all options
  ['a0','a1','a2','a3'].forEach(a=>{const e=document.getElementById(a);if(e){e.disabled=true;e.className='choice-btn';}});
  // Mark selected button
  const el=document.getElementById(id); if(el) el.className='choice-btn '+(ok?'ok':'no');
  // If wrong, highlight the correct answer in green
  if(!ok && currentSession && currentSession.assess_question){
    const ci = currentSession.assess_question.correct_index;
    const correctBtn = document.getElementById('a'+ci);
    if(correctBtn) correctBtn.className='choice-btn ok';
  }
  // Feedback + confidence self-rating
  const fb=document.getElementById('afb');
  if(fb){
    fb.style.color=ok?'var(--wave)':'var(--coral)';
    fb.innerHTML = (ok?'✓ Correct!':'Not quite — the correct answer is highlighted above.')
      + '<div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border)">'
      + '<p style="font-size:12px;color:var(--text3);margin-bottom:8px">How well do you feel you understand this concept?</p>'
      + '<div style="display:flex;gap:6px">'
      + '<button onclick="setSelfScore(40,this)" style="flex:1;padding:7px 4px;font-size:11px;background:var(--card);border:1px solid var(--border);border-radius:6px;cursor:pointer;color:var(--text2)">🌱 Still learning</button>'
      + '<button onclick="setSelfScore(75,this)" style="flex:1;padding:7px 4px;font-size:11px;background:var(--card);border:1px solid var(--border);border-radius:6px;cursor:pointer;color:var(--text2)">✓ Getting it</button>'
      + '<button onclick="setSelfScore(100,this)" style="flex:1;padding:7px 4px;font-size:11px;background:var(--card);border:1px solid var(--border);border-radius:6px;cursor:pointer;color:var(--text2)">🚀 I knew this</button>'
      + '</div></div>';
  }
};

// Direct session start — skips interest pulse, goes straight to the art.
// Used by Recommended Next Start and individual art row clicks.
window.startDirectSession = function(artSlug) {
  currentSession = null;
  var slug = artSlug || (S.nextRec && S.nextRec.art_slug) || 'grow';
  set({view:'session', phase:0, answered:false, selfScore:null, sessionLoading:true,
       sessionStartTime: Date.now(), challengeText:'', reflectText:'', skillContext: null, skillDomain: null, skillType: null});
  loadAISession(slug);
};

// Start a session focused on a specific learning skill, routed through its primary art.
// The skill name is injected into learner_interests so the AI generates on-target challenges.
window.startSkillSession = function(skillName, fallbackArt) {
  // Pick the art with the highest weight for this specific skill from SKILL_ART_WEIGHTS.
  // This ensures e.g. "Data Analysis" routes to 'understand' (0.45), not the domain's
  // blunt primaryArt 'build' which would produce bioconstruction sessions.
  var weights = SKILL_ART_WEIGHTS[skillName];
  var artSlug = fallbackArt || 'grow';
  if (weights) {
    var topSlug = Object.keys(weights).reduce(function(a, b) {
      return weights[a] > weights[b] ? a : b;
    });
    if (topSlug) artSlug = topSlug;
  }
  currentSession = null;
  var _skillMeta = SKILL_DOMAIN_META[skillName] || {};
  set({view:'session', phase:0, answered:false, selfScore:null, sessionLoading:true,
       sessionStartTime: Date.now(), challengeText:'', reflectText:'', skillContext: skillName,
       skillDomain: _skillMeta.domain || null, skillType: _skillMeta.type || null});
  loadAISession(artSlug);
};

window.startRecommendedSession = async function() {
  SND.sessionStart();
  showInterestPulse();
};

// Retry after Groq failure — replays the exact same session trigger (art slug + skill context).
// Does NOT show the interest pulse or clear skillContext/skillDomain/skillType.
window.retryLastSession = function() {
  var retrySlug = lastSessionArtSlug || (S.nextRec && S.nextRec.art_slug) || 'grow';
  currentSession = null;
  // skillContext / skillDomain / skillType intentionally NOT reset — preserve the Mouseion skill that was clicked
  set({view:'session', phase:0, answered:false, selfScore:null, sessionLoading:true,
       sessionStartTime: Date.now(), challengeText:'', reflectText:''});
  loadAISession(retrySlug);
};

// ── Preferences modal ─────────────────────────────────────────
window.showPreferences = function() {
  var pm = document.getElementById('profile-menu');
  if (pm) pm.remove();
  var old = document.getElementById('prefs-modal');
  if (old) { old.remove(); return; }

  var l = S.learner || {};
  var curEmoji = l.avatar_emoji || '🌊';
  var curColor = l.avatar_color || '#00E5C8';
  var curName  = l.display_name || l.username || '';

  var emojiRow = EMOJIS.map(function(e) {
    var sel = curEmoji === e;
    return '<div onclick="prefPickEmoji(\''+e+'\')" style="width:36px;height:36px;display:inline-flex;align-items:center;justify-content:center;font-size:20px;border-radius:50%;cursor:pointer;border:2px solid '+(sel?'var(--wave)':'transparent')+';background:'+(sel?'var(--wave-dim)':'none')+'" id="pem-'+e+'">'+e+'</div>';
  }).join('');

  var colorRow = COLORS.map(function(c) {
    var sel = curColor === c;
    return '<div onclick="prefPickColor(\''+c+'\')" style="width:26px;height:26px;border-radius:50%;background:'+c+';cursor:pointer;border:3px solid '+(sel?'#fff':'transparent')+';display:inline-block;margin:2px" id="pcl-'+c.replace('#','')+'"></div>';
  }).join('');

  var phaseRow = PHASES.map(function(p) {
    var sel = (S.onboardPhase||'adult') === p.slug;
    return '<button onclick="prefPickPhase(\''+p.slug+'\')" id="pph-'+p.slug+'" style="padding:7px 10px;font-size:12px;border-radius:6px;cursor:pointer;border:1px solid '+(sel?'var(--wave)':'var(--border)')+';background:'+(sel?'var(--wave-dim)':'var(--bg3)')+';color:'+(sel?'var(--wave)':'var(--text2)')+'">'+p.icon+' '+p.name+'</button>';
  }).join('');

  var modal = document.createElement('div');
  modal.id = 'prefs-modal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(8,12,20,0.92);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;backdrop-filter:blur(4px)';
  modal.innerHTML =
    '<div style="background:var(--bg2);border:1px solid var(--border);border-radius:var(--r-lg);padding:28px 24px;max-width:420px;width:100%;max-height:90vh;overflow-y:auto">'
    + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">'
    + '<h3 style="font-family:var(--font-display);color:var(--text);font-size:18px">Preferences</h3>'
    + '<button onclick="document.getElementById(\'prefs-modal\').remove()" style="background:none;border:none;color:var(--text3);font-size:20px;cursor:pointer;line-height:1">×</button>'
    + '</div>'

    + '<div style="margin-bottom:18px">'
    + '<label style="font-size:12px;color:var(--text2);display:block;margin-bottom:6px">Display name</label>'
    + '<input id="pref-name" value="'+curName+'" style="width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:9px 12px;color:var(--text);font-size:14px;box-sizing:border-box">'
    + '</div>'

    + '<div style="margin-bottom:18px">'
    + '<label style="font-size:12px;color:var(--text2);display:block;margin-bottom:8px">Avatar</label>'
    + '<div id="pref-avatar-preview" style="width:56px;height:56px;border-radius:50%;background:'+curColor+'33;border:3px solid '+curColor+';display:flex;align-items:center;justify-content:center;font-size:26px;margin-bottom:10px">'+curEmoji+'</div>'
    + '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:10px">'+emojiRow+'</div>'
    + '<div style="display:flex;flex-wrap:wrap;gap:2px">'+colorRow+'</div>'
    + '</div>'

    + '<div style="margin-bottom:18px">'
    + '<label style="font-size:12px;color:var(--text2);display:block;margin-bottom:8px">' + T('prefs.language') + '</label>'
    + '<div style="display:flex;flex-wrap:wrap;gap:7px">'
    + [
        ['en','🇬🇧','English'],['fr','🇫🇷','Français'],['es','🇪🇸','Español'],
        ['de','🇩🇪','Deutsch'],['ru','🇷🇺','Русский'],
        ['vi','🇻🇳','Tiếng Việt'],['zh','🇨🇳','中文'],['ar','🇸🇦','العربية'],
      ].map(function(l) {
        var sel = (S.language||'en') === l[0];
        return '<button onclick="prefPickLang(\''+l[0]+'\')" id="plng-'+l[0]+'" '
          + 'style="padding:7px 11px;font-size:13px;border-radius:6px;cursor:pointer;'
          + 'border:1px solid '+(sel?'var(--wave)':'var(--border)')+';'
          + 'background:'+(sel?'var(--wave-dim)':'var(--bg3)')+';'
          + 'color:'+(sel?'var(--wave)':'var(--text2)')+'">'+l[1]+' '+l[2]+'</button>';
      }).join('')
    + '</div></div>'

    + '<div style="margin-bottom:24px">'
    + '<label style="font-size:12px;color:var(--text2);display:block;margin-bottom:8px">' + T('prefs.phase') + '</label>'
    + '<div style="display:flex;flex-wrap:wrap;gap:6px">'+phaseRow+'</div>'
    + '</div>'

    + '<button onclick="savePreferences()" class="btn btn-wave btn-full">' + T('prefs.save') + '</button>'
    + '</div>';

  document.body.appendChild(modal);
  // Close on backdrop click
  modal.addEventListener('click', function(e) { if(e.target===modal) modal.remove(); });

  // Track current selections in closure via temp state
  window._prefEmoji = curEmoji;
  window._prefColor = curColor;
  window._prefPhase = S.onboardPhase || 'adult';
  window._prefLang  = S.language || 'en';
};

window.prefPickEmoji = function(e) {
  window._prefEmoji = e;
  document.querySelectorAll('[id^="pem-"]').forEach(function(el) {
    el.style.border = '2px solid transparent'; el.style.background = 'none';
  });
  var el = document.getElementById('pem-'+e);
  if (el) { el.style.border='2px solid var(--wave)'; el.style.background='var(--wave-dim)'; }
  var p = document.getElementById('pref-avatar-preview');
  if (p) p.textContent = e;
};

window.prefPickColor = function(c) {
  window._prefColor = c;
  document.querySelectorAll('[id^="pcl-"]').forEach(function(el){ el.style.border='3px solid transparent'; });
  var el = document.getElementById('pcl-'+c.replace('#',''));
  if (el) el.style.border = '3px solid #fff';
  var p = document.getElementById('pref-avatar-preview');
  if (p) { p.style.background=c+'33'; p.style.borderColor=c; }
};

window.prefPickLang = function(lang) {
  window._prefLang = lang;
  document.querySelectorAll('[id^="plng-"]').forEach(function(el) {
    el.style.border='1px solid var(--border)'; el.style.background='var(--bg3)'; el.style.color='var(--text2)';
  });
  var el = document.getElementById('plng-'+lang);
  if (el) { el.style.border='1px solid var(--wave)'; el.style.background='var(--wave-dim)'; el.style.color='var(--wave)'; }
};

window.prefPickPhase = function(slug) {
  window._prefPhase = slug;
  document.querySelectorAll('[id^="pph-"]').forEach(function(el){
    el.style.border='1px solid var(--border)'; el.style.background='var(--bg3)'; el.style.color='var(--text2)';
  });
  var el = document.getElementById('pph-'+slug);
  if (el) { el.style.border='1px solid var(--wave)'; el.style.background='var(--wave-dim)'; el.style.color='var(--wave)'; }
};

window.savePreferences = async function() {
  var name = (document.getElementById('pref-name')||{}).value || '';
  try {
    await API.patch('/learners/me/preferences', {
      display_name:  name.trim() || undefined,
      avatar_emoji:  window._prefEmoji,
      avatar_color:  window._prefColor,
      phase:         window._prefPhase,
      language:      window._prefLang,
    });
    var l = Object.assign({}, S.learner||{});
    if (name.trim()) l.display_name = name.trim();
    l.avatar_emoji = window._prefEmoji;
    l.avatar_color = window._prefColor;
    localStorage.setItem('fl_learner', JSON.stringify(l));
    set({learner:l, onboardPhase:window._prefPhase, language: window._prefLang || S.language});
    document.getElementById('prefs-modal').remove();
  } catch(e) {
    console.log('Save prefs error:', e.message);
  }
};
// ── LMBoK info popup ─────────────────────────────────────────
window.goToPolis = async function() {
  try {
    var streak = await API.get('/learners/me/streak');
    var xp   = streak && streak.total_xp      ? streak.total_xp      : 0;
    var days = streak && streak.current_streak ? streak.current_streak : 0;
    if (xp >= 50 || days >= 5) {
      window.location.href = '/polis';
    } else {
      set({showPolisGate: true});
      setTimeout(function(){ set({showPolisGate:false}); }, 5000);
    }
  } catch(e) { window.location.href = '/polis'; }
};
window.showLMBoKInfo = function() {
  var old = document.getElementById('lmbok-modal');
  if (old) { old.remove(); return; }
  var modal = document.createElement('div');
  modal.id = 'lmbok-modal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(8,12,20,0.92);z-index:9999;display:flex;align-items:center;justify-content:center;padding:24px;backdrop-filter:blur(4px)';
  modal.innerHTML =
    '<div style="background:var(--bg2);border:1px solid var(--border);border-radius:var(--r-lg);padding:28px 26px;max-width:480px;width:100%">'
    + '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px">'
    + '<div style="font-size:10px;font-weight:700;letter-spacing:1.5px;color:var(--wave);text-transform:uppercase">Life Management Body of Knowledge</div>'
    + '<button onclick="document.getElementById(\'lmbok-modal\').remove()" style="background:none;border:none;color:var(--text3);font-size:22px;cursor:pointer;line-height:1;margin-left:12px">×</button>'
    + '</div>'
    + '<h2 style="font-family:var(--font-display);font-size:20px;margin-bottom:14px;line-height:1.3">Your living map of human potential</h2>'
    + '<p style="font-size:14px;color:var(--text2);line-height:1.8;margin-bottom:14px">'
    + 'The LMBoK organises everything a human being can learn, develop, and master into 15 arts across three domains — Being, Becoming, and Connecting. Rooted in the belief that free, open, lifelong learning belongs to everyone, it maps human development into measurable skills that grow at your own pace, guided by curiosity and owned by no one but you.'
    + '</p>'
    + '<p style="font-size:14px;color:var(--text2);line-height:1.8;margin-bottom:20px">'
    + 'It is not a curriculum handed to you. It is a body of knowledge navigated by you — built by the community, for the community, forever freely accessible to anyone, anywhere, at any time.'
    + '</p>'
    + '<a href="https://www.epangea.top/the-mission" target="_blank" rel="noopener" '
    + 'style="display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--wave);border:1px solid rgba(0,229,200,0.3);border-radius:20px;padding:7px 16px;text-decoration:none">'
    + '↗ Read the full mission at ePangea'
    + '</a>'
    + '</div>';
  document.body.appendChild(modal);
  modal.addEventListener('click', function(e){ if(e.target===modal) modal.remove(); });
};

window.showInterestPulse = function() {
  var old = document.getElementById('interest-modal');
  if (old) old.remove();
  var zones = [
    {e:'🏃', l:'Move & Feel',      s:'move',        d:'Physical, sensory, emotional'},
    {e:'💭', l:'Think & Notice',   s:'understand',  d:'Ideas, patterns, meaning'},
    {e:'🤝', l:'Connect & Give',   s:'listen',      d:'People, empathy, community'},
    {e:'🌱', l:'Grow & Build',     s:'grow',        d:'Making, creating, tending'},
    {e:'✨', l:'Express & Live',   s:'express',     d:'Creativity, voice, presence'},
    {e:'🎲', l:'Surprise me',      s:null,          d:'Let the frequencies decide'},
  ];
  var m = document.createElement('div');
  m.id = 'interest-modal';
  m.style.cssText = 'position:fixed;inset:0;background:rgba(8,12,20,0.93);z-index:999;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px;backdrop-filter:blur(4px)';
  m.innerHTML = '<div style="max-width:400px;width:100%">'
    + '<h2 style="font-family:var(--font-display);color:var(--wave);margin-bottom:4px;text-align:center;font-size:22px">What\'s calling you?</h2>'
    + '<p style="color:var(--text3);font-size:13px;text-align:center;margin-bottom:20px">Choose what resonates right now</p>'
    + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">'
    + zones.map(function(z){
        var arg = z.s ? "'"+z.s+"'" : 'null';
        return '<button onclick="pickInterest('+arg+')" style="background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:14px 12px;text-align:left;cursor:pointer;width:100%">'
          + '<div style="font-size:22px;margin-bottom:5px">'+z.e+'</div>'
          + '<div style="font-weight:600;color:var(--text);font-size:13px;margin-bottom:2px">'+z.l+'</div>'
          + '<div style="color:var(--text2);font-size:11px">'+z.d+'</div>'
          + '</button>';
      }).join('')
    + '</div>'
    + '<button onclick="pickInterest(null)" style="margin-top:14px;width:100%;background:none;border:none;color:var(--text3);font-size:12px;cursor:pointer;padding:8px">Skip — use engine recommendation</button>'
    + '</div>';
  document.body.appendChild(m);
};

window.pickInterest = function(slug) {
  var old = document.getElementById('interest-modal');
  if (old) old.remove();
  currentSession = null;
  var artSlug = slug || (S.nextRec && S.nextRec.art_slug) || 'grow';
  set({view:'session', phase:0, answered:false, selfScore:null, sessionLoading:true,
       sessionStartTime: Date.now(), challengeText:'', reflectText:''});
  loadAISession(artSlug);
};

window.finishSession = function() {
  SND.sessionComplete();
  if (API.isLoggedIn()) {
    // Use active session ID if we have one, otherwise start a new one
    var artId = 14; // default: grow
    var skillId = 1;
    if (currentSession) {
      artId  = currentSession.art_id  || 14;
      skillId= currentSession.skill_id || 1;
    }
    var startPayload = {
          skill_id: skillId,
          art_id:   artId,
          title:    currentSession ? currentSession.title : 'The Art of Growing',
          // 'engine' only when engine recommended AND learner didn't override with a skill click
          recommended_by: (!S.skillContext && S.nextRec) ? 'engine' : 'learner',
          engine_reasoning: (!S.skillContext && S.nextRec) ? S.nextRec : null,
          language: S.language || 'en',
        };
    // Use existing session_id if AI generated one, else start fresh
    var sessionPromise = (currentSession && currentSession.session_id)
      ? Promise.resolve({id: currentSession.session_id})
      : API.post('/sessions/start', startPayload);

    sessionPromise
      .then(function(s) {
        return API.post('/sessions/' + s.id + '/complete', {
          duration_seconds: Math.round((Date.now() - (S.sessionStartTime || Date.now())) / 1000) || 900,
          xp_earned:        18,
          challenge_response: S.challengeText || '',
          reflect_response:   S.reflectText   || '',
          phase_reached:      5,
          assess_score:       S.selfScore || (S.answered ? 85 : 50),
          // 2026-07-07: which option did the learner actually pick? Backend
          // persists this on the session row and uses it to build the
          // LEARNER CONTINUITY block in future generations.
          assess_selected_index: S.assessSelectedIndex,
          // Pass skill context so backend can (when ready) distribute XP across contributing arts
          skill_context:      S.skillContext || null,
          contributing_arts:  S.skillContext ? Object.keys(window.SKILL_ART_WEIGHTS && SKILL_ART_WEIGHTS[S.skillContext] || {}) : null,
        });
      })
      .then(function(result) {
        // Update radar from API response
        if (result && result.radar) {
          var updates = {};
          if (result.radar.group_scores) updates.radar = result.radar.group_scores;
          if (result.radar.art_scores) {
            var _s = result.radar.art_scores;
            if (Object.keys(_s).some(function(k){ return _s[k] > 0; })) {
              updates.artScores = _s;
              try { localStorage.setItem('fl_artScores', JSON.stringify(_s)); } catch(e) {}
            }
          }
          if (result.next_session) updates.nextRec = result.next_session;
          set(updates);
        }
        loadDashboard();
      })
      .catch(function(e) { console.log('Session save:', e.message); loadDashboard(); });
  }
  // Fire-and-forget: distil sandbox conversation into learner profile
  if (S.sandboxMessages && S.sandboxMessages.length >= 2) triggerProfileUpdate();
  currentSession = null;
  S.sandboxMessages = [];
  S.sandboxOpen = false;
  set({view:'dashboard', phase:0, answered:false, selfScore:null, xp: S.xp + 18, sessionStartTime: null});
};

window.set = set;

// ══════════════════════════════════════════════════
// ONBOARDING
// ══════════════════════════════════════════════════
var ARTS_DATA = [
  {slug:'move',      name:'Move',        group:'Being',      tag:'Inner-connectedness & physical growth'},
  {slug:'eat',       name:'Eat',         group:'Being',      tag:'Nourishment & bodily wisdom'},
  {slug:'feel',      name:'Feel',        group:'Being',      tag:'Emotional awareness & growth'},
  {slug:'notice',    name:'Notice',      group:'Being',      tag:'Outward awareness without judgement'},
  {slug:'express',   name:'Express',     group:'Being',      tag:'Creativity & self-determination'},
  {slug:'live',      name:'Live',        group:'Becoming',   tag:'Personal needs, rights & duties'},
  {slug:'listen',    name:'Listen',      group:'Becoming',   tag:'Empathy & civil discourse'},
  {slug:'give',      name:'Give',        group:'Becoming',   tag:'Compassion & selfless contribution'},
  {slug:'receive',   name:'Receive',     group:'Becoming',   tag:'Acceptance, humility & equity'},
  {slug:'collaborate',name:'Collaborate',group:'Becoming',   tag:'Shared vision & inclusive action'},
  {slug:'understand',name:'Understand',  group:'Connecting', tag:'First principles & theory of knowledge'},
  {slug:'respect',   name:'Respect',     group:'Connecting', tag:'The golden rule extended to all life'},
  {slug:'build',     name:'Build',       group:'Connecting', tag:'Green design & bioconstruction'},
  {slug:'grow',      name:'Grow',        group:'Connecting', tag:'Regenerative agriculture & food sovereignty'},
  {slug:'consume',   name:'Consume',     group:'Connecting', tag:'Water, resource & energy stewardship'},
];

// ── Art → Domain weighted mapping ──────────────────────────
// Each art contributes fractionally to 1–4 of the 8 learning domains.
// Weights per art sum to 1.0. Used to compute the 8-domain "what you learn" radar.
var DOMAIN_WEIGHTS = {
  move:        {physical:0.65, emotional:0.20, meta:0.15},
  eat:         {physical:0.45, emotional:0.30, cognitive:0.15, meta:0.10},
  feel:        {emotional:0.65, social:0.20, meta:0.15},
  notice:      {cognitive:0.35, meta:0.30, technical:0.20, emotional:0.15},
  express:     {creative:0.55, language:0.25, emotional:0.20},
  live:        {meta:0.25, cognitive:0.25, social:0.20, technical:0.30},
  listen:      {social:0.45, language:0.35, emotional:0.20},
  give:        {social:0.50, emotional:0.30, meta:0.20},
  receive:     {emotional:0.45, social:0.30, meta:0.25},
  collaborate: {social:0.55, language:0.20, cognitive:0.25},
  understand:  {cognitive:0.60, meta:0.20, technical:0.20},
  respect:     {social:0.40, emotional:0.35, cognitive:0.25},
  build:       {creative:0.35, technical:0.30, cognitive:0.20, physical:0.15},
  grow:        {physical:0.30, cognitive:0.25, technical:0.25, meta:0.20},
  consume:     {cognitive:0.35, technical:0.25, meta:0.25, social:0.15},
};

function computeDomainScores(artScores) {
  var DOMAINS = ['cognitive','creative','physical','social','language','emotional','meta','technical'];
  var norm = {}, raw = {};
  DOMAINS.forEach(function(d){ norm[d]=0; raw[d]=0; });
  Object.keys(DOMAIN_WEIGHTS).forEach(function(art) {
    var weights = DOMAIN_WEIGHTS[art];
    var artVal  = artScores[art] || 0;
    Object.keys(weights).forEach(function(domain) {
      norm[domain] += weights[domain];
      raw[domain]  += artVal * weights[domain];
    });
  });
  var result = {};
  DOMAINS.forEach(function(d){ result[d] = norm[d]>0 ? Math.min(raw[d]/norm[d], 1.0) : 0; });
  return result;
}

// ── Skill → Art weighted mapping ───────────────────────────
// Each learning skill is a weighted blend of the human arts that feed it.
// Mirrors the art→domain layer one level down: art scores → skill scores.
// Weights per skill need not sum to 1.0 (they are normalised in computeSkillScore).
var SKILL_ART_WEIGHTS = {
  // COGNITIVE & INTELLECTUAL
  'Critical Thinking':    {understand:0.50, notice:0.30, live:0.20},
  'Problem Solving':      {understand:0.40, build:0.35, notice:0.25},
  'Systems Thinking':     {understand:0.45, live:0.30, consume:0.25},
  'Memory & Retention':   {understand:0.40, notice:0.35, consume:0.25},
  'Decision Making':      {understand:0.40, live:0.35, notice:0.25},
  'Project Management':   {understand:0.35, live:0.35, collaborate:0.20, notice:0.10},
  // CREATIVE & ARTISTIC
  'Visual Art':                       {express:0.70, notice:0.20, build:0.10},
  'Music & Rhythm':                   {express:0.60, move:0.25, feel:0.15},
  'Creative Writing':                 {express:0.55, listen:0.25, notice:0.20},
  'Drama & Theatre':                  {express:0.60, collaborate:0.25, notice:0.15},
  'Improvisation & Public Speaking':  {express:0.50, listen:0.30, collaborate:0.20},
  'Craftsmanship & Making':           {build:0.60, express:0.25, notice:0.15},
  // PHYSICAL & MOTOR
  'Gross Motor':          {move:0.70, eat:0.20, grow:0.10},
  'Fine Motor':           {move:0.55, build:0.30, notice:0.15},
  'Physical Fitness':     {move:0.60, eat:0.25, grow:0.15},
  'Dance & Movement':     {move:0.65, express:0.25, feel:0.10},
  'Body Awareness':       {move:0.50, notice:0.30, feel:0.20},
  'First Aid & Nursing':  {move:0.45, notice:0.35, give:0.20},
  // SOCIAL & RELATIONAL
  'Collaboration':           {collaborate:0.55, give:0.25, listen:0.20},
  'Conflict Resolution':     {listen:0.40, respect:0.35, collaborate:0.25},
  'Empathetic Leadership':   {collaborate:0.35, give:0.30, listen:0.25, live:0.10},
  'Negotiation':             {listen:0.40, collaborate:0.35, live:0.25},
  'Cultural Competence':     {respect:0.50, listen:0.30, understand:0.20},
  'Parenting & Caregiving':  {give:0.55, listen:0.25, feel:0.20},
  // LANGUAGE & COMMUNICATION
  'Active Reading':              {understand:0.50, notice:0.35, consume:0.15},
  'Active Listening':            {listen:0.60, notice:0.25, feel:0.15},
  'Storytelling':                {express:0.50, listen:0.30, feel:0.20},
  'Debate & Argumentation':      {listen:0.40, understand:0.35, collaborate:0.25},
  'Foreign Language Acquisition':{listen:0.45, understand:0.30, express:0.25},
  'Rhetoric & Persuasion':       {express:0.45, understand:0.35, listen:0.20},
  // EMOTIONAL & PSYCHOLOGICAL
  'Self-Awareness':          {feel:0.55, notice:0.30, move:0.15},
  'Emotional Regulation':    {feel:0.55, move:0.25, notice:0.20},
  'Empathy and Compassion':  {feel:0.45, listen:0.35, give:0.20},
  'Self-Efficacy':           {feel:0.40, live:0.35, move:0.25},
  'Contemplative Practice':  {notice:0.55, feel:0.35, move:0.10},
  'Gratitude & Appreciation':{feel:0.45, notice:0.35, receive:0.20},
  // META-LEARNING
  'Learning How to Learn':       {notice:0.40, understand:0.35, live:0.25},
  'Self-Regulation':             {live:0.40, move:0.35, notice:0.25},
  'Personal Values':             {live:0.45, feel:0.30, notice:0.25},
  'Curiosity and Exploration':   {notice:0.50, understand:0.30, consume:0.20},
  'Vision, Mission and Purpose': {live:0.55, understand:0.25, give:0.20},
  'Mentorship & Teaching':       {give:0.40, understand:0.35, listen:0.25},
  // TOOLS & SYSTEMS
  'Digital Literacy':            {consume:0.40, understand:0.40, notice:0.20},
  'Data Analysis & Statistics':  {understand:0.50, notice:0.30, consume:0.20},
  'Design Thinking':             {understand:0.35, collaborate:0.30, express:0.20, build:0.15},
  'Philosophy & Ethics':         {understand:0.35, respect:0.35, live:0.30},
  'Permaculture':                {grow:0.50, build:0.30, respect:0.20},
  'Cooking & Nutrition':         {eat:0.55, grow:0.25, build:0.20},
};

// Maps each skill name → learning_domain + skill_type for scaffold context (P18).
// Domain labels match _DOMS; skill_type follows Bloom's taxonomy (cognitive/affective/psychomotor).
var SKILL_DOMAIN_META = {
  // COGNITIVE & INTELLECTUAL
  'Critical Thinking':    {domain:'Cognitive & Intellectual', type:'cognitive'},
  'Problem Solving':      {domain:'Cognitive & Intellectual', type:'cognitive'},
  'Systems Thinking':     {domain:'Cognitive & Intellectual', type:'cognitive'},
  'Memory & Retention':   {domain:'Cognitive & Intellectual', type:'cognitive'},
  'Decision Making':      {domain:'Cognitive & Intellectual', type:'cognitive'},
  'Project Management':   {domain:'Cognitive & Intellectual', type:'cognitive'},
  // CREATIVE & ARTISTIC
  'Visual Art':                       {domain:'Creative & Artistic',      type:'affective,psychomotor'},
  'Music & Rhythm':                   {domain:'Creative & Artistic',      type:'affective,psychomotor'},
  'Creative Writing':                 {domain:'Creative & Artistic',      type:'cognitive,affective'},
  'Drama & Theatre':                  {domain:'Creative & Artistic',      type:'affective,psychomotor'},
  'Improvisation & Public Speaking':  {domain:'Creative & Artistic',      type:'affective,psychomotor'},
  'Craftsmanship & Making':           {domain:'Creative & Artistic',      type:'affective,psychomotor'},
  // PHYSICAL & MOTOR
  'Gross Motor':          {domain:'Physical & Motor',          type:'psychomotor'},
  'Fine Motor':           {domain:'Physical & Motor',          type:'psychomotor'},
  'Physical Fitness':     {domain:'Physical & Motor',          type:'psychomotor'},
  'Dance & Movement':     {domain:'Physical & Motor',          type:'affective,psychomotor'},
  'Body Awareness':       {domain:'Physical & Motor',          type:'affective,psychomotor'},
  'First Aid & Nursing':  {domain:'Physical & Motor',          type:'cognitive,psychomotor'},
  // SOCIAL & RELATIONAL
  'Collaboration':           {domain:'Social & Relational',      type:'cognitive,affective'},
  'Conflict Resolution':     {domain:'Social & Relational',      type:'cognitive,affective'},
  'Empathetic Leadership':   {domain:'Social & Relational',      type:'cognitive,affective'},
  'Negotiation':             {domain:'Social & Relational',      type:'cognitive,affective'},
  'Cultural Competence':     {domain:'Social & Relational',      type:'cognitive,affective'},
  'Parenting & Caregiving':  {domain:'Social & Relational',      type:'affective'},
  // LANGUAGE & COMMUNICATION
  'Active Reading':               {domain:'Language & Communication', type:'cognitive'},
  'Active Listening':             {domain:'Language & Communication', type:'cognitive,affective'},
  'Storytelling':                 {domain:'Language & Communication', type:'cognitive,affective'},
  'Debate & Argumentation':       {domain:'Language & Communication', type:'cognitive'},
  'Foreign Language Acquisition': {domain:'Language & Communication', type:'cognitive,affective'},
  'Rhetoric & Persuasion':        {domain:'Language & Communication', type:'cognitive,affective'},
  // EMOTIONAL & PSYCHOLOGICAL
  'Self-Awareness':           {domain:'Emotional & Psychological', type:'affective'},
  'Emotional Regulation':     {domain:'Emotional & Psychological', type:'affective'},
  'Empathy and Compassion':   {domain:'Emotional & Psychological', type:'affective'},
  'Self-Efficacy':            {domain:'Emotional & Psychological', type:'affective,psychomotor'},
  'Contemplative Practice':   {domain:'Emotional & Psychological', type:'affective'},
  'Gratitude & Appreciation': {domain:'Emotional & Psychological', type:'affective'},
  // META-LEARNING
  'Learning How to Learn':        {domain:'Meta-Learning',           type:'cognitive'},
  'Self-Regulation':              {domain:'Meta-Learning',           type:'cognitive,affective'},
  'Personal Values':              {domain:'Meta-Learning',           type:'affective'},
  'Curiosity and Exploration':    {domain:'Meta-Learning',           type:'cognitive,affective'},
  'Vision, Mission and Purpose':  {domain:'Meta-Learning',           type:'cognitive,affective'},
  'Mentorship & Teaching':        {domain:'Meta-Learning',           type:'cognitive,affective'},
  // TOOLS & SYSTEMS
  'Digital Literacy':             {domain:'Tools & Systems',         type:'cognitive'},
  'Data Analysis & Statistics':   {domain:'Tools & Systems',         type:'cognitive'},
  'Design Thinking':              {domain:'Tools & Systems',         type:'cognitive,psychomotor'},
  'Philosophy & Ethics':          {domain:'Tools & Systems',         type:'cognitive,affective'},
  'Permaculture':                 {domain:'Tools & Systems',         type:'cognitive,psychomotor'},
  'Cooking & Nutrition':          {domain:'Tools & Systems',         type:'cognitive,psychomotor'},
};

function computeSkillScore(skillName, artScores) {
  var weights = SKILL_ART_WEIGHTS[skillName];
  if (!weights) return 0;
  var norm = 0, raw = 0;
  Object.keys(weights).forEach(function(art) {
    norm += weights[art];
    raw  += (artScores[art] || 0) * weights[art];
  });
  return norm > 0 ? Math.min(raw / norm, 1.0) : 0;
}

var PHASES = [
  {slug:'prenascent', icon:'🌱', name:'Expecting a child', desc:'Pregnancy \u00B7 preparing for parenthood'},
  {slug:'nascent',    icon:'🌿', name:'Newborn & Infant',  desc:'Ages 0\u20132 \u00B7 attuning to a new life'},
  {slug:'child',      icon:'🧒', name:'Child',            desc:'Ages 3\u201311 \u00B7 curiosity-led exploration'},
  {slug:'adolescent', icon:'🔥', name:'Adolescent',       desc:'Ages 12\u201317 \u00B7 identity & independence'},
  {slug:'adult',      icon:'🌳', name:'Adult',            desc:'Ages 18\u201360 \u00B7 building & contributing'},
  {slug:'elder',      icon:'🍂', name:'Elder',            desc:'Ages 61+ \u00B7 wisdom & transmission'},
];

var EMOJIS = ['🌊','🔥','🌿','⚡','🎵','🦋','🌙','🌸','🐉','🦁','🌍','✨'];
var COLORS = ['#00E5C8','#3D7BFF','#FF6B6B','#FFD166','#9B72FF','#6DC86D','#FF9F43','#EE5A24','#0652DD','#C4E538'];

function pips(current) {
  return PHASES.map(function(_,i) {
    return '<div class="onboard-pip' + (i < current ? ' done' : '') + '"></div>';
  }).join('') + '<div class="onboard-pip' + (current >= 5 ? ' done' : '') + '"></div>'
    + '<div class="onboard-pip' + (current >= 6 ? ' done' : '') + '"></div>';
}

function OnboardPage() {
  var step = S.onboardStep;
  var inner = '';

  if (step === 1) {
    inner = "<div class=\"onboard-step\">Step 1 of 5</div>"
      + "<div class=\"onboard-title\">Welcome to the frequency \uD83C\uDF0A</div>"
      + "<div class=\"onboard-sub\">This is a space for lifelong learning \u2014 free, open, and entirely yours."
      + " No grades, no competition, no wrong answers. Just you, growing at your own pace.<br><br>"
      + "Let us start by getting to know you a little.</div>"
      + "<button class=\"btn btn-wave btn-full btn-lg\" onclick=\"set({onboardStep:2})\">Let us go \u2192</button>";
  }

  else if (step === 2) {
    inner = "<div class=\"onboard-step\">Step 2 of 5 \u00B7 Your name</div>"
      + "<div class=\"onboard-title\">What shall we call you?</div>"
      + "<div class=\"onboard-sub\">This is how you will appear on your journey."
      + " It can be your real name, a nickname, anything that feels like you.</div>"
      + "<div class=\"form-group\"><input class=\"form-input\" id=\"ob-name\" type=\"text\"" 
      + " placeholder=\"Your name...\" value=\"" + S.onboardName + "\" style=\"font-size:18px;padding:14px\"/></div>"
      + "<button class=\"btn btn-wave btn-full btn-lg\" onclick=\"obSetName()\">Continue \u2192</button>";
  }

  else if (step === 3) {
    var phaseCards = PHASES.map(function(p) {
      var sel = S.onboardPhase === p.slug ? " sel" : "";
      return "<div class=\"phase-card" + sel + "\" onclick=\"obPhase('" + p.slug + "');\">"
        + "<div class=\"phase-icon\">" + p.icon + "</div>"
        + "<div class=\"phase-name\">" + p.name + "</div>"
        + "<div class=\"phase-desc\">" + p.desc + "</div>"
        + "</div>";
    }).join('');
    inner = "<div class=\"onboard-step\">Step 3 of 5 \u00B7 Your phase</div>"
      + "<div class=\"onboard-title\">Where are you in life?</div>"
      + "<div class=\"onboard-sub\">Every phase has its own gifts."
      + " There is no better or worse \u2014 just where you are right now.</div>"
      + "<div class=\"phase-grid\">" + phaseCards + "</div>"
      + "<button class=\"btn btn-wave btn-full btn-lg\" "
      + (S.onboardPhase ? "" : "disabled ")
      + "onclick=\"set({onboardStep:4})\">Continue \u2192</button>";
  }

  else if (step === 4) {
    var groupColors = {Being:"var(--wave)", Becoming:"var(--deep)", Connecting:"var(--gold)"};
    var artCards = ARTS_DATA.map(function(a) {
      var sel = S.onboardArt === a.slug ? " sel" : "";
      var col = groupColors[a.group] || "var(--wave)";
      var borderStyle = S.onboardArt === a.slug ? "border-color:" + col + ";" : "";
      return "<div class=\"art-pick" + sel + "\" style=\"" + borderStyle + "\" onclick=\"obArt('" + a.slug + "');\">"
        + "<div class=\"art-name\" style=\"color:" + col + "\">" + a.name + "</div>"
        + "<div class=\"art-tag\">" + a.tag + "</div>"
        + "</div>";
    }).join('');
    inner = "<div class=\"onboard-step\">Step 4 of 5 \u00B7 Your first art</div>"
      + "<div class=\"onboard-title\">What pulls you right now?</div>"
      + "<div class=\"onboard-sub\">Choose the art that speaks to where you are today."
      + " This shapes your first session \u2014 you can explore all 15 arts over time.</div>"
      + "<div class=\"art-grid\">" + artCards + "</div>"
      + "<button class=\"btn btn-wave btn-full btn-lg\" "
      + (S.onboardArt ? "" : "disabled ")
      + "onclick=\"set({onboardStep:5})\">Continue \u2192</button>";
  }

  else if (step === 5) {
    var emojiOpts = EMOJIS.map(function(e) {
      var sel = S.onboardEmoji === e ? " sel" : "";
      return "<div class=\"emoji-opt" + sel + "\" onclick=\"obEmoji('" + e + "');\">" + e + "</div>";
    }).join('');
    var colorOpts = COLORS.map(function(c) {
      var sel = S.onboardColor === c ? " sel" : "";
      return "<div class=\"color-opt" + sel + "\" style=\"background:" + c + "\" onclick=\"obColor('" + c + "');\">" + "</div>";
    }).join('');
    inner = "<div class=\"onboard-step\">Step 5 of 6 \u00B7 Your avatar</div>"
      + "<div class=\"onboard-title\">Make it yours</div>"
      + "<div class=\"onboard-sub\">Your avatar is your presence on the platform."
      + " Pick what feels right \u2014 you can always change it later.</div>"
      + "<div style=\"text-align:center;margin-bottom:20px\">"
      + "<div style=\"width:72px;height:72px;border-radius:50%;background:" + S.onboardColor + "33;"
      + "border:3px solid " + S.onboardColor + ";display:inline-flex;align-items:center;"
      + "justify-content:center;font-size:32px;box-shadow:0 0 24px " + S.onboardColor + "44\">"
      + S.onboardEmoji + "</div></div>"
      + "<h4 style=\"margin-bottom:10px\">Choose your wave</h4>"
      + "<div class=\"emoji-grid\">" + emojiOpts + "</div>"
      + "<h4 style=\"margin-bottom:10px\">Choose your colour</h4>"
      + "<div class=\"color-grid\">" + colorOpts + "</div>"
      + "<button class=\"btn btn-wave btn-full btn-lg\" onclick=\"set({onboardStep:6})\">Continue \u2192</button>";
  }

  else if (step === 6) {
    var groups6 = [
      {key:'being',      emoji:'🧘', label:'Being',      desc:'Moving, feeling, noticing, expressing', color:'var(--wave)'},
      {key:'becoming',   emoji:'🤝', label:'Becoming',   desc:'Living, listening, giving, collaborating', color:'var(--deep)'},
      {key:'connecting', emoji:'🌍', label:'Connecting', desc:'Understanding, building, growing, consuming', color:'var(--gold)'},
    ];
    var fam = S.onboardFamiliarity || {};
    inner = "<div class=\"onboard-step\">Step 6 of 6 \u00B7 Your starting point</div>"
      + "<div class=\"onboard-title\">Where are you right now?</div>"
      + "<div class=\"onboard-sub\">This helps the engine meet you where you are \u2014 not where it assumes you should be.</div>"
      + groups6.map(function(g) {
          var cur = fam[g.key] !== undefined ? fam[g.key] : -1;
          return "<div style=\"margin-bottom:18px\">"
            + "<div style=\"font-weight:600;color:" + g.color + ";font-size:13px;margin-bottom:8px\">" + g.emoji + " " + g.label
            + " <span style=\"color:var(--text3);font-weight:400;font-size:12px\">\u2014 " + g.desc + "</span></div>"
            + "<div style=\"display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px\">"
            + [['\uD83C\uDF31','New to this',0],['\uD83D\uDCD6','Some experience',1],['\u2713','Comfortable',2]].map(function(opt) {
                var sel = cur === opt[2];
                return "<button onclick=\"obFamiliarity('" + g.key + "'," + opt[2] + ")\" "
                  + "style=\"padding:9px 4px;font-size:11px;line-height:1.4;"
                  + "background:" + (sel ? "rgba(0,229,200,0.15)" : "var(--card)") + ";"
                  + "border:1px solid " + (sel ? "var(--wave)" : "var(--border)") + ";"
                  + "border-radius:6px;cursor:pointer;"
                  + "color:" + (sel ? "var(--wave)" : "var(--text)") + "\">"
                  + opt[0] + "<br>" + opt[1] + "</button>";
              }).join('')
            + "</div></div>";
        }).join('')
      + "<button class=\"btn btn-wave btn-full btn-lg\" onclick=\"obComplete()\">Begin my journey \u2192</button>";
  }

  return "<div class=\"onboard-wrap\"><div class=\"onboard-card\">"
    + "<div class=\"logo\" style=\"margin-bottom:20px;font-size:clamp(13px,3.5vw,18px);white-space:nowrap\">Surfing the Frequencies</div>"
    + "<div class=\"onboard-progress\">" + pips(step) + "</div>"
    + inner
    + "</div></div>";
}

window.obPhase  = function(slug) { SND.step(); set({onboardPhase: slug}); };
window.obArt    = function(slug) { SND.tap(); set({onboardArt: slug}); };
window.obEmoji  = function(e)    { set({onboardEmoji: e}); };
window.obColor  = function(c)    { set({onboardColor: c}); };
window.obFamiliarity = function(group, level) {
  var fam = Object.assign({}, S.onboardFamiliarity || {});
  fam[group] = level;
  set({onboardFamiliarity: fam});
};

window.obSetName = function() {
  var name = document.getElementById('ob-name');
  if (!name || !name.value.trim()) return;
  set({onboardName: name.value.trim(), onboardStep: 3});
};

window.obComplete = async function() {
  try {
    await API.patch('/learners/me/preferences', {
      avatar_emoji:  S.onboardEmoji,
      avatar_color:  S.onboardColor,
      phase:         S.onboardPhase,
      display_name:  S.onboardName,
      first_art:     S.onboardArt,
    });
  } catch(e) { console.log('Preferences save:', e.message); }

  // Seed initial skill progress from familiarity self-assessment
  if (S.onboardFamiliarity && Object.keys(S.onboardFamiliarity).length > 0) {
    try {
      await API.post('/learners/me/seed-progress', { familiarity: S.onboardFamiliarity });
    } catch(e) { console.log('Seed progress:', e.message); }
  }
  // Mark onboarded on server (persists across devices) + locally
  try { await API.patch('/auth/me', { onboarding_complete: true }); } catch(e) { console.log('Onboarding flag sync:', e.message); }
  localStorage.setItem('fl_onboarded', '1');
  localStorage.setItem('fl_first_art', S.onboardArt);
  // Update learner display name + onboarding flag in local cache
  var l = S.learner || {};
  l.display_name = S.onboardName || l.display_name;
  l.onboarding_complete = true;
  localStorage.setItem('fl_learner', JSON.stringify(l));
  set({
    learner: l,
    view: 'session',
    phase: 0,
    answered: false,
  });
  loadDashboard();
};

// ══════════════════════════════════════════════════
// RENDER
// ══════════════════════════════════════════════════
// ══════════════════════════════════════════════════
// BIOREGION PAGE
// Collective portraits of the earth's living places
// ══════════════════════════════════════════════════

window.openBioregionForm = function(name, prefillText) {
  var bs = _bioregionState;
  var formName = name || ((bs && bs.profile && bs.profile.name) ? bs.profile.name
    : (bs && bs.placeName) ? bs.placeName : '');
  set({bioregionForm:true, bioregionFormName:formName,
       bioregionFormText: prefillText || '', bioregionFormError:''});
};
window.cancelBioregionForm = function() {
  set({bioregionForm:false, bioregionFormError:''});
};
window.loadBioregionPage = function() {
  set({view:'bioregion', bioregionPortrait:null});
  var p1 = (!S.bioregionPortraits) ? _fetchBioregionPortraits() : Promise.resolve();
  var p2 = (!S.bioregionContribLoaded) ? _fetchMyContribution() : Promise.resolve();
  Promise.all([p1, p2]).then(function() { _maybeLoadDraft(); });
};

function _fetchBioregionPortraits() {
  set({bioregionLoading:true});
  var bs = _bioregionState;
  var path = '/bioregions';
  if (bs && bs.lat != null && bs.lng != null) {
    path += '?lat=' + bs.lat + '&lng=' + bs.lng;
  }
  return API.get(path).then(function(data) {
    set({bioregionPortraits: data.portraits || [], bioregionLoading:false});
  }).catch(function() {
    set({bioregionPortraits: [], bioregionLoading:false});
  });
}

function _fetchMyContribution() {
  return API.get('/bioregions/my-contribution').then(function(data) {
    set({bioregionContrib: data.contribution, bioregionContribLoaded:true});
  }).catch(function() {
    set({bioregionContribLoaded:true});
  });
}

function _maybeLoadDraft() {
  if (S.bioregionContrib) return;          // already contributed
  if (S.bioregionDraft !== null) return;   // false = checked/no draft; obj = has draft
  if (S.bioregionDraftLoading) return;     // already in flight
  var bs = _bioregionState;
  if (!bs || bs.lat == null || bs.lng == null) return;  // no GPS coords
  // Skip if any portrait is already within 50 km
  var portraits = S.bioregionPortraits || [];
  for (var i = 0; i < portraits.length; i++) {
    if (portraits[i].distance_km != null && portraits[i].distance_km <= 50) return;
  }
  _fetchBioregionDraft();
}

function _fetchBioregionDraft() {
  var bs = _bioregionState;
  if (!bs || bs.lat == null) return;
  set({bioregionDraftLoading:true});
  var placeName = (bs.profile && bs.profile.name) ? bs.profile.name
    : (bs.placeName || '');
  API.post('/bioregions/draft', {lat: bs.lat, lng: bs.lng, place_name: placeName})
    .then(function(data) {
      if (data && data.draft) {
        set({bioregionDraft: data.draft, bioregionDraftLoading: false,
             bioregionDraftAccepted: {summary:false, watershed:false, climate:false,
                                      species:false, vitality:false,
                                      economy:false, material_culture:false}});
      } else {
        set({bioregionDraft: false, bioregionDraftLoading: false});
      }
    })
    .catch(function() {
      set({bioregionDraft: false, bioregionDraftLoading: false});
    });
}

window.viewBioregionPortrait = function(id) {
  set({bioregionPortrait:null, bioregionLoading:true});
  API.get('/bioregions/'+id).then(function(data) {
    set({bioregionPortrait:data, bioregionLoading:false});
  }).catch(function() {
    set({bioregionLoading:false});
  });
};

window.submitBioregionContrib = function() {
  var name = S.bioregionFormName.trim();
  var text = S.bioregionFormText.trim();
  if (!name) { set({bioregionFormError:'Please give your bioregion a name.'}); return; }
  if (text.length < 20) { set({bioregionFormError:'Please write at least 20 characters.'}); return; }
  var bs = _bioregionState;
  set({bioregionFormSaving:true, bioregionFormError:''});
  API.post('/bioregions/contribute', {
    bioregion_name: name,
    statement: text,
    lat: (bs && bs.lat) || null,
    lng: (bs && bs.lng) || null,
  }).then(function() {
    set({bioregionFormSaving:false, bioregionForm:false, bioregionFormText:'', bioregionFormName:'',
         bioregionContribLoaded:false, bioregionPortraits:null,
         bioregionDraft:null, bioregionDraftAccepted:null, bioregionDraftLoading:false});
    _fetchMyContribution();
    _fetchBioregionPortraits();
  }).catch(function(e) {
    set({bioregionFormSaving:false, bioregionFormError: e && e.detail ? e.detail : 'Could not save — please try again.'});
  });
};

window.withdrawBioregionContrib = function() {
  if (!confirm('Withdraw your contribution? This cannot be undone.')) return;
  API.delete('/bioregions/my-contribution').then(function() {
    set({bioregionContrib:null, bioregionContribLoaded:false, bioregionPortraits:null,
         bioregionDraft:null, bioregionDraftAccepted:null});
    _fetchMyContribution();
    _fetchBioregionPortraits();
  }).catch(function(){});
};

window.draftSectionToggle = function(key) {
  if (!S.bioregionDraftAccepted) return;
  var updated = Object.assign({}, S.bioregionDraftAccepted);
  updated[key] = !updated[key];
  set({bioregionDraftAccepted: updated});
};

window.buildStatementFromDraft = function() {
  var draft = S.bioregionDraft;
  var accepted = S.bioregionDraftAccepted;
  if (!draft || !accepted) return;
  var LABELS = {summary:'Overview', watershed:'Watershed & Water', climate:'Climate',
                species:'Species & Life', vitality:'Vitality',
                economy:'Economy & Livelihoods', material_culture:'Material Culture'};
  var parts = [];
  ['summary','watershed','climate','species','vitality','economy','material_culture'].forEach(function(k) {
    if (accepted[k] && draft[k]) parts.push(LABELS[k] + ': ' + draft[k]);
  });
  openBioregionForm(draft.place_name || '', parts.join('\n\n'));
};

function BioregionPage() {
  // ── Single portrait view ─────────────────────────────────────────────────
  if (S.bioregionPortrait) {
    var p = S.bioregionPortrait;
    var voicesHtml = (p.voices && p.voices.length)
      ? p.voices.map(function(v) {
          return '<div style="margin-bottom:16px;padding:14px 16px;background:var(--bg2);border-radius:var(--r-sm);border-left:3px solid rgba(0,229,200,0.3)">'
            + '<div style="font-size:12px;font-weight:600;color:var(--wave);margin-bottom:6px">'+_esc(v.display_name)+'</div>'
            + '<div style="font-size:13px;color:var(--text2);line-height:1.7">'+_esc(v.statement)+'</div>'
            + '</div>';
        }).join('')
      : '<div style="font-size:13px;color:var(--text3);padding:20px 0;text-align:center">No approved voices yet.</div>';

    return '<div class="page-content">'
      + '<div style="max-width:680px;margin:0 auto">'
      + '<button onclick="set({bioregionPortrait:null})" style="font-size:12px;color:var(--text3);background:none;border:none;cursor:pointer;padding:0;margin-bottom:20px">← All portraits</button>'
      + '<h2 style="font-size:22px;font-weight:800;font-family:var(--font-display);color:var(--text1);margin:0 0 4px">'+_esc(p.cluster_label)+'</h2>'
      + '<div style="font-size:12px;color:var(--text3);margin-bottom:20px">'+p.contributor_count+' voice'+(p.contributor_count!==1?'s':'')+' shaping this portrait</div>'
      + (p.summary
          ? '<div style="background:linear-gradient(135deg,var(--bg2) 0%,rgba(0,229,200,0.04) 100%);border:1px solid rgba(0,229,200,0.2);border-radius:var(--r);padding:20px;margin-bottom:24px;font-size:14px;color:var(--text2);line-height:1.8">'+_esc(p.summary)+'</div>'
          : '<div style="padding:16px;background:var(--bg2);border-radius:var(--r-sm);color:var(--text3);font-size:13px;margin-bottom:24px">This portrait hasn&#39;t been synthesised yet &#8212; an admin will generate it once enough voices are gathered.</div>')
      + '<div style="font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text3);margin-bottom:12px">Contributing voices</div>'
      + voicesHtml
      + '</div></div>';
  }

  // ── Map view ──────────────────────────────────────────────────────────────
  if (S.bioregionView === 'map') {
    return '<div class="page-content">'
      + '<div style="max-width:1100px;margin:0 auto">'
      + '<div style="margin-bottom:16px">'
      + '<h2 style="font-size:24px;font-weight:800;font-family:var(--font-display);color:var(--text1);margin:0 0 6px">🌍 Bioregion Portraits</h2>'
      + '<p style="font-size:13px;color:var(--text3);line-height:1.6;margin:0">Living collective portraits of the earth&#39;s places &#8212; shaped by learners who know them from the inside.</p>'
      + '</div>'
      + _renderBioViewToggle()
      + _renderBioMapView()
      + '</div></div>';
  }

  // ── Table view ────────────────────────────────────────────────────────────
  if (S.bioregionView === 'table') {
    return '<div class="page-content">'
      + '<div style="max-width:1100px;margin:0 auto">'
      + '<div style="margin-bottom:16px">'
      + '<h2 style="font-size:24px;font-weight:800;font-family:var(--font-display);color:var(--text1);margin:0 0 6px">🌍 Bioregion Portraits</h2>'
      + '<p style="font-size:13px;color:var(--text3);line-height:1.6;margin:0">Living collective portraits of the earth&#39;s places &#8212; shaped by learners who know them from the inside.</p>'
      + '</div>'
      + _renderBioViewToggle()
      + _renderBioTableView()
      + '</div></div>';
  }

  // ── Field Guide view — point-form seed profiles (Layer 1) ──────────────────
  if (S.bioregionView === 'fieldguide') {
    return '<div class="page-content">'
      + '<div style="max-width:1100px;margin:0 auto">'
      + '<div style="margin-bottom:16px">'
      + '<h2 style="font-size:24px;font-weight:800;font-family:var(--font-display);color:var(--text1);margin:0 0 6px">🌍 Bioregion Portraits</h2>'
      + '<p style="font-size:13px;color:var(--text3);line-height:1.6;margin:0">Precise, point-form natural identity for each of the earth&#39;s named bioregions &#8212; the same data that powers your &quot;Where I Stand&quot; card.</p>'
      + '</div>'
      + _renderBioViewToggle()
      + _renderBioFieldGuideView()
      + '</div></div>';
  }

  // ── Portraits view (default) ──────────────────────────────────────────────
  var myCard = '';
  if (S.bioregionContribLoaded) {
    var c = S.bioregionContrib;
    if (c) {
      var statusColor = c.status==='approved' ? 'var(--wave)' : c.status==='rejected' ? '#E88080' : 'var(--amber,#E8A87C)';
      var statusLabel = c.status==='approved' ? '✓ Approved' : c.status==='rejected' ? '✗ Rejected' : '⏳ Pending review';
      myCard = '<div style="background:var(--bg2);border:1px solid var(--border);border-radius:var(--r);padding:16px;margin-bottom:20px">'
        + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">'
        + '<div style="font-size:12px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:.08em">Your contribution</div>'
        + '<span style="font-size:11px;font-weight:600;color:'+statusColor+';background:rgba(0,0,0,0.2);padding:3px 9px;border-radius:20px">'+statusLabel+'</span>'
        + '</div>'
        + '<div style="font-size:13px;font-weight:600;color:var(--text1);margin-bottom:6px">'+_esc(c.bioregion_name)+'</div>'
        + '<div style="font-size:12px;color:var(--text2);line-height:1.6">'+_esc(c.statement)+'</div>'
        + (c.status==='pending' ? '<div style="margin-top:12px"><button onclick="withdrawBioregionContrib()" style="font-size:11px;padding:5px 14px;background:transparent;border:1px solid var(--border2);color:var(--text3);border-radius:20px;cursor:pointer">Withdraw</button></div>' : '')
        + '</div>';
    } else if (!S.bioregionForm) {
      if (S.bioregionDraftLoading) {
        myCard = '<div style="text-align:center;padding:28px;color:var(--text3);font-size:13px">'
          + '<div style="font-size:22px;margin-bottom:10px">✨</div>'
          + 'Generating an AI portrait for your area…</div>';
      } else if (S.bioregionDraft && typeof S.bioregionDraft === 'object') {
        var d = S.bioregionDraft;
        var acc = S.bioregionDraftAccepted || {};
        var SECT = [
          {key:'summary',          icon:'🌍', label:'Overview'},
          {key:'watershed',        icon:'💧', label:'Watershed & Water'},
          {key:'climate',          icon:'☁️', label:'Climate'},
          {key:'species',          icon:'🌿', label:'Species & Life'},
          {key:'vitality',         icon:'✨', label:'Vitality'},
          {key:'economy',          icon:'🪙', label:'Economy & Livelihoods'},
          {key:'material_culture', icon:'🏺', label:'Material Culture'},
        ];
        var sectHtml = SECT.map(function(s) {
          if (!d[s.key]) return '';
          var on = !!acc[s.key];
          return '<div style="margin-bottom:10px;padding:13px 15px;background:var(--bg2);border-radius:var(--r-sm);border-left:3px solid '+(on?'rgba(0,229,200,0.5)':'var(--border2)')+'">'
            + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:7px">'
            + '<div style="font-size:12px;font-weight:600;color:var(--text3)">'+s.icon+' '+s.label+'</div>'
            + '<button onclick="draftSectionToggle(\''+s.key+'\')" style="font-size:11px;padding:3px 10px;background:'+(on?'rgba(0,229,200,0.15)':'transparent')+';border:1px solid '+(on?'rgba(0,229,200,0.4)':'var(--border2)')+';color:'+(on?'var(--wave)':'var(--text3)')+';border-radius:12px;cursor:pointer">'+(on?'✓ Include':'Skip')+'</button>'
            + '</div>'
            + '<div style="font-size:12px;color:var(--text2);line-height:1.6">'+_esc(d[s.key])+'</div>'
            + '</div>';
        }).join('');
        var anyOn = SECT.some(function(s) { return acc[s.key]; });
        myCard = '<div style="background:linear-gradient(135deg,var(--bg2) 0%,rgba(0,229,200,0.06) 100%);border:1px solid rgba(0,229,200,0.25);border-radius:var(--r);padding:20px;margin-bottom:20px">'
          + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
          + '<span style="font-size:18px">🤖</span>'
          + '<div style="font-size:14px;font-weight:700;color:var(--text1)">AI Draft: '+_esc(d.place_name||'')+'</div>'
          + '</div>'
          + '<div style="font-size:11px;color:var(--text3);line-height:1.5;margin-bottom:14px">No one has described this bioregion yet. Select the sections that resonate, then build your statement.</div>'
          + sectHtml
          + '<button onclick="buildStatementFromDraft()" '+(anyOn?'':' disabled')+' style="width:100%;margin-top:6px;padding:10px 0;background:'+(anyOn?'rgba(0,229,200,0.12)':'var(--bg2)')+';border:1px solid '+(anyOn?'rgba(0,229,200,0.3)':'var(--border2)')+';color:'+(anyOn?'var(--wave)':'var(--text3)')+';border-radius:20px;cursor:'+(anyOn?'pointer':'default')+';font-size:13px;font-weight:600">Build my statement →</button>'
          + '</div>';
      } else {
        myCard = '<div style="background:linear-gradient(135deg,var(--bg2) 0%,rgba(0,229,200,0.04) 100%);border:1px dashed rgba(0,229,200,0.3);border-radius:var(--r);padding:20px;margin-bottom:20px;text-align:center">'
          + '<div style="font-size:22px;margin-bottom:10px">🌱</div>'
          + '<div style="font-size:14px;font-weight:600;color:var(--text1);margin-bottom:6px">You know your land</div>'
          + '<div style="font-size:12px;color:var(--text3);line-height:1.6;margin-bottom:14px">Describe your bioregion — its rhythms, waters, living systems, and what it feels like to be here. Your voice joins a collective portrait.</div>'
          + '<button onclick="openBioregionForm()" style="font-size:13px;padding:9px 22px;background:rgba(0,229,200,0.12);border:1px solid rgba(0,229,200,0.3);color:var(--wave);border-radius:20px;cursor:pointer;font-weight:600">Share my bioregion</button>'
          + '</div>';
      }
    }
  }

  var formHtml = '';
  if (S.bioregionForm) {
    formHtml = '<div style="background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:20px;margin-bottom:20px">'
      + '<div style="font-size:14px;font-weight:700;color:var(--text1);margin-bottom:16px">Describe your bioregion</div>'
      + '<div style="margin-bottom:14px">'
      + '<label style="font-size:11px;font-weight:600;color:var(--text3);display:block;margin-bottom:5px">Bioregion name</label>'
      + '<input id="bio-form-name" type="text" value="'+_esc(S.bioregionFormName)+'" maxlength="100" placeholder="e.g. Red River Delta, Mekong Delta, Hanoi Plain…"'
      + ' oninput="S.bioregionFormName=this.value"'
      + ' style="width:100%;padding:9px 12px;background:var(--bg2);border:1px solid var(--border2);border-radius:var(--r-sm);color:var(--text1);font-size:13px;box-sizing:border-box"/>'
      + '</div>'
      + '<div style="margin-bottom:14px">'
      + '<label style="font-size:11px;font-weight:600;color:var(--text3);display:block;margin-bottom:5px">Your statement <span style="font-weight:400;color:var(--text3)">(20–2000 characters)</span></label>'
      + '<textarea id="bio-form-text" rows="5" maxlength="2000" placeholder="What does this place feel like? What are its rhythms, waters, living systems? What makes it distinctive?"'
      + ' oninput="S.bioregionFormText=this.value;var c=document.getElementById(\'bio-form-char-count\');if(c)c.textContent=this.value.length+\' / 2000\'"'
      + ' style="width:100%;padding:9px 12px;background:var(--bg2);border:1px solid var(--border2);border-radius:var(--r-sm);color:var(--text1);font-size:13px;resize:vertical;box-sizing:border-box;line-height:1.6">'
      + _esc(S.bioregionFormText)+'</textarea>'
      + '<div id="bio-form-char-count" style="font-size:10px;color:var(--text3);text-align:right;margin-top:3px">'+S.bioregionFormText.length+' / 2000</div>'
      + '</div>'
      + (S.bioregionFormError ? '<div style="font-size:12px;color:var(--coral);margin-bottom:10px">'+_esc(S.bioregionFormError)+'</div>' : '')
      + '<div style="display:flex;gap:10px">'
      + '<button onclick="submitBioregionContrib()" '+(S.bioregionFormSaving?'disabled':'')+' style="padding:9px 22px;background:var(--wave);color:#000;border:none;border-radius:20px;cursor:pointer;font-size:13px;font-weight:600">'+(S.bioregionFormSaving?'Submitting…':'Submit for review')+'</button>'
      + '<button onclick="cancelBioregionForm()" style="padding:9px 18px;background:transparent;border:1px solid var(--border2);color:var(--text3);border-radius:20px;cursor:pointer;font-size:13px">Cancel</button>'
      + '</div>'
      + '<div style="font-size:11px;color:var(--text3);margin-top:10px;line-height:1.5">Contributions are reviewed before appearing publicly. Your display name will be shown alongside your voice.</div>'
      + '</div>';
  }

  // ── Portrait list ─────────────────────────────────────────────────────────
  var listHtml = '';
  if (S.bioregionLoading) {
    listHtml = '<div style="text-align:center;padding:40px;color:var(--text3);font-size:13px">Loading portraits…</div>';
  } else if (!S.bioregionPortraits || S.bioregionPortraits.length === 0) {
    listHtml = '<div style="text-align:center;padding:40px;color:var(--text3);font-size:13px">'
      + '<div style="font-size:28px;margin-bottom:12px">🌍</div>'
      + '<div style="font-size:14px;color:var(--text2);font-weight:600;margin-bottom:6px">No portraits yet</div>'
      + '<div style="font-size:12px;line-height:1.6">Be the first to describe your bioregion. Once contributions are approved, collective portraits will appear here.</div>'
      + '</div>';
  } else {
    listHtml = '<div class="bioregion-grid">'
      + S.bioregionPortraits.map(function(p) {
          var excerpt = p.summary ? p.summary.slice(0,120)+'…' : 'Collective portrait forming…';
          var distHtml = (p.distance_km != null)
            ? (p.distance_km <= 50
                ? ' · <span style="color:var(--wave)">near you</span>'
                : ' · ≈' + Math.round(p.distance_km) + ' km away')
            : '';
          var vBadge = (p.version_number && p.version_number > 1)
            ? ' <span class="bio-v-num-badge" title="'+(p.vitality_snapshot ? 'Vitality: '+_esc(p.vitality_snapshot) : 'Version '+p.version_number)+'">v'+p.version_number+'</span>'
            : '';
          return '<div id="portrait-'+p.id+'" class="bioregion-card" onclick="viewBioregionPortrait('+p.id+')">'
            + '<div style="display:flex;align-items:baseline;gap:6px;flex-wrap:wrap;margin-bottom:4px">'
            + '<span style="font-size:16px;font-weight:700;color:var(--text1);font-family:var(--font-display)">'+_esc(p.cluster_label)+'</span>'
            + vBadge
            + '</div>'
            + '<div style="font-size:11px;color:var(--text3);margin-bottom:10px">'+p.contributor_count+' voice'+(p.contributor_count!==1?'s':'')+distHtml+'</div>'
            + '<div style="font-size:12px;color:var(--text2);line-height:1.6">'+_esc(excerpt)+'</div>'
            + '</div>';
        }).join('')
      + '</div>';
  }

  return '<div class="page-content">'
    + '<div style="max-width:800px;margin:0 auto">'
    + '<div style="margin-bottom:20px">'
    + '<h2 style="font-size:24px;font-weight:800;font-family:var(--font-display);color:var(--text1);margin:0 0 6px">🌍 Bioregion Portraits</h2>'
    + '<p style="font-size:13px;color:var(--text3);line-height:1.6;margin:0">Living collective portraits of the earth&#39;s places &#8212; shaped by learners who know them from the inside.</p>'
    + '</div>'
    + _renderBioViewToggle()
    + myCard
    + formHtml
    + listHtml
    + '</div></div>';
}

// helper: safely escape html for inline use
function _esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}


// ══════════════════════════════════════════════════════════════════════════════
// BIOREGION MAP, TABLE & VERSION HISTORY  (P_MAP)
// All functions below are additions — no existing functions modified.
// ══════════════════════════════════════════════════════════════════════════════

// ── Module-level state ────────────────────────────────────────────────────────
let _bioMap          = null;   // MapLibre map instance
let _bioMarkers      = [];     // MapLibre Marker objects
let _bioMapPortraits = [];     // portraits array cached for map click handler

let _bioPanelPortraitId  = null;   // portrait.id currently open in panel
let _bioPanelCurrentData = null;   // full portrait object in panel
let _bioVersionCache     = {};     // { [portrait_id]: versions_array }

let _bioSortCol = null;
let _bioSortDir = 1;

// ── Helpers ───────────────────────────────────────────────────────────────────

function _bioFormatLabel(label) {
  if (!label) return 'Unnamed Bioregion';
  return label.replace(/-/g, ' ').replace(/\b\w/g, function(c){ return c.toUpperCase(); });
}

// Returns 'bio-vit-high' | 'bio-vit-mid' | 'bio-vit-low' | 'bio-vit-unknown'
function _bioVitClass(v) {
  if (!v) return 'bio-vit-unknown';
  var l = v.toLowerCase();
  if (/high|thriv|excel|robust|health/.test(l)) return 'bio-vit-high';
  if (/low|declin|threat|critical|poor/.test(l)) return 'bio-vit-low';
  return 'bio-vit-mid';
}

var _BIO_VIT_SCORE = {
  thriving:5, excellent:5, high:4, robust:4, healthy:4,
  moderate:3, stable:3, fair:3,
  low:2, declining:2, poor:2, stressed:2,
  critical:1, threatened:1
};
function _bioVitScore(v) {
  if (!v) return null;
  var l = v.toLowerCase();
  var keys = Object.keys(_BIO_VIT_SCORE);
  for (var i = 0; i < keys.length; i++) { if (l.indexOf(keys[i]) !== -1) return _BIO_VIT_SCORE[keys[i]]; }
  return null;
}

// Returns 'up' | 'down' | 'stable' | null
function _bioVitTrend(current, previous) {
  var cs = _bioVitScore(current), ps = _bioVitScore(previous);
  if (cs === null || ps === null) return null;
  if (cs > ps) return 'up';
  if (cs < ps) return 'down';
  return 'stable';
}

// Haversine distance in km
function _bioDist(lat1, lng1, lat2, lng2) {
  var R = 6371, r = Math.PI / 180;
  var dLa = (lat2 - lat1) * r, dLo = (lng2 - lng1) * r;
  var a = Math.sin(dLa/2)*Math.sin(dLa/2) + Math.cos(lat1*r)*Math.cos(lat2*r)*Math.sin(dLo/2)*Math.sin(dLo/2);
  return R * 2 * Math.asin(Math.sqrt(a));
}

function _bioNearest(lat, lng, portraits) {
  var best = null, min = Infinity;
  for (var i = 0; i < portraits.length; i++) {
    var p = portraits[i];
    if (p.center_lat == null || p.center_lng == null) continue;
    var d = _bioDist(lat, lng, +p.center_lat, +p.center_lng);
    if (d < min) { min = d; best = p; }
  }
  return best;
}

function _bioHasWebGL() {
  try {
    var c = document.createElement('canvas');
    return !!(c.getContext('webgl2') || c.getContext('webgl') || c.getContext('experimental-webgl'));
  } catch(e) { return false; }
}

function _bioFmtCoords(lat, lng) {
  if (lat == null || lng == null) return null;
  var la = +lat, lo = +lng;
  return Math.abs(la).toFixed(2) + '\u00b0\u202f' + (la >= 0 ? 'N' : 'S') + '\u2002'
       + Math.abs(lo).toFixed(2) + '\u00b0\u202f' + (lo >= 0 ? 'E' : 'W');
}

function _bioFmtDate(iso) {
  if (!iso) return '\u2014';
  try { return new Date(iso).toLocaleDateString(undefined, {year:'numeric',month:'short',day:'numeric'}); }
  catch(e) { return String(iso).slice(0, 10); }
}

function _bioTrunc(text, maxLen) {
  if (!text) return '';
  text = text.trim();
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen).replace(/\s\S+$/, '') + '\u2026';
}

// ── Map lifecycle ─────────────────────────────────────────────────────────────

function destroyBioMap() {
  if (_bioMap) {
    _bioMarkers.forEach(function(m){ m.remove(); });
    _bioMarkers = [];
    _bioMap.remove();
    _bioMap = null;
  }
}

function _buildBioMap(portraits) {
  var container = document.getElementById('bio-map-canvas');
  if (!container || _bioMap) return;
  _bioMapPortraits = portraits;

  _bioMap = new maplibregl.Map({
    container: 'bio-map-canvas',
    style:     'https://tiles.openfreemap.org/styles/liberty',
    center:    [20, 15],
    zoom:      1.6,
    minZoom:   1,
    maxZoom:   14,
  });

  // Globe projection (MapLibre GL JS v4+) — degrades to Mercator silently
  _bioMap.once('styledata', function() {
    try { _bioMap.setProjection('globe'); } catch(e) {}
  });

  _bioMap.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right');
  _bioMap.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');

  _bioMap.on('load', function() {
    portraits.forEach(function(p, i) {
      if (p.center_lat == null || p.center_lng == null) return;
      var el = document.createElement('div');
      el.className = 'bio-marker';
      el.style.setProperty('--pulse-delay', (i % 5) * 0.55 + 's');
      el.innerHTML = '<div class="bio-marker-ring"></div><div class="bio-marker-dot"></div>';
      el.title = _bioFormatLabel(p.cluster_label);
      el.addEventListener('click', (function(portrait){ return function(e) {
        e.stopPropagation();
        _bioFlyAndOpen(portrait);
      }; })(p));
      var marker = new maplibregl.Marker({ element: el, anchor: 'center' })
        .setLngLat([+p.center_lng, +p.center_lat])
        .addTo(_bioMap);
      _bioMarkers.push(marker);
    });

    _bioMap.on('click', function(e) {
      var nearest = _bioNearest(e.lngLat.lat, e.lngLat.lng, _bioMapPortraits);
      if (nearest) _bioFlyAndOpen(nearest);
    });
    _bioMap.getCanvas().style.cursor = 'crosshair';
  });
}

function initBioregionMap(portraits) {
  if (!portraits || !portraits.length) return;
  if (!_bioHasWebGL()) {
    var c = document.getElementById('bio-map-canvas');
    if (c) c.innerHTML = '<div class="bio-map-fallback"><p>WebGL is required for the map view and is not available in this browser.</p><button onclick="window.setBioView(\'table\')">Switch to Table \u2192</button></div>';
    return;
  }
  if (window.maplibregl) { _buildBioMap(portraits); return; }

  // Lazy-load MapLibre GL JS from CDN on first map activation
  if (!document.getElementById('_mgl_css')) {
    var lnk = document.createElement('link');
    lnk.id = '_mgl_css'; lnk.rel = 'stylesheet';
    lnk.href = 'https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.css';
    document.head.appendChild(lnk);
  }
  if (!document.getElementById('_mgl_js')) {
    var scr = document.createElement('script');
    scr.id = '_mgl_js';
    scr.src = 'https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js';
    scr.onload = function() { _buildBioMap(portraits); };
    scr.onerror = function() {
      var c = document.getElementById('bio-map-canvas');
      if (c) c.innerHTML = '<div class="bio-map-fallback"><p>Map library could not be loaded. Check your connection.</p></div>';
    };
    document.body.appendChild(scr);
  }
}

// ── Panel ─────────────────────────────────────────────────────────────────────

function _bioFlyAndOpen(p) {
  if (_bioMap && p.center_lat != null) {
    _bioMap.flyTo({ center: [+p.center_lng, +p.center_lat], zoom: 5, duration: 1100, essential: true });
  }
  _bioOpenPanel(p);
}

function _bioOpenPanel(p) {
  var panel = document.getElementById('bio-map-panel');
  if (!panel) return;

  _bioPanelPortraitId  = p.id;
  _bioPanelCurrentData = p;

  var name    = _bioFormatLabel(p.cluster_label);
  var coords  = _bioFmtCoords(p.center_lat, p.center_lng);
  var vitCls  = _bioVitClass(p.vitality_snapshot);
  var vNum    = p.version_number || 1;
  var summary = _bioTrunc((p.summary || '').trim(), 300);
  var cached  = _bioVersionCache[p.id];
  var vCount  = cached ? cached.length : '\u2026';

  panel.innerHTML = '<div class="bio-panel-head">'
    + '<div class="bio-panel-head-text">'
    + '<div class="bio-panel-name-row">'
    + '<span class="bio-panel-name">'+_esc(name)+'</span>'
    + '<span class="bio-panel-v-badge" title="Version '+vNum+'">v'+vNum+'</span>'
    + '</div>'
    + (coords ? '<div class="bio-panel-coords">\ud83d\udccd '+_esc(coords)+'</div>' : '')
    + (p.radius_km != null ? '<div class="bio-panel-radius">\u223c'+Math.round(+p.radius_km)+' km radius</div>' : '')
    + '</div>'
    + '<button class="bio-panel-close" onclick="document.getElementById(\'bio-map-panel\').classList.remove(\'bio-panel-open\')" aria-label="Close">\u2715</button>'
    + '</div>'
    + '<div class="bio-panel-body">'
    + '<div id="bio-panel-summary" class="bio-panel-summary-wrap">'
    + (summary ? '<p class="bio-panel-summary-text">'+_esc(summary)+'</p>' : '<p class="bio-panel-summary-empty">No portrait generated yet.</p>')
    + '</div>'
    + '<div class="bio-panel-meta">'
    + (p.vitality_snapshot ? '<span class="bio-vit-badge '+vitCls+'">'+_esc(p.vitality_snapshot)+'</span>' : '')
    + (p.contributor_count != null ? '<span class="bio-panel-contrib">'+p.contributor_count+' contributor'+(p.contributor_count!==1?'s':'')+'</span>' : '')
    + '</div>'
    + (p.change_notes ? '<div class="bio-panel-change-note">\ud83d\uddd2 '+_esc(p.change_notes)+'</div>' : '')
    + '<div class="bio-version-section">'
    + '<button class="bio-version-toggle" aria-expanded="false" onclick="window.toggleBioVersionTimeline('+p.id+')">'
    + '<span class="bio-vt-toggle-label">Version History</span>'
    + '<span class="bio-vt-count-tag">'+vCount+'</span>'
    + '<span class="bio-vt-chevron">\u25be</span>'
    + '</button>'
    + '<div class="bio-version-timeline" id="bio-version-timeline" aria-hidden="true">'
    + (cached ? _renderVersionTimeline(cached, p.id) : '')
    + '</div>'
    + '</div>'
    + '<button class="bio-panel-view-btn" onclick="window.setBioView(\'portraits\');requestAnimationFrame(function(){var el=document.getElementById(\'portrait-'+p.id+'\');if(el)el.scrollIntoView({behavior:\'smooth\',block:\'center\'});})">Read full portrait \u2192</button>'
    + '</div>';

  panel.classList.add('bio-panel-open');
}

// ── Version timeline ──────────────────────────────────────────────────────────

function _renderVersionTimeline(versions, portraitId) {
  if (!versions || !versions.length) {
    return '<div class="bio-vt-empty">No version history yet.</div>';
  }
  return '<div class="bio-vt-list">' + versions.map(function(v, i) {
    var isCurrent = i === 0;
    var prevV     = versions[i + 1];
    var trend     = prevV ? _bioVitTrend(v.vitality_snapshot, prevV.vitality_snapshot) : null;
    var trendHtml = trend
      ? '<span class="bio-vt-trend bio-vt-trend-'+trend+'">'+(trend==='up'?'\u2191':trend==='down'?'\u2193':'\u2192')+'</span>'
      : '';
    var clickAttr = isCurrent ? '' : 'role="button" tabindex="0"'
      + ' onclick="window.switchBioVersion('+portraitId+','+v.version_number+')"'
      + ' onkeydown="if(event.key===\'Enter\'||event.key===\' \')window.switchBioVersion('+portraitId+','+v.version_number+')"';
    return '<div class="bio-vt-node'+(isCurrent?' bio-vt-current':'')+'" id="bio-vt-node-'+v.version_number+'" '+clickAttr+'>'
      + '<div class="bio-vt-dot-col">'
      + '<div class="bio-vt-dot'+(isCurrent?' bio-vt-dot-live':'')+'"></div>'
      + (i < versions.length - 1 ? '<div class="bio-vt-line"></div>' : '')
      + '</div>'
      + '<div class="bio-vt-info">'
      + '<div class="bio-vt-row-top">'
      + '<span class="bio-vt-num">'+(isCurrent?'v'+v.version_number+' \u00b7 current':'v'+v.version_number)+'</span>'
      + '<span class="bio-vt-date">'+_bioFmtDate(v.generated_at)+'</span>'
      + trendHtml
      + '</div>'
      + (v.vitality_snapshot ? '<div class="bio-vt-vitality">'+_esc(v.vitality_snapshot)+'</div>' : '')
      + '<div class="bio-vt-contrib">'+v.contributor_count+' contributor'+(v.contributor_count!==1?'s':'')+'</div>'
      + (v.change_notes ? '<div class="bio-vt-notes">\u201c'+_esc(v.change_notes)+'\u201d</div>' : '')
      + '</div>'
      + '</div>';
  }).join('') + '</div>';
}

async function _loadAndRenderVersionTimeline(portraitId) {
  var tl = document.getElementById('bio-version-timeline');
  if (!tl) return;
  tl.innerHTML = '<div class="bio-vt-loading"><span class="bio-vt-spin"></span>Loading history\u2026</div>';
  try {
    var versions = await API.get('/bioregions/'+portraitId+'/versions');
    _bioVersionCache[portraitId] = versions;
    tl.innerHTML = _renderVersionTimeline(versions, portraitId);
    var countEl = document.querySelector('.bio-vt-count-tag');
    if (countEl) countEl.textContent = versions.length;
  } catch(e) {
    console.error('[P_MAP] version history', e);
    tl.innerHTML = '<div class="bio-vt-error">Could not load version history.</div>';
  }
}

// ── Render functions (return HTML strings) ────────────────────────────────────

function _renderBioViewToggle() {
  var v = S.bioregionView || 'portraits';
  return '<div class="bio-toggle" role="tablist" aria-label="Bioregion view">'
    + '<button role="tab" aria-selected="'+(v==='portraits')+'"  class="bio-toggle-btn'+(v==='portraits' ?' bio-toggle-active':'')+'" onclick="window.setBioView(\'portraits\')">🖼 Portraits</button>'
    + '<button role="tab" aria-selected="'+(v==='map')+'"        class="bio-toggle-btn'+(v==='map'       ?' bio-toggle-active':'')+'" onclick="window.setBioView(\'map\')">🌍 Map</button>'
    + '<button role="tab" aria-selected="'+(v==='table')+'"      class="bio-toggle-btn'+(v==='table'     ?' bio-toggle-active':'')+'" onclick="window.setBioView(\'table\')">📋 Table</button>'
    + '<button role="tab" aria-selected="'+(v==='fieldguide')+'" class="bio-toggle-btn'+(v==='fieldguide'?' bio-toggle-active':'')+'" onclick="window.setBioView(\'fieldguide\')">🧭 Field Guide</button>'
    + '</div>';
}

function _renderBioMapView() {
  if (S.bioregionLoading) {
    return '<div class="bio-map-wrap"><div class="bio-map-loader"><div class="bio-map-spinner"></div><span>Loading bioregions\u2026</span></div></div>';
  }
  return '<div class="bio-map-wrap" id="bio-map-wrap">'
    + '<div id="bio-map-canvas" class="bio-map-canvas"></div>'
    + '<div id="bio-map-panel" class="bio-map-panel">'
    + '<div class="bio-panel-placeholder">'
    + '<div class="bio-panel-ph-icon">🌍</div>'
    + '<p>Click any marker or anywhere on the map<br>to explore a local bioregion</p>'
    + '</div>'
    + '</div>'
    + '<div class="bio-map-hint">Click anywhere on the map to find your bioregion</div>'
    + '</div>';
}

function _renderBioTableView() {
  if (S.bioregionLoading) {
    return '<div class="bio-tbl-empty">Loading bioregions\u2026</div>';
  }
  var portraits = S.bioregionPortraits || [];
  if (!portraits.length) {
    return '<div class="bio-tbl-empty">No published bioregion portraits yet. Be the first to contribute!</div>';
  }
  var rows = portraits.map(function(p) {
    var label   = _bioFormatLabel(p.cluster_label);
    var coords  = _bioFmtCoords(p.center_lat, p.center_lng) || '\u2014';
    var vNum    = p.version_number || 1;
    var vitCls  = _bioVitClass(p.vitality_snapshot);
    var summary = _bioTrunc(p.summary || '', 110);
    return '<tr class="bio-tr" data-label="'+_esc(label.toLowerCase())+'">'
      + '<td class="bio-td bio-td-name">'
      + '<div class="bio-td-name-inner">'
      + '<span class="bio-tbl-label">'+_esc(label)+'</span>'
      + (p.vitality_snapshot ? '<span class="bio-vit-badge '+vitCls+' bio-vit-sm">'+_esc(p.vitality_snapshot)+'</span>' : '')
      + '</div>'
      + '</td>'
      + '<td class="bio-td bio-td-summary" title="'+_esc((p.summary||'').trim())+'">'+(_esc(summary)||'<span class="bio-td-nil">\u2014</span>')+'</td>'
      + '<td class="bio-td bio-td-center"><span class="bio-v-num-badge" title="'+(p.vitality_snapshot?'Vitality: '+_esc(p.vitality_snapshot):'Version '+vNum)+'">v'+vNum+'</span></td>'
      + '<td class="bio-td bio-td-center">'+( p.contributor_count != null ? p.contributor_count : '\u2014')+'</td>'
      + '<td class="bio-td bio-td-coords">'+_esc(coords)+'</td>'
      + '<td class="bio-td bio-td-date">'+_bioFmtDate(p.last_generated_at)+'</td>'
      + '<td class="bio-td bio-td-action"><button class="bio-tbl-view-btn" onclick="window.setBioView(\'portraits\');requestAnimationFrame(function(){var el=document.getElementById(\'portrait-'+p.id+'\');if(el)el.scrollIntoView({behavior:\'smooth\',block:\'center\'});})">View \u2192</button></td>'
      + '</tr>';
  }).join('');

  return '<div class="bio-tbl-wrap">'
    + '<div class="bio-tbl-toolbar">'
    + '<div class="bio-tbl-search-wrap">'
    + '<span class="bio-tbl-search-icon" aria-hidden="true">\u2315</span>'
    + '<input type="search" id="bio-tbl-search" class="bio-tbl-search" placeholder="Filter bioregions\u2026" oninput="window.filterBioTable(this.value)" aria-label="Filter bioregions">'
    + '</div>'
    + '<span class="bio-tbl-count" id="bio-tbl-count">'+portraits.length+' bioregion'+(portraits.length!==1?'s':'')+'</span>'
    + '</div>'
    + '<div class="bio-tbl-scroll" role="region" aria-label="Bioregion directory" tabindex="0">'
    + '<table class="bio-tbl" id="bio-tbl">'
    + '<thead><tr>'
    + '<th class="bio-th bio-th-sort" onclick="window.sortBioTable(\'cluster_label\')" scope="col">Bioregion <span class="bio-sort-ico" id="bio-sort-cluster_label">\u21c5</span></th>'
    + '<th class="bio-th" scope="col">Summary</th>'
    + '<th class="bio-th bio-th-sort bio-th-center" onclick="window.sortBioTable(\'version_number\')" scope="col">Ver <span class="bio-sort-ico" id="bio-sort-version_number">\u21c5</span></th>'
    + '<th class="bio-th bio-th-sort bio-th-center" onclick="window.sortBioTable(\'contributor_count\')" scope="col">Contributors <span class="bio-sort-ico" id="bio-sort-contributor_count">\u21c5</span></th>'
    + '<th class="bio-th" scope="col">Coordinates</th>'
    + '<th class="bio-th bio-th-sort" onclick="window.sortBioTable(\'last_generated_at\')" scope="col">Updated <span class="bio-sort-ico" id="bio-sort-last_generated_at">\u21c5</span></th>'
    + '<th class="bio-th" scope="col"><span style="position:absolute;width:1px;height:1px;overflow:hidden">Actions</span></th>'
    + '</tr></thead>'
    + '<tbody id="bio-tbody">'+rows+'</tbody>'
    + '</table>'
    + '</div>'
    + '</div>';
}

// ── Field Guide view (Layer 1 — author-curated seed profiles) ─────────────────
// Reuses _loadedProfiles (populated by loadBioregionProfiles(), the same
// fetch + 24h localStorage cache that powers the "Where I Stand" dashboard
// card) and the existing _bioRow() helper, so styling stays in perfect sync
// with that card with zero duplicated CSS.

function _bioVitalityColor(v) {
  if (!v) return 'var(--text2)';
  return v.indexOf('Critical') === 0 ? '#E88080'
       : v.indexOf('Stressed') === 0 ? '#E8A87C'
       : v.indexOf('At risk')  === 0 ? '#E8A87C'
       : 'var(--wave)';
}

function _renderBioFieldGuideView() {
  if (!_loadedProfiles || _loadedProfiles.length === 0) {
    return '<div class="bio-tbl-empty">'
      + '<div class="bio-map-spinner" style="margin:0 auto 14px"></div>'
      + 'Loading field guide\u2026</div>';
  }

  var cards = _loadedProfiles.map(function(p, i) {
    var boundsLine = (p.min_lat != null && p.max_lat != null && p.min_lng != null && p.max_lng != null)
      ? '<div class="bio-fg-bounds">Covers roughly '+Math.abs(p.min_lat).toFixed(1)+'\u00b0\u2013'+Math.abs(p.max_lat).toFixed(1)+'\u00b0 '+(p.min_lat>=0?'N':'S')
        +', '+Math.abs(p.min_lng).toFixed(1)+'\u00b0\u2013'+Math.abs(p.max_lng).toFixed(1)+'\u00b0 '+(p.min_lng>=0?'E':'W')+'</div>'
      : '';

    return '<div class="bio-fg-card" data-fg-name="'+_esc((p.name||'').toLowerCase())+'">'
      + '<div class="bio-fg-name">'+_esc(p.name||'Unnamed')+'</div>'
      + ((p.colonial || p.archaic) ? (
          '<div class="bio-fg-construct-grid">'
          + (p.colonial ? '<div class="bio-fg-construct-box"><div class="bio-fg-construct-label">Current construct</div><div class="bio-fg-construct-val">'+_esc(p.colonial)+'</div></div>' : '')
          + (p.archaic  ? '<div class="bio-fg-construct-box bio-fg-construct-deep"><div class="bio-fg-construct-label bio-fg-construct-label-deep">Deeper roots</div><div class="bio-fg-construct-val">'+_esc(p.archaic)+'</div></div>' : '')
          + '</div>'
        ) : '')
      + '<div class="bio-fg-rows">'
      + (p.climate     ? _bioRow('\ud83c\udf26','Climate', _esc(p.climate)) : '')
      + (p.watershed   ? _bioRow('\ud83d\udca7','Watershed', _esc(p.watershed)) : '')
      + (p.tectonic    ? _bioRow('\ud83c\udf0b','Tectonic', _esc(p.tectonic)) : '')
      + (p.species     ? _bioRow('\ud83e\udd85','Keystone species', _esc(p.species)) : '')
      + (p.soil        ? _bioRow('\ud83c\udf31','Soil', _esc(p.soil)) : '')
      + (p.resources   ? _bioRow('\u26cf','Natural resources', _esc(p.resources)) : '')
      + (p.vitality    ? _bioRow('\ud83d\udc9a','Vitality', _esc(p.vitality), _bioVitalityColor(p.vitality)) : '')
      + (p.connections ? _bioRow('\ud83d\udd17','Connections', _esc(p.connections)) : '')
      + '</div>'
      + boundsLine
      + '</div>';
  }).join('');

  return '<div class="bio-fg-wrap">'
    + '<div class="bio-tbl-toolbar">'
    + '<div class="bio-tbl-search-wrap">'
    + '<span class="bio-tbl-search-icon" aria-hidden="true">\u2315</span>'
    + '<input type="search" id="bio-fg-search" class="bio-tbl-search" placeholder="Filter bioregions\u2026" oninput="window.filterBioFieldGuide(this.value)" aria-label="Filter field guide">'
    + '</div>'
    + '<span class="bio-tbl-count" id="bio-fg-count">'+_loadedProfiles.length+' bioregion'+(_loadedProfiles.length!==1?'s':'')+'</span>'
    + '</div>'
    + '<div class="bio-fg-grid" id="bio-fg-grid">'+cards+'</div>'
    + '</div>';
}

window.filterBioFieldGuide = function(q) {
  var lower = (q || '').toLowerCase();
  var shown = 0;
  document.querySelectorAll('#bio-fg-grid .bio-fg-card').forEach(function(card) {
    var match = (card.dataset.fgName || '').indexOf(lower) !== -1;
    card.style.display = match ? '' : 'none';
    if (match) shown++;
  });
  var cntEl = document.getElementById('bio-fg-count');
  if (cntEl) cntEl.textContent = shown + ' bioregion' + (shown !== 1 ? 's' : '');
};

// ── Window-exposed interactions ───────────────────────────────────────────────

window.setBioView = function(view) {
  set({bioregionView: view});
};

window.sortBioTable = function(col) {
  var tbody = document.getElementById('bio-tbody');
  if (!tbody) return;
  _bioSortDir = (_bioSortCol === col) ? -_bioSortDir : 1;
  _bioSortCol = col;

  var colIndex = {cluster_label:0, version_number:2, contributor_count:3, last_generated_at:5};
  var idx   = colIndex[col] !== undefined ? colIndex[col] : 0;
  var isNum = col === 'contributor_count' || col === 'version_number';

  var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr.bio-tr'));
  rows.sort(function(a, b) {
    var av = (a.querySelectorAll('td')[idx] || {}).textContent.trim() || '';
    var bv = (b.querySelectorAll('td')[idx] || {}).textContent.trim() || '';
    return _bioSortDir * (isNum ? (parseFloat(av)||0) - (parseFloat(bv)||0) : av.localeCompare(bv, undefined, {sensitivity:'base'}));
  });
  rows.forEach(function(r){ tbody.appendChild(r); });

  document.querySelectorAll('.bio-sort-ico').forEach(function(el){ el.textContent = '\u21c5'; });
  var ico = document.getElementById('bio-sort-'+col);
  if (ico) ico.textContent = _bioSortDir === 1 ? '\u2191' : '\u2193';
};

window.filterBioTable = function(q) {
  var lower = (q || '').toLowerCase();
  var shown = 0;
  document.querySelectorAll('#bio-tbody tr.bio-tr').forEach(function(row) {
    var match = (row.dataset.label || '').indexOf(lower) !== -1;
    row.style.display = match ? '' : 'none';
    if (match) shown++;
  });
  var cntEl = document.getElementById('bio-tbl-count');
  if (cntEl) cntEl.textContent = shown + ' bioregion' + (shown !== 1 ? 's' : '');
};

window.toggleBioVersionTimeline = function(portraitId) {
  var tl  = document.getElementById('bio-version-timeline');
  var btn = document.querySelector('.bio-version-toggle');
  if (!tl || !btn) return;
  var isOpen = tl.classList.toggle('bio-vt-open');
  tl.setAttribute('aria-hidden', !isOpen);
  btn.setAttribute('aria-expanded', isOpen);
  btn.querySelector('.bio-vt-chevron').textContent = isOpen ? '\u25b4' : '\u25be';
  if (isOpen && portraitId && !_bioVersionCache[portraitId]) {
    _loadAndRenderVersionTimeline(portraitId);
  }
};

window.switchBioVersion = async function(portraitId, versionNumber) {
  var summaryEl = document.getElementById('bio-panel-summary');
  if (!summaryEl) return;

  if (versionNumber === null) {
    var p = _bioPanelCurrentData;
    if (!p) return;
    var summary = _bioTrunc((p.summary || '').trim(), 300);
    summaryEl.innerHTML = summary
      ? '<p class="bio-panel-summary-text">'+_esc(summary)+'</p>'
      : '<p class="bio-panel-summary-empty">No portrait generated yet.</p>';
    document.querySelectorAll('.bio-vt-node').forEach(function(el){ el.classList.remove('bio-vt-selected'); });
    var liveNode = document.getElementById('bio-vt-node-'+(p.version_number||1));
    if (liveNode) liveNode.classList.add('bio-vt-selected');
    return;
  }

  summaryEl.innerHTML = '<div class="bio-panel-v-loading">Loading v'+versionNumber+'\u2026</div>';
  try {
    var vdata = await API.get('/bioregions/'+portraitId+'/versions/'+versionNumber);
    var summary = (vdata.summary || '').trim();
    summaryEl.innerHTML = '<div class="bio-viewing-banner">'
      + '<span>Viewing v'+versionNumber+' \u00b7 '+_bioFmtDate(vdata.generated_at)+'</span>'
      + '<button class="bio-viewing-back" onclick="window.switchBioVersion('+portraitId+',null)">\u2190 current</button>'
      + '</div>'
      + (vdata.change_notes ? '<div class="bio-viewing-note">\ud83d\uddd2 '+_esc(vdata.change_notes)+'</div>' : '')
      + '<p class="bio-panel-summary-text">'+_esc(_bioTrunc(summary, 400))+'</p>';

    document.querySelectorAll('.bio-vt-node').forEach(function(el){ el.classList.remove('bio-vt-selected'); });
    var node = document.getElementById('bio-vt-node-'+versionNumber);
    if (node) node.classList.add('bio-vt-selected');
  } catch(e) {
    console.error('[P_MAP] switchBioVersion', e);
    summaryEl.innerHTML = '<p class="bio-panel-error">Could not load v'+versionNumber+'.</p>';
  }
};

function draw() {
  const views = {
    login:     AuthPage,
    onboard:   OnboardPage,
    register:  AuthPage,
    dashboard: Dashboard,
    session:   Session,
    skills:    Mouseion,
    reflect:   Stoa,
    portfolio: Portfolio,
    bioregion: BioregionPage,
  };

  const root = document.getElementById('root');
  const isAuth = S.view === 'login' || S.view === 'register';

  root.innerHTML = (isAuth ? '' : Nav()) + (views[S.view] || Dashboard)();

  // Restore challenge text
  const t = document.getElementById('ctxt');
  if (t && S.challengeText) t.value = S.challengeText;

  // Auto-focus first input on auth pages
  if (isAuth) {
    setTimeout(() => {
      const first = document.querySelector('.form-input');
      if (first) first.focus();
    }, 50);
  }
}

// ── Boot ──────────────────────────────────────────
async function boot() {
  // Clear #register / #login hash from URL bar (set by landing page)
  if (location.hash === '#register' || location.hash === '#login') {
    history.replaceState(null, '', '/app.html');
  }
  // ── Responsive dashboard grid ──────────────────────────────
  // Injects CSS once: on narrow viewports columns stack in order 1→2→3
  if (!API.isLoggedIn()) {
    draw();
    return;
  }
  // Try to refresh the access token before doing anything. The refresh
  // token itself lives in the httpOnly fl_refresh cookie (path-scoped to
  // /api/auth) — the browser attaches it automatically, nothing to read
  // from localStorage here (P-SEC1, 2026-07-16).
  try {
    const res = await fetch('/api/auth/refresh', {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
    });
    if (res.ok) {
      const data = await res.json();
      const learner = API.getLearner();
      if (learner) {
        learner.display_name = data.display_name || learner.display_name;
        localStorage.setItem('fl_learner', JSON.stringify(learner));
      }
      console.log('Token refreshed successfully');
    } else if (res.status === 401 || res.status === 403) {
      // Refresh token genuinely expired/missing — log out cleanly
      console.log('Refresh token expired — logging out');
      API.logout();
      set({view:'login', learner:null});
      return;
    } else {
      // Server error (5xx) or other transient failure — keep going; the
      // server may just be restarting or temporarily overloaded.
      console.log('Token refresh server error (' + res.status + ') — continuing');
    }
  } catch(e) {
    console.log('Token refresh failed:', e.message);
    // Network error — continue and try anyway
  }
  draw();
  // Load bioregion seed profiles (populates the ecological detail in the Where I Stand card)
  loadBioregionProfiles();
  // Load learner profile (includes language preference)
  API.get('/learners/me').then(function(me) {
    if (me) {
      // Load learner_profile into state so sandbox companion has memory from day one
      if (me.learner_profile) S.learnerProfile = me.learner_profile;
      // Restore cached Guiding Star (regenerated after each profile update)
      try {
        var _gs = localStorage.getItem('fl_guiding_star');
        if (_gs) S.guidingStar = _gs;
      } catch(e) {}
      // If bioregion already located but not yet in profile, write it now (e.g. returning user, new account)
      if (_bioregionState.status === 'done' && _bioregionState.profile) {
        var _existingProfile = me.learner_profile || '';
        if (_existingProfile.indexOf('BIOREGION:') === -1) {
          _saveBioregionToProfile();
        }
      }
      if (me.language && me.language !== S.language) {
        set({language: me.language, learner: Object.assign({}, S.learner||{}, me)});
      } else {
        set({learner: Object.assign({}, S.learner||{}, me)});
      }
    }
  }).catch(function(){});
  loadDashboard();
}

boot();
