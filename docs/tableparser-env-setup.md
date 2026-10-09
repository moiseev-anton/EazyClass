# Настройка TableParser в основной локальной базе и production

Dockerfile устанавливает EazyClass и TableParser за одну сборку. Compose передаёт
каталог `${TABLEPARSER_RELEASE_DIR}/image` как дополнительный контекст сборки,
а весь релиз подключает в контейнер только для чтения. Знания остаются в PostgreSQL.
Нужны Docker Compose 2.17+ и BuildKit: [additional_contexts](https://docs.docker.com/reference/compose-file/build/#additional_contexts).
Зависимости скачиваются при первой сборке; дальнейшие изменения кода используют кеш.

## Переменные окружения

В production `.env`:

```dotenv
TABLEPARSER_RELEASE_DIR=/srv/tableparser/releases/0.1.1
TABLEPARSER_CATALOG_SOURCE=https://eazyclass.ru/api/v1
TABLEPARSER_PUBLIC_BASE_URL=https://eazyclass.ru
```

В каталоге релиза должны быть `image/`, `runtime/`, `seed/`, `release.json`.
`image/` содержит wheel, `wheel.sha256` и `constraints.txt`. Docker проверяет хеш
пакета и устанавливает зависимости совместно с requirements.txt. Конфликт версий
останавливает сборку, а не приводит к незаметной замене зависимостей приложения.
`CATALOG_SOURCE` — историческое пространство имён, не URL для запроса справочников.
`PUBLIC_BASE_URL` — адрес приложения для ссылок в отчётах.

Compose сам задаёт `TABLEPARSER_RESOURCE_ROOT=/opt/tableparser-release/runtime`.
Существующую строку с таким значением можно оставить в `.env`.
`TABLEPARSER_DJANGO_IMAGE` и `TABLEPARSER_WORKER_IMAGE` при обычном запуске
не используются; старые строки можно удалить. Они нужны только для необязательного
режима готовых образов ниже. `.env` целиком не заменять: остальные настройки сохраняются.

## Обновление на сервере

Обычное изменение кода без миграций:

```sh
cd /home/eazy/apps/eazyclass
git pull --ff-only
docker compose up -d --build django celery-worker celery-beat flower
```

Команды выполнять после попадания изменений в используемую ветку.
Дополнительный `-f docker-compose.tableparser.yml` не нужен. Старое сокращение `dc`,
которое подключает этот файл, для обычной сборки не использовать; можно переопределить:

```sh
dc() { docker compose --env-file .env -f docker-compose.yml "$@"; }
```

Первый переход с готовых образов 0.1.1 не требует новых миграций или повторного
импорта знаний. Существующий каталог `/srv/tableparser/releases/0.1.1` подходит.
При первой сборке Compose создаст обычные образы проекта и заменит контейнеры.
Старые образы релиза останутся доступны для отката. Запуск beat включает настроенные задачи.

Если есть миграции: сначала сделать резервную копию, остановить beat, дождаться
активных задач, затем остановить worker и Django. После сборки применить миграции
и собрать статику до запуска новых процессов:

```sh
docker compose build django celery-worker celery-beat flower
docker compose run --rm --no-deps django python manage.py migrate --noinput
docker compose run --rm --no-deps django python manage.py collectstatic --noinput
docker compose up -d --no-build django celery-worker flower
# После проверки приложения:
docker compose up -d --no-build celery-beat
```

При изменении CSS/JS админки также выполнить collectstatic.
Первоначальные знания повторно не импортировать. При новой версии TableParser
доставить новый релиз, изменить RELEASE_DIR, пересобрать и проверить готовность
с утверждённым SHA256 нового манифеста. Не редактировать опубликованный релиз на месте.

## Локально через Docker Compose

В `.env.dev` те же настройки, но локальные пути и URL:

```dotenv
TABLEPARSER_RELEASE_DIR=C:/Users/lenovo/Desktop/EazyClassProject/tableparser-releases/0.1.1
TABLEPARSER_CATALOG_SOURCE=https://eazyclass.ru/api/v1
TABLEPARSER_PUBLIC_BASE_URL=http://127.0.0.1:8000
```

```powershell
./scripts/tableparser-local.ps1 start
./scripts/tableparser-local.ps1 status
./scripts/tableparser-local.ps1 check
./scripts/tableparser-local.ps1 logs
```

`start` выполняет сборку. Прямой эквивалент:

```powershell
docker compose --env-file .env.dev -f docker-compose.dev.yml up -d --build django celery-worker celery-beat
```

Флаг `--env-file .env.dev` нужен для подстановок Compose, не только env контейнеров.
Отдельный стенд на 18080 по-прежнему управляется `scripts/parser-sandbox.ps1`.

## Необязательный режим готовых образов

Для доставки уже собранных образов или отката оставить дополнительные переменные:

```dotenv
TABLEPARSER_DJANGO_IMAGE=eazyclass-parser:prod-21ba81a
TABLEPARSER_WORKER_IMAGE=eazyclass-parser-worker:prod-21ba81a
```

Загрузить соответствующие образы и использовать оба файла:

```sh
docker compose --env-file .env -f docker-compose.yml -f docker-compose.tableparser.yml up -d --no-build --pull never django celery-worker celery-beat flower
```

Это отдельный режим: не использовать в нём `--build`, чтобы не перезаписать теги релиза.
Код и схема БД должны быть совместимы с выбранными образами.

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
