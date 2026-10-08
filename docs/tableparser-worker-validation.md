# Проверка Celery через брокер

Общий прогон завершён успешно: 78 тестов ingestion, диапазонов и аннотаций,
включая оба сценария настоящего брокера. Для первого прогона использованы ранее
собранный wheel TableParser и зависимости локального окружения парсера через
`PYTHONPATH`.

8 октября 2026 повторены все 78 тестов в Linux с Python 3.12.13, PostgreSQL 16,
Redis 7 и чистым venv: **все прошли**, включая существующий обученный комплект,
смонтированный только для чтения. Установлены 123 дистрибутива из полного
`requirements.txt` EazyClass и wheel TableParser 0.1.1 с `[ml]`; `pip check`
не обнаружил конфликтов. `PYTHONPATH` содержал только исходники Django.
Для нового wheel разрешён `python-dotenv>=1.2.1,<1.3`, выбран серверный 1.2.1.
Версии ML-библиотек прежние, 52 Python-файла wheel совпадают побайтово с 0.1.0.

Отчёты сохранены в `data/clean-install-0.1.1/`: `build.log`, `install-report.json`,
`installed.txt`, `tests.log`. Образ:
`sha256:b5dfe6c4f7998955b7cfb81ed99853608e09a227f6ad701908916fcafcb13b7d`.
Инструкции повторения чистой установки: `tools/tableparser-validation/README.md`.
Этот прогон проверяет интеграцию с обученным комплектом на малой таблице;
полное сравнение шести исторических выгрузок на Linux ещё не выполнено.
Дополнительно в том же Linux-venv без сети прошли 18 тестов уведомлений;
отчёт — `notification-tests.log`. Сохранилось прежнее предупреждение pytest
об неизвестной настройке `asyncio_default_fixture_loop_scope`.

`schedule_ingestion.tests.test_worker` — отдельные opt-in интеграционные тесты.
Нужны Python-окружение EazyClass с установленным пакетом TableParser, PostgreSQL
16 и Redis 7. Использовать только отдельные временные контейнеры без production
данных, общих очередей и production `.env`.

Пример запуска контейнеров (порты на loopback выбирает Docker):

```powershell
docker run --detach --rm --name tableparser-test-pg --publish 127.0.0.1::5432 --env POSTGRES_DB=tableparser_validation --env POSTGRES_USER=tableparser_validation --env POSTGRES_PASSWORD=local-validation-only postgres:16-alpine
docker run --detach --rm --name tableparser-test-redis --publish 127.0.0.1::6379 redis:7-alpine
docker port tableparser-test-pg 5432/tcp
docker port tableparser-test-redis 6379/tcp
```

В корне EazyClass установить `TABLEPARSER_TEST_PG_PORT` и
`TABLEPARSER_TEST_REDIS_PORT` равными полученным номерам портов, затем:

```powershell
./venv/Scripts/python.exe -B -m django test schedule_ingestion.tests.test_worker --settings=schedule_ingestion.tests.publication_postgres_settings --noinput
```

После проверки остановить только созданные контейнеры:

```powershell
docker stop tableparser-test-redis tableparser-test-pg
```

Тестовые настройки не читают production `.env`. Проверка допускает только
PostgreSQL на `127.0.0.1` с именем тестовой БД `test_tableparser_validation`.
Django создаёт и удаляет эту БД. Redis используется как настоящий брокер и
хранилище результатов (DB 0 и 1); контейнер должен быть выделенным. Без
`TABLEPARSER_TEST_REDIS_PORT` тесты пропускаются. Схема ingestion создаётся
миграциями; текущие модели scheduler — через syncdb, как в остальных тестах
интеграции. Это не проверка цепочки исторических production-миграций scheduler.

Проверяются:

- Получение → настоящий парсер → сохранение экспорта → публикация → уведомления
  → отчёт, с передачей UUID между задачами через JSON/Redis.
- Повтор того же запроса публикации после штатного перезапуска worker:
  одна публикация, одно занятие и по одному вызову каждого отправителя.
- Исключение отправителя: публикация остаётся применённой, доставка получает
  `uncertain`, отчёт остаётся `pending`. Повтор через брокер возвращает
  сериализованную ошибку `DeliveryUncertain` и не вызывает отправитель снова.

Подменяются получение Google-листа и оба отправителя. Справочники и расписание
находятся в тестовом PostgreSQL, парсер использует минимальные временные ресурсы.
Проверка эталонных обученных ресурсов выполняется отдельно существующими тестами.

Worker запускается через Celery `start_worker`, `pool=solo`, в отдельном потоке.
Это проверяет брокер, регистрацию задач, сериализацию, цепочки и повтор доставки,
но не отдельный процесс, Linux-prefork, принудительное завершение процесса,
повторную выдачу unacked-сообщений либо production-мониторинг. Перезапуск в тесте
штатный. Общие Celery app-настройки восстанавливаются при завершении теста;
соединения БД закрываются в потоке worker после каждой задачи.
