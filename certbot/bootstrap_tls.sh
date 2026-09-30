#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"
ENV_FILE="$SCRIPT_DIR/.env"

# --- Load env ---------------------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ $ENV_FILE not found"
    echo "👉 Create it from certbot/env.example"
    exit 1
fi

source "$ENV_FILE"

# --- Validate env -----------------------------------------------------------
: "${TLS_PRIMARY_DOMAIN:?TLS_PRIMARY_DOMAIN is required}"
: "${TLS_DOMAINS:?TLS_DOMAINS is required}"
: "${TLS_EMAIL:?TLS_EMAIL is required}"
: "${TLS_CRON_SCHEDULE:?TLS_CRON_SCHEDULE is required}"


echo "🔐 Bootstrapping TLS for $TLS_PRIMARY_DOMAIN"

# --- Ensure nginx is running (HTTP-01 needs port 80) ------------------------
docker compose -f "$COMPOSE_FILE" up -d nginx

# --- Check if certificate already exists -----------------------------------
if docker compose -f "$COMPOSE_FILE" run --rm certbot certificates \
    | grep -q "$TLS_PRIMARY_DOMAIN"; then
    echo "✔ Certificate already exists, skipping initial issuance"
else
    echo "📜 Requesting initial certificate..."
    docker compose -f "$COMPOSE_FILE" run --rm certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        $TLS_DOMAINS \
        --email "$TLS_EMAIL" \
        --agree-tos \
        --no-eff-email \
        --non-interactive || {
            echo "❌ Failed to obtain certificate"
            exit 1
        }
fi

# --- Reload nginx -----------------------------------------------------------
docker compose -f "$COMPOSE_FILE" exec -T nginx nginx -s reload



# Install or update renewal scheduling without repeating certificate operations.
bash "$SCRIPT_DIR/install_renewal.sh"

echo "✅ TLS bootstrap completed"
