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

  # Every .html file that currently references this asset with a ?v= tag --
  # discovered dynamically via grep, not a hardcoded file list, so a new
  # page added later that links app.css/app.js is picked up automatically.
  local refs
  refs=$(grep -l "${basename}\.${ext}?v=" *.html 2>/dev/null || true)

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

echo "-- Checking asset versions (content-hash based) --"
bump_asset app.css
bump_asset app.js

echo ""
if [ "$changed" -eq 0 ]; then
  echo "Nothing to update -- all references already match current file content."
else
  echo "Updated $changed reference(s). Review with 'git diff', then deploy as usual."
fi
