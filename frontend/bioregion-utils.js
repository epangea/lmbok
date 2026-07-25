// ══════════════════════════════════════════════════
// bioregion-utils.js — shared bioregion auto-detection
// Added 2026-07-24 for P11 (org bioregion self-service + admin parity).
//
// NOTE: app.js has its own long-standing copy of this same lat/lng-matching
// logic (getBioregionProfile / loadBioregionProfiles / initBioregion), built
// for the learner onboarding flow and wired into localStorage state that's
// specific to that flow. It was deliberately NOT refactored to use this file
// — app.js is a large, history-laden file and this was a small enough need
// that duplicating ~20 lines of pure logic was lower-risk than touching it.
// This is acknowledged tech debt: two copies of the same bounding-box match
// exist (app.js's internal one, and this shared one for org.html/admin.html).
// If a third consumer ever needs it, that's the trigger to properly unify
// both into this file and refactor app.js to call it.
// ══════════════════════════════════════════════════

var BioregionUtils = (function () {
  var _profiles = null; // cached in-memory after first load

  function loadProfiles() {
    if (_profiles) return Promise.resolve(_profiles);
    try {
      var cached = localStorage.getItem('flb_profiles_cache');
      if (cached) {
        var c = JSON.parse(cached);
        if (c && c.ts && (Date.now() - c.ts) < 86400000 && Array.isArray(c.profiles) && c.profiles.length) {
          _profiles = c.profiles;
          return Promise.resolve(_profiles);
        }
      }
    } catch (e) {}
    return fetch('/api/bioregions/seed-profiles')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        _profiles = (data && Array.isArray(data.profiles)) ? data.profiles : [];
        try {
          localStorage.setItem('flb_profiles_cache', JSON.stringify({ ts: Date.now(), profiles: _profiles }));
        } catch (e) {}
        return _profiles;
      })
      .catch(function () { _profiles = []; return _profiles; });
  }

  function matchProfile(lat, lng, profiles) {
    for (var i = 0; i < profiles.length; i++) {
      var p = profiles[i];
      if (lat >= p.min_lat && lat <= p.max_lat && lng >= p.min_lng && lng <= p.max_lng) return p;
    }
    return null;
  }

  // detect(onResult) — onResult({ok, name, placeName, lat, lng, reason})
  function detect(onResult) {
    if (!navigator.geolocation) { onResult({ ok: false, reason: 'no_geolocation' }); return; }
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        var lat = Math.round(pos.coords.latitude * 10) / 10;
        var lng = Math.round(pos.coords.longitude * 10) / 10;
        loadProfiles().then(function (profiles) {
          var profile = matchProfile(lat, lng, profiles);
          fetch('https://nominatim.openstreetmap.org/reverse?lat=' + lat + '&lon=' + lng + '&zoom=10&format=json')
            .then(function (r) { return r.json(); })
            .then(function (d) {
              var a = d.address || {};
              var placeName = [a.city || a.town || a.village, a.country].filter(Boolean).join(', ');
              onResult({
                ok: true,
                name: (profile && profile.name) ? profile.name : (placeName || null),
                placeName: placeName, lat: lat, lng: lng, profile: profile,
              });
            })
            .catch(function () {
              onResult({ ok: true, name: profile ? profile.name : null, placeName: null, lat: lat, lng: lng, profile: profile });
            });
        });
      },
      function () { onResult({ ok: false, reason: 'denied' }); },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 3600000 }
    );
  }

  // listNames(cb) — cb(['Red River Delta', ...]) for a manual-override dropdown
  function listNames(cb) {
    loadProfiles().then(function (profiles) {
      cb(profiles.map(function (p) { return p.name; }).filter(Boolean).sort());
    });
  }

  return { detect: detect, listNames: listNames, loadProfiles: loadProfiles };
})();
