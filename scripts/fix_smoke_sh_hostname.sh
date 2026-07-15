#!/usr/bin/env bash
# FreqLearn — fix smoke.sh to point at the real production hostname.
# Run once on server:
#   bash /var/www/freqlearn/scripts/fix_smoke_sh_hostname.sh
#
# Background: smoke.sh defaults UI_BASE=http://127.0.0.1, which on the
# droplet hits the catch-all default_server in /etc/nginx/sites-enabled/onehouse
# (port 80, returns 404 for any host that isn't onehouse.top/www.onehouse.top/etc).
# The actual production site is https://build.onehouse.top. The smoke test must
# use that hostname to exercise the freqlearn server block (port 443).

set -euo pipefail

TARGET="${1:-/var/www/freqlearn/scripts/smoke.sh}"

if [ ! -f "$TARGET" ]; then
  echo "ERROR: $TARGET not found"
  exit 1
fi

# Make a backup just in case
cp "$TARGET" "${TARGET}.bak.$(date +%Y%m%d_%H%M%S)"

# Replace UI_BASE default — old: http://127.0.0.1
sed -i 's|UI_BASE="${UI_BASE:-http://127\.0\.0\.1}"|UI_BASE="${UI_BASE:-https://build.onehouse.top}"|' "$TARGET"

# Replace API_BASE default — old: http://127.0.0.1:8000
# (API on port 8000 is only reachable locally; for the smoke test against
#  the production hostname, the API goes through the same nginx proxy,
#  so API_BASE should also be the public hostname.)
sed -i 's|API_BASE="${API_BASE:-http://127\.0\.0\.1:8000}"|API_BASE="${API_BASE:-https://build.onehouse.top}"|' "$TARGET"

# Verify
echo "=== After patch — first 10 lines of $TARGET ==="
head -n 10 "$TARGET"

echo ""
echo "Test it with:"
echo "  bash -n $TARGET && echo 'syntax OK'"
echo "  bash $TARGET"