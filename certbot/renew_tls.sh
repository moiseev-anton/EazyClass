#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"
stage="renew"

log() {
    printf '%s %s\n' "$(date -Iseconds)" "$*"
}

on_error() {
    local status=$?
    log "ERROR: проверка сертификатов завершилась ошибкой; этап=$stage код=$status" >&2
    exit "$status"
}
trap on_error ERR

log "Начинается проверка продления сертификатов"
docker compose -f "$COMPOSE_FILE" run --rm -T certbot renew \
  --webroot \
  --webroot-path=/var/www/certbot \
  --quiet \
  --non-interactive

stage="nginx_config_check"
log "Проверяется конфигурация nginx"
docker compose -f "$COMPOSE_FILE" exec -T nginx nginx -t

stage="nginx_reload"
log "Отправляется команда reload nginx"
docker compose -f "$COMPOSE_FILE" exec -T nginx nginx -s reload
log "Проверка продления завершена; команда reload nginx выполнена успешно"
