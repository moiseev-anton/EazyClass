# Настройка TableParser в основной локальной базе и production

Это настройки обычного EazyClass (`eazyclass.settings`), а не изолированного
стенда на 18080. Файл `tableparser-releases/compose.secret` к ним не относится.

## Локально через Docker Compose

В `.env.dev`:

```dotenv
TABLEPARSER_RELEASE_DIR=C:/Users/lenovo/Desktop/EazyClassProject/tableparser-releases/0.1.1
TABLEPARSER_CATALOG_SOURCE=https://eazyclass.ru/api/v1
TABLEPARSER_PUBLIC_BASE_URL=http://127.0.0.1:8000
TABLEPARSER_DJANGO_IMAGE=eazyclass-parser:YOUR_NEW_RELEASE_TAG
TABLEPARSER_WORKER_IMAGE=eazyclass-parser-worker:YOUR_NEW_RELEASE_TAG
```

Последние две переменные — теги действительно собранных образов с установленным
пакетом парсера, не буквальные значения с YOUR_NEW_RELEASE_TAG. Обычный Dockerfile
и requirements.txt сами по себе пакет парсера пока не устанавливают. Сборка образов
описана в [инструкции выпуска](tableparser-server-release.md#сборка-образов).
Нужны образы из текущего кода; старые `faa9571` не содержат последних доработок.

Использовать одновременно dev-compose и overlay:

```powershell
docker compose --env-file .env.dev -f docker-compose.dev.yml -f docker-compose.tableparser.yml up -d --no-build django celery-worker celery-beat
```

Overlay подключает комплект только для чтения и сам задаёт
`TABLEPARSER_RESOURCE_ROOT=/opt/tableparser-release/runtime` внутри контейнеров.
Не задавать Windows-путь как RESOURCE_ROOT для Linux-контейнера.
`--env-file .env.dev` нужен и для подстановки переменных самого Compose.

## Production через Docker Compose

В `.env`:

```dotenv
TABLEPARSER_RELEASE_DIR=/srv/tableparser/releases/0.1.1
TABLEPARSER_CATALOG_SOURCE=https://eazyclass.ru/api/v1
TABLEPARSER_PUBLIC_BASE_URL=https://eazyclass.ru
TABLEPARSER_DJANGO_IMAGE=eazyclass-parser:YOUR_NEW_RELEASE_TAG
TABLEPARSER_WORKER_IMAGE=eazyclass-parser-worker:YOUR_NEW_RELEASE_TAG
```

В RELEASE_DIR должен находиться перенесённый комплект с `runtime/`, `seed/`,
`image/`, `release.json`. PUBLIC_BASE_URL — внешний адрес именно вашего EazyClass,
без `/admin/` в конце. Он используется для ссылки из отчёта.

```sh
docker compose --env-file .env -f docker-compose.yml -f docker-compose.tableparser.yml up -d --no-build django celery-worker celery-beat flower
```

Образы должны быть доставлены на сервер заранее. В production использовать
закреплённые теги или digest, не тестовый образ sandbox. Перед первым включением
выполнить этапы первоначальной подготовки ниже. Beat запускает уже включённые
периодические задачи: до завершения подготовки держать их выключенными.

## Если Django и Celery запускаются прямо в Windows, без Docker

В `.env.dev` достаточно настроек runtime (образы и RELEASE_DIR не используются):

```dotenv
TABLEPARSER_RESOURCE_ROOT=C:/Users/lenovo/Desktop/EazyClassProject/tableparser-releases/0.1.1/runtime
TABLEPARSER_CATALOG_SOURCE=https://eazyclass.ru/api/v1
TABLEPARSER_PUBLIC_BASE_URL=http://127.0.0.1:8000
```

В используемом Python-окружении должен быть установлен проверенный wheel
TableParser с его зависимостями. Перезапустить Django и Celery после изменения env.

## Первоначальная подготовка каждой отдельной базы

Миграции создают таблицы, но не импортируют знания. Если в этой базе первоначальный
импорт ещё не выполнен, запустить внутри соответствующего контейнера Django:

```sh
python manage.py import_tableparser_knowledge /opt/tableparser-release/seed/knowledge.sqlite3
python manage.py import_tableparser_knowledge /opt/tableparser-release/seed/knowledge.sqlite3 --apply
python manage.py check_tableparser_release /opt/tableparser-release/release.json --expected-sha256 e8251bda3a70b81596e4ffffba5570d9949966f85fb45b04fe850891d87427b1 --require-imported
```

Контрольная сумма выше относится именно к подготовленному комплекту 0.1.1.
Для другого комплекта нужна его утверждённая сумма. На native Windows заменить
`/opt/tableparser-release` абсолютным путём к комплекту. При обновлениях кодовой
базы память заново не импортировать. Рабочие знания сохраняются в PostgreSQL.

Обычные `TELEGRAM_BOT_TOKEN` и `TELEGRAM_ADMIN_BOT_TOKEN` остаются прежними.
Переменные `SANDBOX_*` и `TABLEPARSER_LOCAL_SANDBOX` здесь не нужны.
`TABLEPARSER_CATALOG_SOURCE` не переключается на localhost: это пространство имён
импортированной памяти, а не адрес API, куда парсер ходит за справочниками.
