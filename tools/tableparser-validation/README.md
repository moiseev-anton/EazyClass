# Изолированная установка TableParser вместе с EazyClass

Этот Dockerfile предназначен для проверки зависимостей, а не для запуска
production-сервисов. Он создаёт отдельный venv без system-site-packages,
устанавливает весь `requirements.txt` и выбранный wheel с дополнением `ml`,
затем выполняет `pip check`. Для psycopg2 устанавливаются build-зависимости,
как в основном Dockerfile проекта.

В отдельный каталог контекста сборки скопировать только:

- этот `Dockerfile`;
- актуальный `requirements.txt` EazyClass;
- один проверенный `eazyclass_tableparser-*.whl`.

Не передавать корень рабочего проекта как контекст. Пример:

```powershell
docker build --progress plain --tag tableparser-validation:local PATH_TO_CONTEXT
docker run --rm --network none tableparser-validation:local
```

`BASE_IMAGE` по умолчанию — `python:3.12-slim`. Для локальной проверки можно
использовать уже имеющийся Python 3.12 Linux-образ через `--build-arg BASE_IMAGE=...`;
установленные в нём Python-библиотеки не наследуются venv. Проверка не запускает
его исходную команду приложения: entrypoint и command заменены. Такой образ может
содержать старый код приложения и не предназначен для публикации как выпуск.

Внутри образа сохраняются `/validation/install-report.json` (источники и хеши
пакетов) и `/validation/installed.txt` (полный список версий). Для воспроизведения
выпуска сохранять их вместе с wheel, sdist, контрольными суммами моделей/правил,
версией Python и идентификатором образа. `installed.txt` содержит локальную ссылку
на wheel: при переносе указывать сохранённый wheel явно, а не копировать эту
ссылку как существующий путь на другом сервере.

Для тестов монтировать отдельный экспорт исходников EazyClass в `/workspace`
только для чтения. Он должен содержать проверяемые изменения, но не `.env` и
рабочие данные. `PYTHONPATH=/workspace` нужен только для исходников Django:
TableParser и все зависимости загружаются из нового venv. Тестовый комплект
моделей монтировать отдельно, только для чтения, и указывать через
`TABLEPARSER_TEST_RESOURCE_ROOT`.

PostgreSQL и Redis должны быть временными. Можно создать PostgreSQL-контейнер
без опубликованных портов, а Redis и тестовый контейнер запустить с
`--network container:NAME_OF_TEST_POSTGRES`. Тогда тестовые настройки используют
`127.0.0.1`, `TABLEPARSER_TEST_PG_PORT=5432`, `TABLEPARSER_TEST_REDIS_PORT=6379`.
Команда тестового контейнера:

```text
-m django test schedule_ingestion.tests scheduler.tests.test_lesson_sync_range scheduler.tests.test_lesson_annotation_sync --settings=schedule_ingestion.tests.publication_postgres_settings --noinput
```

Эта проверка не заменяет проверку production-миграций, Linux-prefork и
принудительного завершения отдельного worker-процесса. Ограничения тестов
описаны в `docs/tableparser-worker-validation.md`.
