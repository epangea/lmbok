// sw.js — LMBoK / Surfing the Frequencies service worker
//
// Scope: whole origin (served from site root, default scope covers
// index.html, app.html, org.html, admin.html, polis.html, contribute.html).
//
// Strategy, chosen for LMBoK's low-bandwidth/2G target (matches the same
// philosophy as scripts/bump_asset_versions.sh's aggressive-cache-plus-
// instant-bust approach):
//   - App shell (HTML/CSS/JS/icons/manifest): precached on install so a
//     repeat visit or install-to-homescreen launch is instant even on a
//     bad connection.
//   - Navigations (HTML page loads): network-first, falling back to cache
//     when offline, falling back further to the cached app shell as a
//     last resort so the app still opens rather than showing a browser
//     offline page.
//   - /api/* requests: NEVER intercepted. These carry cookies/CSRF and
//     return live, per-learner data — caching them would risk serving
//     stale or cross-session content. Always network passthrough.
//   - Everything else (fonts, misc static assets): cache-first with a
//     network fallback that also updates the cache (stale-while-revalidate
//     style), since these rarely change.
//
// Versioning: CACHE_NAME below is derived from a content hash by
// scripts/bump_asset_versions.sh, the same script that already maintains
// the ?v= query strings on app.css/app.js. It is intentionally NOT
// hand-edited — running that script is what bumps it. A changed
// CACHE_NAME is also what makes the browser see this file itself as
// "different" on its next periodic check, which is what actually
// triggers the update flow (see frontend/app.js's registerServiceWorker
// section for the "update available" prompt this pairs with).
const CACHE_NAME = 'lmbok-shell-1521142941';

// Precached at install. Kept intentionally small (the learner-facing
// shell only) rather than every page on the site -- org.html/admin.html/
// polis.html/contribute.html are fetched+cached on first real visit
// instead, via the runtime handlers below, so an install doesn't pull
// down pages most learners will never open.
const PRECACHE_URLS = [
  '/',
  '/app.html',
  '/app.css?v=609255717',
  '/app.js?v=90457374',
  '/manifest.json',
  '/favicon.ico',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
];

// Lets the "update available" banner (app.html) tell a waiting worker to
// activate immediately, instead of waiting for every tab to close.
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(
        names
          .filter((name) => name.startsWith('lmbok-shell-') && name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Only handle same-origin GETs -- everything else (API calls, other
  // origins, non-GET methods) passes straight to the network untouched.
  if (req.method !== 'GET' || url.origin !== self.location.origin) {
    return;
  }
  if (url.pathname.startsWith('/api/')) {
    return; // never cache live/auth'd API responses
  }

  // Navigations (actual page loads / installed-app launches): network
  // first so a learner with a connection always gets the current page,
  // cache as fallback when offline, app shell as last resort.
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          return res;
        })
        .catch(() =>
          caches.match(req).then((cached) => cached || caches.match('/app.html'))
        )
    );
    return;
  }

  // Static assets: cache-first, refresh cache in the background.
  event.respondWith(
    caches.match(req).then((cached) => {
      const network = fetch(req)
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          }
          return res;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});
