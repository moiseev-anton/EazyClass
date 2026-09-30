# Локальный сбор логов

Отдельный Compose-проект `eazyclass-observability`: Alloy читает Docker API и
файл cron, Loki хранит записи, Grafana предоставляет поиск. Основные Compose-файлы
и работающие контейнеры приложения менять не требуется.

## Первый запуск

Все команды выполняются из корня репозитория. Нужны Docker Compose v2 и Linux
containers (в том числе Docker Desktop). Узнать имя проекта приложения:

```bash
docker compose ls
```

Скопировать `observability/.env.example` в `observability/.env` и проверить
`APP_COMPOSE_PROJECT`. Это метка Compose-проекта, а не имя контейнера или сервиса.
Локальное значение сейчас — `eazyclassproject`. Файл `.env` этого стека
не использует секреты приложения из корневого `.env`.

Создать `observability/grafana-admin.secret` с уникальным паролем администратора
в UTF-8 без BOM. Например, в Linux:

```bash
umask 077
openssl rand -base64 24 > observability/grafana-admin.secret
```

Для текущей локальной установки файл уже создан. Он, `.env` и тестовые логи
исключены из Git. Grafana получает пароль через Compose secret; учётная запись
`admin`. Пароль применяется при первом создании БД Grafana. Последующие изменения
этого файла не меняют пароль существующего пользователя — это делается в Grafana.

```bash
docker compose --env-file observability/.env -f docker-compose.observability.yml config --quiet
docker compose --env-file observability/.env -f docker-compose.observability.yml up -d
```

Открыть <http://localhost:3000>, войти и выбрать Explore → Loki. Источник Loki
подключается автоматически. Сначала выбрать период «последние 15 минут».

```logql
{environment="development", service="django"}
```

Другие примеры:

```logql
{environment="development", service="celery-worker"} | json | event="schedule.sync.completed"
{environment="development", service="nginx"} | json | status_code >= 500
{environment="development", service="certbot"}
```

Имя события брать из реальных записей. Для JSON можно добавить `| json`, а
затем фильтровать `request_id`, `run_id`, `event` и остальные поля. `level`
доступен как метка у JSON-записей, содержащих поле `level`; обычный текст
не отбрасывается. Локальные приложения по-прежнему могут писать компактный
текст. Для структурированного поиска задать им `LOG_FORMAT=json` в `.env.dev`
и пересоздать только нужные контейнеры, когда удобно.

`service` — Compose-сервис источника. Сообщения subprocess Scrapy находятся
в потоке `celery-worker`; исходное поле JSON `service` сохраняется в строке
(при `| json` совпадающее имя поля отображается как `service_extracted`).
Идентификаторы пользователей/запросов не становятся индексными метками Loki.

## Certbot и ротация

Локально `/var/log/host` внутри Alloy — это `observability/host-logs`.
Если там нет `certbot-renew.log`, сборщик ждёт появления файла. На Linux-сервере
нужно задать `CERTBOT_LOG_DIR=/var/log` и `OBS_ENVIRONMENT=production`.
Читается только `certbot-renew.log`, не весь каталог. Docker-сервис `certbot`
исключён, так как его вывод уже записан cron в этот файл.

Монтируется каталог, а не отдельный файл: после logrotate сборщик должен
увидеть новый файл. Непрочитанный архив после длительного простоя автоматически
не импортируется. Не собирать одновременно `.log` и все архивы по маске:
это может повторно отправить уже прочитанные строки.

## Хранение, доступ и ограничения

- Loki хранит данные в `loki_data`, Grafana — пользователей и настройки в
  `grafana_data`, Alloy — позиции чтения в `alloy_data`.
- Срок хранения Loki — 7 дней. Compactor удаляет старые данные асинхронно,
  с задержкой; это не ограничение объёма диска. Docker-ротация действует отдельно.
- Окно подхвата записей — последние 55 минут (с запасом до часового окна
  внеочередных записей Loki). Архив за прошлые дни не импортируется автоматически.
  Это также ограничивает восстановление после долгого простоя Alloy. Семь дней
  хранения отсчитываются для уже собранных записей и не означают импорт семи дней
  Docker-истории. Для текстовых строк без времени используется время источника:
  Docker предоставляет своё время, для файла это время чтения.
- Только Grafana публикует порт, и только на `127.0.0.1`. Loki и Alloy доступны
  внутри сети этого Compose-проекта. На сервере для начала можно использовать
  SSH-туннель: `ssh -L 3000:127.0.0.1:3000 user@server`.
- Alloy работает от root для чтения Docker socket и root-owned файла cron.
  `:ro` на сокете не ограничивает возможности Docker API: конфигурация и контейнер
  Alloy требуют доверия. Административный интерфейс Alloy наружу не опубликован.
- При недоступности Loki Alloy повторяет отправку до 20 раз с паузой до 30 секунд.
  Недоставленная очередь находится в памяти. Авария Alloy или исчерпание повторов
  могут привести к потере записей. Позиция чтения — не подтверждение доставки.
  Экспериментальная дисковая очередь Alloy на этом этапе не включена.
- Loki использует свой WAL для восстановления принятых данных. Это не резервная
  копия и не защита от потери диска. Все три сервиса на одном сервере разделяют
  его доступность.
- Ресурсы пока измеряются, жёсткие лимиты памяти не подобраны. Ограничены
  параллелизм запросов Loki и размер кеша. Перед продом проверить нагрузку
  одновременно с пауком/рассылками и свободное место. Дашборды и оповещения —
  следующий этап; текущая конфигурация сама никого не уведомляет.

## Проверка и обслуживание

```bash
docker compose --env-file observability/.env -f docker-compose.observability.yml ps
docker compose --env-file observability/.env -f docker-compose.observability.yml logs --tail=50
docker compose --env-file observability/.env -f docker-compose.observability.yml stats --no-stream
```

Проверить синтаксис конфигураций после изменения:

```bash
docker compose --env-file observability/.env -f docker-compose.observability.yml run --rm --no-deps alloy validate /etc/alloy/config.alloy
docker compose --env-file observability/.env -f docker-compose.observability.yml run --rm --no-deps loki '-config.file=/etc/loki/config.yml' '-verify-config=true'
```

Изменения bind-mounted конфигураций применять перезапуском нужного сервиса;
изменения `.env`/Compose — `up -d`. Конфигурация datasource Grafana читается
при запуске. Версии образов зафиксированы и обновляются явно с проверкой.

Остановить только сбор и интерфейс, сохранив данные:

```bash
docker compose --env-file observability/.env -f docker-compose.observability.yml down
```

Не добавлять `--volumes`, если данные нужны. Для переноса на новый сервер
сохранить конфигурации, секрет и согласованные копии volumes (после остановки
стека), восстановить их и проверить имя Compose-проекта приложения.

Документация: [Docker source](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.docker/),
[File source](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.file/),
[повторные отправки](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.write/),
[срок хранения](https://grafana.com/docs/loki/latest/operations/storage/retention/).
