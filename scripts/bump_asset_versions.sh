#!/bin/bash
# bump_asset_versions.sh — auto cache-bust app.css / app.js (2026-08-11)
#
# Problem this solves: app.css is referenced with a manually-typed
# "?v=YYYYMMDDx" query string from 6 separate HTML files (app.html,
# admin.html, org.html, polis.html, contribute.html, privacy.html) --
# app.js similarly from app.html. Every time either file changes, every
# reference has to be bumped by hand or the browser serves a stale cached
# copy after deploy (this bit us twice on 2026-08-11 alone). The cache-
# busting itself is intentional and should stay -- LMBoK targets 2G
# connections and $30 devices, so assets are meant to be cached
# aggressively; the query string is what lets an update bypass that cache
# instantly instead of waiting out a long max-age.
#
# Fix: derive the version tag from the file's own content (a checksum),
# not a hand-picked date string. Content unchanged -> tag unchanged -> no
# edits, no diff noise. Content changed -> tag changes automatically and
# EVERY referencing file gets updated in one pass, so it's structurally
# impossible to update the CSS/JS but forget one of the HTML files.
#
# Uses `cksum` (POSIX, ships on every Linux and macOS box, zero deps --
# checked against shasum/md5sum/sha256sum too, all four are present here,
# but cksum needs no OS-specific fallback logic) rather than a
# cryptographic hash; this only needs to change when the file changes; it
# doesn't need to resist tampering.
#
# Usage: run from repo root (or anywhere -- it cd's to its own location):
#   bash scripts/bump_asset_versions.sh
# Run this locally against your working copy BEFORE sftp'ing to the
# server, same as any other frontend edit -- it doesn't touch the server
# and doesn't require deploying scripts/ itself.

set -euo pipefail
cd "$(dirname "$0")/../frontend"

changed=0

bump_asset() {
  local asset="$1"          # e.g. app.css
  local basename="${asset%.*}"
  local ext="${asset##*.}"

  if [ ! -f "$asset" ]; then
    echo "SKIP  $asset not found in frontend/"
    return
  fi

  local hash
  hash=$(cksum "$asset" | awk '{print $1}')
  local new_ref="${asset}?v=${hash}"

  # Every .html file (plus sw.js, which precaches these same URLs -- see
  # its PRECACHE_URLS array) that currently references this asset with a
  # ?v= tag -- discovered dynamically via grep, not a hardcoded file list,
  # so a new page added later that links app.css/app.js is picked up
  # automatically.
  local refs
  refs=$(grep -l "${basename}\.${ext}?v=" *.html sw.js 2>/dev/null || true)

  if [ -z "$refs" ]; then
    echo "WARN  no .html files reference ${asset}?v=... -- nothing to update"
    return
  fi

  for f in $refs; do
    local current
    current=$(grep -o "${basename//./\\.}\.${ext}?v=[0-9a-zA-Z]*" "$f" | head -1)
    if [ "$current" = "$new_ref" ]; then
      continue   # already correct, no edit needed
    fi
    sed -i.bak "s|${basename//./\\.}\.${ext}?v=[0-9a-zA-Z]*|${new_ref}|g" "$f"
    rm -f "${f}.bak"
    echo "OK    $f -> ${new_ref}"
    changed=$((changed+1))
  done
}

bump_sw_cache_name() {
  # sw.js's CACHE_NAME (see its own header comment) is a second, independent
  # version signal on top of the ?v= tags bump_asset already keeps in sync
  # above -- it's what actually changes sw.js's own byte content, which is
  # what makes the browser's periodic service-worker update check notice
  # anything changed at all. Derived from a combined hash of the three
  # files that make up the precached app shell, so it changes exactly when
  # a repeat visitor would need a fresh cache -- no more, no less.
  local sw="sw.js"
  if [ ! -f "$sw" ]; then
    echo "SKIP  $sw not found in frontend/"
    return
  fi
  if [ ! -f app.css ] || [ ! -f app.js ] || [ ! -f app.html ]; then
    echo "WARN  app shell file(s) missing -- skipping sw.js CACHE_NAME bump"
    return
  fi

  local combined
  combined=$(cat app.css app.js app.html | cksum | awk '{print $1}')
  local new_name="lmbok-shell-${combined}"

  local current
  current=$(grep -o "CACHE_NAME = '[^']*'" "$sw" | head -1)
  if [ "$current" = "CACHE_NAME = '${new_name}'" ]; then
    return
  fi
  sed -i.bak "s/CACHE_NAME = '[^']*'/CACHE_NAME = '${new_name}'/" "$sw"
  rm -f "${sw}.bak"
  echo "OK    $sw -> CACHE_NAME '${new_name}'"
  changed=$((changed+1))
}

echo "-- Checking asset versions (content-hash based) --"
bump_asset app.css
bump_asset app.js
bump_sw_cache_name

echo ""
if [ "$changed" -eq 0 ]; then
  echo "Nothing to update -- all references already match current file content."
else
  echo "Updated $changed reference(s). Review with 'git diff', then deploy as usual."
fi
