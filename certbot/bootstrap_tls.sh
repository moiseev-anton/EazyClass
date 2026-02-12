#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"
ENV_FILE="$SCRIPT_DIR/.env"

# --- Load env ---------------------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ $ENV_FILE not found"
    echo "👉 Create it from scripts/env.example"
    exit 1
fi

source "$ENV_FILE"

# --- Validate env -----------------------------------------------------------
: "${TLS_PRIMARY_DOMAIN:?TLS_PRIMARY_DOMAIN is required}"
: "${TLS_DOMAINS:?TLS_DOMAINS is required}"
: "${TLS_EMAIL:?TLS_EMAIL is required}"
: "${TLS_CRON_SCHEDULE:?TLS_CRON_SCHEDULE is required}"

echo "DEBUG: Загрузили переменные .env"
echo "DEBUG: TLS_PRIMARY_DOMAIN='$TLS_PRIMARY_DOMAIN'"
echo "DEBUG: TLS_DOMAINS='$TLS_DOMAINS'"
echo "DEBUG: TLS_EMAIL='$TLS_EMAIL'"
echo "DEBUG: TLS_EMAIL='$TLS_EMAIL'"
echo "DEBUG: TLS_CRON_SCHEDULE='$TLS_CRON_SCHEDULE'"

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
docker compose -f "$COMPOSE_FILE" exec nginx nginx -s reload



# --- Install cron job for daily tls renew -----------------------------------
CRON_FILE="/etc/cron.d/eazyclass-certbot"
RENEW_SCRIPT="$SCRIPT_DIR/renew_tls.sh"

# --- Validate renew script --------------------------------------------------
chmod 755 "$RENEW_SCRIPT" 2>/dev/null || true

# --- Install cron -----------------------------------------------------------
if [ ! -f "$CRON_FILE" ]; then
    echo "⏰ Installing cron job at $TLS_CRON_SCHEDULE"
    sudo tee "$CRON_FILE" > /dev/null <<EOF
# Renew Let's Encrypt certificates for eazyclass
$TLS_CRON_SCHEDULE root $RENEW_SCRIPT >> /var/log/certbot-renew.log 2>&1
EOF
    sudo chmod 644 "$CRON_FILE"
    sudo systemctl restart cron || true
else
    echo "✔ Cron job already installed"
fi

echo "✅ TLS bootstrap completed"
