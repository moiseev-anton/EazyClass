#!/usr/bin/env bash
# Устанавливает/обновляет cron и ротацию логов. Не запускает certbot и контейнеры.
# Прерываем установку при ошибке команды, неопределённой переменной или сбое в pipe.
set -euo pipefail

# Ищем .env рядом со скриптом, независимо от текущего рабочего каталога.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "Missing $ENV_FILE; create it from certbot/env.example" >&2
    exit 1
fi
source "$ENV_FILE"
# Завершаемся с понятной ошибкой, если расписание отсутствует или пустое.
: "${TLS_CRON_SCHEDULE:?TLS_CRON_SCHEDULE is required}"

# Разрешаем пять числовых полей cron; запрещаем переносы и дополнительные команды.
# Это проверка формы записи, а не диапазонов значений минут, часов и дней.
if [[ "$TLS_CRON_SCHEDULE" == *$'\n'* || "$TLS_CRON_SCHEDULE" == *$'\r'* ]] ||
   [[ ! "$TLS_CRON_SCHEDULE" =~ ^[0-9*/,-]+[[:blank:]]+[0-9*/,-]+[[:blank:]]+[0-9*/,-]+[[:blank:]]+[0-9*/,-]+[[:blank:]]+[0-9*/,-]+$ ]]; then
    echo "TLS_CRON_SCHEDULE must contain five numeric cron fields" >&2
    exit 1
fi

# Сначала готовим файл целиком. Временный файл удалится и при ошибке установки.
CRON_FILE="$(mktemp)"
trap 'rm -f "$CRON_FILE"' EXIT
# В /etc/cron.d после расписания обязателен пользователь (root).
# У cron ограниченный PATH; задаём его явно для поиска docker и служебных команд.
# Bash запускает скрипт без требования executable-бита; >> и 2>&1 сохраняют оба потока.
cat > "$CRON_FILE" <<EOF
# Managed by certbot/install_renewal.sh
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
$TLS_CRON_SCHEDULE root /bin/bash "$SCRIPT_DIR/renew_tls.sh" >> /var/log/certbot-renew.log 2>&1
EOF

# install копирует файлы с заданными владельцем и правами, заменяя прежнюю версию.
# Постоянное имя cron-файла исключает дубликаты при повторном запуске установщика.
sudo install -o root -g root -m 0644 "$SCRIPT_DIR/logrotate.conf" /etc/logrotate.d/eazyclass-certbot
sudo install -o root -g root -m 0644 "$CRON_FILE" /etc/cron.d/eazyclass-certbot
# Системный cron сам подхватывает изменения /etc/cron.d; перезапуск не требуется.
echo "Cron task updated: /etc/cron.d/eazyclass-certbot"
echo "Log rotation installed: /etc/logrotate.d/eazyclass-certbot"
