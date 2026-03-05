import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Optional

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.conf import settings


logger = logging.getLogger(__name__)


BACKUP_DIR = "/tmp/db_backups"
REMOTE_PATH = "yandex:backups/postgres/"
ROTATION_DAYS = 7
SUBPROCESS_TIMEOUT = 3600
RCLONE_TIMEOUT = 1800


def run_subprocess(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Запускает команду, логирует stderr при ошибке и поднимает исключение"""
    try:
        return subprocess.run(
            cmd,
            check=True,
            text=False,           # оставляем bytes, декодируем сами при ошибке
            **kwargs,
        )
    except subprocess.CalledProcessError as e:
        stderr_text = (
            e.stderr.decode("utf-8", errors="replace").strip()
            if e.stderr
            else "(stderr отсутствует)"
        )
        logger.error(
            "%s завершился с ошибкой (код %d):\n%s",
            cmd[0],
            e.returncode,
            stderr_text,
        )
        raise


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

    logger.info(f"pg_dump → {dump_file}")

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
    except FileNotFoundError:
        logger.critical("pg_dump не найден в PATH")
        raise
    except subprocess.TimeoutExpired:
        logger.error(f"pg_dump превысил таймаут {SUBPROCESS_TIMEOUT} сек")
        if os.path.exists(dump_file):
            os.unlink(dump_file)
        raise
    except OSError as e:
        logger.error("Ошибка файловой системы при создании дампа: %s", e)
        raise

    return dump_file


def upload_to_remote_storage(dump_file: str) -> None:
    """Загружает файл в удалённое хранилище."""
    logger.info(f"Выполняется rclone copy {dump_file} → {REMOTE_PATH}")

    try:
        subprocess.run(
            ["rclone", "copy", dump_file, REMOTE_PATH],
            check=True,
            timeout=RCLONE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.error(f"rclone copy превысил таймаут {RCLONE_TIMEOUT} сек")
        raise
    except subprocess.CalledProcessError as e:
        logger.error(
            "rclone copy завершился с ошибкой (код %d)\n%s",
            e.returncode,
            e.stderr.decode() if e.stderr else "(stderr отсутствует)",
        )
        raise


def rotate_remote_backups() -> None:
    """Удаляет старые бэкапы в удалённом хранилище."""
    logger.info(f"Ротация: удаление старше {ROTATION_DAYS} дней")

    try:
        result = subprocess.run(
            [
                "rclone",
                "delete",
                REMOTE_PATH,
                "--min-age", f"{ROTATION_DAYS}d",
                "-v",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=300,
        )
        output = result.stdout.strip()
        if output:
            logger.info("Удалено:\n%s", output)
        else:
            logger.info("Нет файлов для удаления")
    except subprocess.TimeoutExpired:
        logger.error("rclone delete превысил таймаут")
        raise
    except subprocess.CalledProcessError as e:
        logger.error(
            "rclone delete завершился с ошибкой (код %d)\n%s",
            e.returncode,
            e.stderr or "(stderr отсутствует)",
        )
        raise


def cleanup_local_file(dump_file: str) -> None:
    """Удаляет локальный файл дампа."""
    try:
        if os.path.exists(dump_file):
            os.unlink(dump_file)
            logger.info("Локальный дамп удалён: %s", dump_file)
    except OSError as e:
        logger.warning("Не удалось удалить локальный файл %s: %s", dump_file, e)


@shared_task(
    bind=True,
    name="backup.periodic_database_backup",
    queue="periodic_tasks",
    max_retries=3,
    default_retry_delay=180,
    retry_backoff=True,
)
def periodic_database_backup(self):
    db_settings = settings.DATABASES["default"]
    dump_file: Optional[str] = None

    try:
        dump_file = create_pg_dump(db_settings)
        upload_to_remote_storage(dump_file)
        rotate_remote_backups()

        logger.info("Бэкап успешно завершён")
        return "OK"

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        # Транзиентные ошибки → retry
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            logger.critical("Исчерпано количество попыток → бэкап провален")
            raise

    except Exception as exc:
        logger.exception("Критическая ошибка при выполнении бэкапа")
        raise

    finally:
        # Очистка всегда, даже если был retry или raise
        cleanup_local_file(dump_file) if dump_file else None
