# ===== Стадия 1: сборка зависимостей =====
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

# Установка build-зависимостей для компиляции пакетов
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Установка зависимостей в отдельную директорию /install
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt



# ===== Стадия 2: финальный образ =====
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# runtime-зависимость для PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Копируем только установленные пакеты из builder
COPY --from=builder /install /usr/local

WORKDIR /app

COPY . .
