import csv
import logging
import re
from pathlib import Path
from time import perf_counter
from typing import Dict, List, Optional, Set, Tuple

import orjson
from celery import shared_task
from eazyclass.logging_config import safe_error_context

from scheduler.models import Group, Teacher
from utils import RedisClientManager
from enums import KeyEnum

logger = logging.getLogger(__name__)




DATA_DIR = Path("/worker_input")


class GoogleScheduleError(Exception):
    pass


def _row_diagnostic(stats, row_number, reason, *, group_id=None, exc=None):
    # Bound diagnostics for large/broken files; the final counters cover all rows.
    stats["diagnostics_count"] = stats.get("diagnostics_count", 0) + 1
    if stats["diagnostics_count"] <= 10:
        logger.debug(
            "Строка %s пропущена при импорте: %s", row_number, reason,
            extra={"event": "schedule.import.row_skipped", "row_number": row_number,
                   "reason": reason, "group_id": group_id,
                   **(safe_error_context(exc) if exc else {})},
        )


def get_latest_file_by_pattern(dir_path: Path, pattern: str) -> Optional[Path]:
    files = sorted(
        dir_path.glob(pattern),                     # ← только "groups_from_google_*.txt"
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    return files[0] if files else None


def normalize_group_name(name: str) -> str:
    """
    Максимально агрессивная нормализация для сопоставления
     - только буквы и цифры, нижний регистр
    """
    if not name:
        return ""
    # Убираем всё лишнее, оставляем буквы, цифры
    cleaned = re.sub(r'[^а-яА-ЯёЁa-zA-Z0-9]', '', name)
    # Нижний регистр
    return cleaned.lower()


def load_group_map() -> Dict[str, int]:
    """Загружает маппинг нормализованного названия группы → id"""
    group_map = {
        normalize_group_name(g["title"]): g["id"]
        for g in Group.objects.filter(is_active=True).values("title", "id")
    }
    logger.debug(f"Загружено групп: {len(group_map)}")
    return group_map


def load_teacher_map() -> Dict[str, str]:
    """Загружает маппинг short_name → full_name"""
    teacher_map = {
        t["short_name"]: t["full_name"]
        for t in Teacher.objects.filter(is_active=True).values("short_name", "full_name")
        if t["short_name"] and t["full_name"]
    }
    logger.debug(f"Загружено учителей: {len(teacher_map)}")
    return teacher_map


def load_processed_groups(
    groups_path: Path, group_map: Dict[str, int], *, stats=None
) -> Tuple[Set[int], int]:
    """Читает файл групп и возвращает set id + количество пропущенных"""
    processed_group_ids = set()
    skipped = 0
    stats = stats if stats is not None else {}

    with open(groups_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            title = line.strip()
            normalized_title = normalize_group_name(title)
            if normalized_title:
                group_id = group_map.get(normalized_title)
                if group_id:
                    processed_group_ids.add(group_id)
                else:
                    _row_diagnostic(stats, line_num, "unknown_txt_group")
                    skipped += 1

    return processed_group_ids, skipped


def process_lessons_csv(
    lessons_path: Path,
    group_map: Dict[str, int],
    teacher_map: Dict[str, str],
    *, stats=None,
) -> Tuple[List[dict], Set[int]]:
    """Читает CSV с уроками, возвращает валидные уроки и failed-группы"""
    all_raw_lessons = []
    failed_group_ids = set()
    stats = stats if stats is not None else {}
    stats.update(rows_count=0, skipped_count=0, invalid_count=0)

    with open(lessons_path, encoding="utf-8-sig") as f:
        # Определяем разделитель
        first_line = f.readline().strip()
        delimiter = ';' if ';' in first_line and ',' not in first_line else ','
        f.seek(0)

        reader = csv.DictReader(f, delimiter=delimiter)
        if not {"group", "date", "lesson_number"}.issubset(reader.fieldnames or []):
            raise GoogleScheduleError("invalid_csv_header")

        # В CSV все элементы строковые
        for row_num, row in enumerate(reader, 1):
            stats["rows_count"] += 1
            group_id = None
            try:
                group_title = row.get("group", "").strip()
                normalized_title = normalize_group_name(group_title)
                group_id = group_map.get(normalized_title)

                if not group_id:
                    stats["skipped_count"] += 1
                    _row_diagnostic(stats, row_num, "unknown_csv_group")
                    continue

                teacher_short = (row.get("teacher") or "").strip() or None
                teacher_full = teacher_map.get(teacher_short, teacher_short)

                lesson = {
                    "group_id": group_id,
                    "period": {
                        "lesson_number": int(row["lesson_number"]),
                        "part": int(row["part"]) if (row.get("part") or "").strip() else None,
                        "date": row["date"].strip(),
                    },
                    "subject": {
                        "title": (row.get("subject") or "").strip() or None,
                    },
                    "classroom": {
                        "title": (row.get("classroom") or "").strip() or None,
                    },
                    "teacher": {
                        "full_name": teacher_full,
                    },
                    "annotation": {
                        "title": (row.get("annotation") or "").strip() or None,
                    },
                    "subgroup": int(row["subgroup"]) if (row.get("subgroup") or "").strip() else None,
                }

                all_raw_lessons.append(lesson)

            except Exception as e:
                stats["invalid_count"] += 1
                _row_diagnostic(stats, row_num, "invalid_csv_row", group_id=group_id, exc=e)
                if group_id:
                    failed_group_ids.add(group_id)

    return all_raw_lessons, failed_group_ids


def build_summary(
    total_groups: int,
    processed_group_ids: Set[int],
    failed_group_ids: Set[int],
    valid_lessons_count: int,
    closing_reason: str,
) -> dict:
    """Формирует summary в нужном формате"""
    valid_group_ids_count = len(processed_group_ids - failed_group_ids)
    return {
        "total_groups": total_groups,
        "parsed": valid_group_ids_count,
        "skipped": 0,
        "no_change": 0,
        "errors": len(failed_group_ids),
        "error_groups": [str(gid) for gid in sorted(failed_group_ids)],
        "total_lessons": valid_lessons_count,
        "closing_reason": closing_reason,
    }


def save_to_redis(
    valid_lessons: List[dict],
    valid_group_ids: Set[int],
    summary: dict,
):
    """Записывает все данные в Redis при успехе"""
    redis_client = RedisClientManager.get_client("scrapy")

    scraped_groups = {str(gid): "" for gid in valid_group_ids}

    redis_client.set(KeyEnum.SCRAPED_LESSONS, orjson.dumps(valid_lessons))
    redis_client.set(KeyEnum.SCRAPED_GROUPS, orjson.dumps(scraped_groups))
    redis_client.set(KeyEnum.UNCHANGED_GROUPS, orjson.dumps([]))
    redis_client.set(KeyEnum.MAIN_PAGE_HASH, "google-sheets-dummy-hash", ex=259200)
    redis_client.set(KeyEnum.SCRAPY_SUMMARY, orjson.dumps(summary))


def _save_summary_only(summary: dict):
    """Записывает только summary (при ошибке)"""
    try:
        redis_client = RedisClientManager.get_client("scrapy")
        redis_client.set(KeyEnum.SCRAPY_SUMMARY, orjson.dumps(summary))
    except Exception as e:
        logger.warning("Не удалось сохранить отчёт об ошибке импорта",
                       extra={"event": "schedule.import.report_failed", **safe_error_context(e)})


@shared_task(queue="periodic_tasks")
def process_google_schedule(
    lessons_pattern: str = "schedule_from_google_*.csv",
    groups_pattern: str = "groups_from_google_*.txt"
):
    started = perf_counter()
    stats = {}
    stage = "find_files"
    logger.info("Начинается импорт расписания из Google-файлов",
                extra={"event": "schedule.import.started"})
    summary = {
        "total_groups": 0,
        "parsed": 0,
        "skipped": 0,
        "no_change": 0,
        "errors": 0,
        "error_groups": [],
        "total_lessons": 0,
        "closing_reason": "google_sheets_started",
    }

    try:
        # 1. Находим файлы
        lessons_path = get_latest_file_by_pattern(DATA_DIR, lessons_pattern)
        if not lessons_path:
            raise GoogleScheduleError("lessons_file_missing")

        groups_path = get_latest_file_by_pattern(DATA_DIR, groups_pattern)
        if not groups_path:
            raise GoogleScheduleError("groups_file_missing")

        # 2. Загружаем маппинги
        stage = "load_mappings"
        group_map = load_group_map()
        summary["total_groups"] = len(group_map)

        teacher_map = load_teacher_map()

        # 3. Читаем все группы из txt
        stage = "read_groups"
        processed_group_ids, skipped = load_processed_groups(groups_path, group_map, stats=stats)
        summary["skipped"] += skipped

        if not processed_group_ids:
            raise GoogleScheduleError("no_matching_groups")

        # 4. Обрабатываем уроки
        stage = "read_lessons"
        all_raw_lessons, failed_group_ids = process_lessons_csv(
            lessons_path, group_map, teacher_map, stats=stats
        )

        valid_lessons = [l for l in all_raw_lessons if l["group_id"] not in failed_group_ids]
        valid_group_ids = processed_group_ids - failed_group_ids

        summary.update({
            "parsed": len(valid_group_ids),
            "errors": len(failed_group_ids),
            "error_groups": [str(gid) for gid in sorted(failed_group_ids)],
            "total_lessons": len(valid_lessons),
        })

        if not valid_group_ids:
            raise GoogleScheduleError("no_valid_groups")

        # 5. Запись в Redis
        stage = "save_redis"
        outcome = "partial" if (failed_group_ids or skipped or stats["skipped_count"] or stats["invalid_count"]) else "success"
        summary["closing_reason"] = f"google_sheets_finished_{outcome}"
        save_to_redis(valid_lessons, valid_group_ids, summary)

        logger.log(
            logging.WARNING if outcome == "partial" else logging.INFO,
            "Импорт %s: прочитано строк %s, принято занятий %s; групп принято %s, с ошибками %s; "
            "неизвестных строк групп в TXT %s, неизвестных групп в строках CSV %s, некорректных строк CSV %s",
            "завершён частично" if outcome == "partial" else "завершён",
            stats["rows_count"], len(valid_lessons), len(valid_group_ids), len(failed_group_ids),
            skipped, stats["skipped_count"], stats["invalid_count"],
            extra={"event": "schedule.import.completed", "outcome": outcome,
                   "rows_count": stats["rows_count"], "lessons_count": len(valid_lessons),
                   "groups_count": len(valid_group_ids), "failed_count": len(failed_group_ids),
                   "skipped_count": stats["skipped_count"], "invalid_count": stats["invalid_count"],
                   "unmatched_count": skipped, "duration_ms": round((perf_counter() - started) * 1000, 3)},
        )

        return {
            "status": outcome,
            "lessons": len(valid_lessons),
            "groups_processed": len(processed_group_ids),
            "groups_valid": len(valid_group_ids),
            "groups_failed": len(failed_group_ids),
        }

    except Exception as e:
        reasons = {
            "lessons_file_missing": "не найден CSV-файл занятий",
            "groups_file_missing": "не найден TXT-файл групп",
            "no_matching_groups": "ни одна группа из TXT не сопоставлена с БД",
            "no_valid_groups": "не осталось групп без ошибок",
            "invalid_csv_header": "в CSV отсутствуют обязательные колонки",
        }
        reason = str(e) if isinstance(e, GoogleScheduleError) and str(e) in reasons else "unexpected_error"
        summary["closing_reason"] = f"google_sheets_error:{reason}"
        summary["errors"] = max(summary["errors"], 1)
        _save_summary_only(summary)
        logger.error(
            "Импорт расписания остановлен: %s", reasons.get(reason, "сбой чтения, обработки или сохранения данных"),
            extra={"event": "schedule.import.failed", "outcome": "failed", "stage": stage,
                   "reason": reason, "duration_ms": round((perf_counter() - started) * 1000, 3),
                   **safe_error_context(e)},
        )
        # A returned error dict would let Celery run sync against stale Redis data.
        raise
