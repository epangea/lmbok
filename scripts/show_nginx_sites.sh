# FreqLearn — show real nginx server blocks
# Run on server:  bash scripts/show_nginx_sites.sh

set -e

echo "=== Files in /etc/nginx/sites-enabled ==="
ls -la /etc/nginx/sites-enabled/

for f in /etc/nginx/sites-enabled/*; do
  echo ""
  echo "=========================================="
  echo "FILE: $f"
  echo "=========================================="
  cat "$f"
  echo ""
done