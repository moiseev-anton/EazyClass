# =============================================================================
# Стадия 1: сборка Python-зависимостей (builder)
# =============================================================================
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

# Build-зависимости для компиляции пакетов (psycopg2 и т.п.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# =============================================================================
# Стадия 2: общая runtime-основа (базовый образ со всеми сервисами)
# =============================================================================
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Минимальные runtime-зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем установленные пакеты из builder
COPY --from=builder /install /usr/local

# Копируем весь проект (один раз — кэшируется для всех последующих стадий)
COPY . .


# =============================================================================
# Стадия 3: чистый образ для django / flower (без бэкап-утилит)
# =============================================================================
FROM base AS django


# =============================================================================
# Стадия 4: образ с инструментами для бэкапов (worker и beat)
# =============================================================================
FROM base AS backup-tools

# Подключаем официальный репозиторий PostgreSQL (PGDG)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    && curl https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/trusted.gpg.d/apt.postgresql.org.gpg \
    && echo "deb http://apt.postgresql.org/pub/repos/apt trixie-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем именно клиент версии 16 + rclone
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client-16 \
    rclone \
    && rm -rf /var/lib/apt/lists/*

# Проверка версии (выводится при сборке образа — удобно для отладки)
RUN pg_dump --version | grep "16\." && echo "OK: postgresql-client-16 установлен" \
    || { echo "ОШИБКА: установлен НЕ postgresql-client-16"; exit 1; }