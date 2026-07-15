#!/usr/bin/env bash
# Strip CRLF line endings from smoke.sh so bash can parse `set -euo pipefail`.
# Run once on the server:
#   bash /var/www/freqlearn/scripts/fix_smoke_sh_crlf.sh

set -euo pipefail

TARGET="${1:-/var/www/freqlearn/scripts/smoke.sh}"

if [ ! -f "$TARGET" ]; then
  echo "ERROR: $TARGET not found"
  exit 1
fi

# Make a backup just in case
cp "$TARGET" "${TARGET}.bak.$(date +%Y%m%d_%H%M%S)"

# Strip CR characters from every line ending
sed -i 's/\r$//' "$TARGET"

# Verify
if file "$TARGET" | grep -q "CRLF"; then
  echo "WARN: $TARGET still has CRLF — sed may not have worked"
  exit 2
fi

echo "OK: $TARGET now has LF line endings"
echo "     backup at ${TARGET}.bak.*"
echo ""
echo "Test it with:"
echo "  bash -n $TARGET && echo 'syntax OK'"
echo "  bash $TARGET"