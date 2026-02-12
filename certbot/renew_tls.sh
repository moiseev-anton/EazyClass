#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"

echo "🔄 Running certbot renew..."

docker compose -f "$COMPOSE_FILE" run --rm certbot renew \
  --webroot \
  --webroot-path=/var/www/certbot \
  --quiet \
  --non-interactive

echo "🔁 Reloading nginx..."
docker compose -f "$COMPOSE_FILE" exec nginx nginx -s reload || true
