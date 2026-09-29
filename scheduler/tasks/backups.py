import logging
import os
import subprocess
from datetime import datetime, timezone
from time import perf_counter
from typing import Optional

from celery import shared_task
from django.conf import settings

from eazyclass.logging_config import safe_error_context


logger = logging.getLogger(__name__)


BACKUP_DIR = "/tmp/db_backups"
REMOTE_PATH = "yandex:backups/postgres/"
ROTATION_DAYS = 7
SUBPROCESS_TIMEOUT = 3600
RCLONE_TIMEOUT = 1800


def run_subprocess(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Capture command output; the task boundary owns error logging."""
    kwargs.setdefault("stdout", subprocess.PIPE)
    kwargs.setdefault("stderr", subprocess.PIPE)
    return subprocess.run(cmd, check=True, text=False, **kwargs)


def create_pg_dump(db_settings: dict) -> str:
    """Создаёт дамп базы. Возвращает путь к файлу или поднимает исключение."""
    db_host = db_settings["HOST"]
    db_port = str(db_settings.get("PORT", 5432))
    db_name = db_settings["NAME"]
    db_user = db_settings["USER"]
    db_password = db_settings["PASSWORD"]

    utc_now = datetime.now(timezone.utc)
    timestamp = utc_now.strftime("%Y-%m-%d_%H%M%S-UTC")
    dump_file = os.path.join(BACKUP_DIR, f"{db_name}_{timestamp}.dump")

    os.makedirs(BACKUP_DIR, exist_ok=True)

    env = os.environ.copy()
    env["PGPASSWORD"] = db_password

    started = perf_counter()
    logger.info("Начинается создание дампа базы данных", extra={"event": "backup.dump.started"})

    try:
        with open(dump_file, "wb") as f:
            run_subprocess(
                [
                    "pg_dump",
                    "-h", db_host,
                    "-p", db_port,
                    "-U", db_user,
                    "-Fc",
                    "--no-owner",
                    "--no-privileges",
                    db_name,
                ],
                stdout=f,
                stderr=subprocess.PIPE,
                env=env,
                timeout=SUBPROCESS_TIMEOUT,
            )
    except Exception:
        # The caller has no path yet if creation failed: remove the partial dump here.
        cleanup_local_file(dump_file)
        raise

    logger.info("Дамп базы данных создан", extra={
        "event": "backup.dump.completed", "size_bytes": os.path.getsize(dump_file),
        "duration_ms": round((perf_counter() - started) * 1000, 3),
    })
    return dump_file


def upload_to_remote_storage(dump_file: str) -> None:
    """Загружает файл в удалённое хранилище."""
    started = perf_counter()
    logger.info("Начинается загрузка дампа в удалённое хранилище",
                extra={"event": "backup.upload.started"})
    run_subprocess(["rclone", "copy", dump_file, REMOTE_PATH], timeout=RCLONE_TIMEOUT)
    logger.info("Дамп загружен в удалённое хранилище", extra={
        "event": "backup.upload.completed",
        "duration_ms": round((perf_counter() - started) * 1000, 3),
    })


def rotate_remote_backups() -> None:
    """Удаляет старые бэкапы в удалённом хранилище."""
    started = perf_counter()
    logger.info("Начинается удаление удалённых бэкапов старше %s дней", ROTATION_DAYS,
                extra={"event": "backup.rotation.started", "retention_days": ROTATION_DAYS})
    run_subprocess(["rclone", "delete", REMOTE_PATH, "--min-age", f"{ROTATION_DAYS}d"], timeout=300)
    # Successful exit confirms completion, but does not tell us how many files were deleted.
    logger.info("Ротация удалённых бэкапов завершена", extra={
        "event": "backup.rotation.completed",
        "duration_ms": round((perf_counter() - started) * 1000, 3),
    })


def cleanup_local_file(dump_file: str) -> None:
    """Удаляет локальный файл, не скрывая исходную ошибку при сбое очистки."""
    try:
        if os.path.exists(dump_file):
            os.unlink(dump_file)
            logger.debug("Локальный дамп удалён", extra={"event": "backup.cleanup.completed"})
    except OSError as exc:
        logger.warning("Не удалось удалить локальный дамп", extra={
            "event": "backup.cleanup.failed", **safe_error_context(exc),
        })


@shared_task(
    bind=True,
    name="backup.periodic_database_backup",
    queue="periodic_tasks",
    max_retries=3,
    default_retry_delay=180,
    retry_backoff=True,
)
def periodic_database_backup(self):
    dump_file: Optional[str] = None
    started = perf_counter()
    stage = "dump"
    attempt = self.request.retries + 1
    logger.info("Начинается резервное копирование базы данных",
                extra={"event": "backup.started", "attempt": attempt})
    try:
        dump_file = create_pg_dump(settings.DATABASES["default"])
        stage = "upload"
        upload_to_remote_storage(dump_file)
        stage = "rotation"
        rotate_remote_backups()
        logger.info("Резервное копирование и ротация завершены", extra={
            "event": "backup.completed", "attempt": attempt,
            "duration_ms": round((perf_counter() - started) * 1000, 3),
        })
        return "OK"
    except Exception as exc:
        retryable = isinstance(exc, (subprocess.TimeoutExpired, subprocess.CalledProcessError))
        will_retry = retryable and self.request.retries < self.max_retries
        details = {"stage": stage, "attempt": attempt,
                   "duration_ms": round((perf_counter() - started) * 1000, 3),
                   **safe_error_context(exc)}
        if isinstance(exc, subprocess.CalledProcessError):
            details["exit_code"] = exc.returncode
        if isinstance(exc, subprocess.TimeoutExpired):
            details["timeout_seconds"] = exc.timeout
        if will_retry:
            logger.warning("Сбой резервного копирования на этапе %s; запрашивается повтор", stage,
                           extra={"event": "backup.retry_requested",
                                  "retry_delay_seconds": self.default_retry_delay, **details})
            raise self.retry(exc=exc)
        logger.error("Резервное копирование завершилось ошибкой на этапе %s", stage,
                     extra={"event": "backup.failed", **details})
        raise
    finally:
        if dump_file:
            cleanup_local_file(dump_file)
