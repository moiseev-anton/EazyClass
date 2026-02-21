import csv
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import orjson
from celery import shared_task

from scheduler.models import Classroom, Group, Subject, Teacher
from utils import RedisClientManager
from enums import Defaults, KeyEnum

logger = logging.getLogger(__name__)


MAX_SUBJECT_TITLE_LENGTH = Subject._meta.get_field("title").max_length
MAX_TEACHER_FULLNAME_LENGTH = Teacher._meta.get_field("full_name").max_length
MAX_CLASSROOM_TITLE_LENGTH = Classroom._meta.get_field("title").max_length


DATA_DIR = Path("/worker_input")


class GoogleScheduleError(Exception):
    pass


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
    groups_path: Path, group_map: Dict[str, int]
) -> Tuple[Set[int], int]:
    """Читает файл групп и возвращает set id + количество пропущенных"""
    processed_group_ids = set()
    skipped = 0

    with open(groups_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            title = line.strip()
            normalized_title = normalize_group_name(title)
            if normalized_title:
                group_id = group_map.get(normalized_title)
                if group_id:
                    processed_group_ids.add(group_id)
                else:
                    logger.warning(f"Группа из txt (строка {line_num}) не найдена в БД: {title}")
                    skipped += 1

    return processed_group_ids, skipped


def process_lessons_csv(
    lessons_path: Path,
    group_map: Dict[str, int],
    teacher_map: Dict[str, str],
    processed_group_ids: Set[int],
) -> Tuple[List[dict], Set[int]]:
    """Читает CSV с уроками, возвращает валидные уроки и failed-группы"""
    all_raw_lessons = []
    failed_group_ids = set()

    with open(lessons_path, encoding="utf-8-sig") as f:
        # Определяем разделитель
        first_line = f.readline().strip()
        delimiter = ';' if ';' in first_line and ',' not in first_line else ','
        f.seek(0)

        reader = csv.DictReader(f, delimiter=delimiter)

        for row_num, row in enumerate(reader, 1):
            try:
                group_title = row.get("group", "").strip()
                normalized_title = normalize_group_name(group_title)
                group_id = group_map.get(normalized_title)

                if not group_id:
                    logger.warning(f"Строка {row_num}: группа '{group_title}' не найдена в БД")
                    continue

                teacher_short = (row.get("teacher") or "").strip()
                teacher_full = teacher_map.get(teacher_short, teacher_short)

                lesson = {
                    "group_id": group_id,
                    "period": {
                        "lesson_number": int(row["lesson_number"]),
                        "date": row["date"].strip(),
                    },
                    "subject": {
                        "title": (row.get("subject") or Defaults.SUBJECT_TITLE).strip()[
                            :MAX_SUBJECT_TITLE_LENGTH
                        ],
                    },
                    "classroom": {
                        "title": (
                            (row.get("cabinet") or row.get("classroom") or "").strip()[
                                :MAX_CLASSROOM_TITLE_LENGTH
                            ]
                            or Defaults.CLASSROOM
                        ),
                    },
                    "teacher": {
                        "full_name": teacher_full[:MAX_TEACHER_FULLNAME_LENGTH]
                        or Defaults.TEACHER_NAME
                    },
                    "subgroup": str(int(row.get("subgroup", Defaults.SUBGROUP))),
                }

                all_raw_lessons.append(lesson)

            except Exception as e:
                logger.warning(
                    f"Ошибка строки {row_num}: {e} | raw: {row.get('raw_cell', '')[:120]}"
                )
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
        logger.error(f"Не удалось сохранить summary: {e}")


@shared_task(queue="periodic_tasks")
def process_google_schedule(
    lessons_pattern: str = "schedule_from_google_*.csv",
    groups_pattern: str = "groups_from_google_*.txt"
):
    redis_client = RedisClientManager.get_client("scrapy")
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
            raise GoogleScheduleError(f"Не найден файл уроков: {lessons_pattern}")

        groups_path = get_latest_file_by_pattern(DATA_DIR, groups_pattern)
        if not groups_path:
            raise GoogleScheduleError(f"Не найден файл групп: {groups_pattern}")

        # 2. Загружаем маппинги
        group_map = load_group_map()
        summary["total_groups"] = len(group_map)

        teacher_map = load_teacher_map()

        # 3. Читаем все группы из txt
        processed_group_ids, skipped = load_processed_groups(groups_path, group_map)
        summary["skipped"] += skipped

        if not processed_group_ids:
            raise GoogleScheduleError("Ни одна группа из txt не сопоставлена с БД")

        # 4. Обрабатываем уроки
        all_raw_lessons, failed_group_ids = process_lessons_csv(
            lessons_path, group_map, teacher_map, processed_group_ids
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
            raise GoogleScheduleError("После фильтрации не осталось успешных групп")

        # 5. Запись в Redis
        summary["closing_reason"] = "google_sheets_finished_success"
        save_to_redis(valid_lessons, valid_group_ids, summary)

        logger.info(
            f"Успех: {len(valid_lessons)} уроков | "
            f"{len(valid_group_ids)} групп | "
            f"{len(failed_group_ids)} failed"
        )

        return {
            "status": "success",
            "lessons": len(valid_lessons),
            "groups_processed": len(processed_group_ids),
            "groups_valid": len(valid_group_ids),
            "groups_failed": len(failed_group_ids),
        }

    except GoogleScheduleError as ge:
        summary["closing_reason"] = f"google_sheets_error: {str(ge)}"
        summary["errors"] = 1
        _save_summary_only(summary)
        logger.error(f"Ошибка: {ge}")
        return {"status": "error", "reason": str(ge)}

    except Exception as e:
        summary["closing_reason"] = f"google_sheets_unexpected_error: {str(e)}"
        summary["errors"] = 1
        _save_summary_only(summary)
        logger.exception("Критическая ошибка")
        return {"status": "critical_error", "reason": str(e)}
