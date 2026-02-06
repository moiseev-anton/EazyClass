import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Set

import orjson
import redis
from bulk_sync import bulk_compare
from django.db import transaction
from django.utils import timezone

from scheduler.fetched_data_sync.lessons.related_objects_map import RelatedObjectsMap
from scheduler.models import Classroom, Lesson, Period, Subject, Teacher
from utils import KeyEnum, RedisClientManager

logger = logging.getLogger(__name__)

ComparisonSummary = Dict[str, List[Dict[str, Any]]]


@dataclass(frozen=True)
class ScrapyFetchResult:
    scraped_groups: Dict[str, str]
    lesson_items: List[Dict[str, Any]]
    unchanged_groups: Set[str]


class LessonsSyncManager:
    PAGE_HASH_TIMEOUT: int = 86400  # 24h
    SCHEDULE_CHANGES_TIMEOUT: int = 3600  # 1h
    BATCH_SIZE: int = 1000  # Для bulk ops

    COMPARISON_FIELDS: List[str] = ["group_id", "period_id", "subgroup"]
    COMPARISON_IGNORE_FIELDS: List[str] = ["updated_at", "created_at"]
    UPDATE_FIELDS: List[str] = [
        "subject_id",
        "classroom_id",
        "teacher_id",
        "updated_at",
    ]

    EMPTY_SUMMARY: ComparisonSummary = {"added": [], "updated": [], "removed": []}

    def __init__(self, redis_client=None, start_sync_day: Optional[date] = None):
        self.redis_client = redis_client or RedisClientManager.get_client("scrapy")
        self.start_sync_day = start_sync_day or date.today()

    def update_schedule(self) -> ComparisonSummary:
        """Основной пайплайн: fetch → process → apply → serialize."""
        data = self._fetch_data()

        if not data.scraped_groups:
            logger.info("Перечень групп пуст.")
            return self.EMPTY_SUMMARY

        new_lessons = self._process_lessons(data.lesson_items, data.scraped_groups)
        comparison_result = self._compare_lessons(new_lessons, data.scraped_groups)
        self._apply_db_changes(comparison_result)
        serialized_summary = self._serialize_summary(comparison_result)
        self._save_to_redis(data.scraped_groups, data.unchanged_groups)

        return serialized_summary

    def _fetch_data(self) -> ScrapyFetchResult:
        lessons_json = self.redis_client.get(KeyEnum.SCRAPED_LESSONS)
        groups_json = self.redis_client.get(KeyEnum.SCRAPED_GROUPS)
        unchanged_json = self.redis_client.get(KeyEnum.UNCHANGED_GROUPS)

        if not lessons_json or not groups_json:
            raise ValueError("Данные для обработки отсутствуют в Redis")

        lesson_items = orjson.loads(lessons_json)
        scraped_groups = orjson.loads(groups_json)
        unchanged_groups = set(orjson.loads(unchanged_json) or [])

        logger.info("Данные скрайпинга загружены из Redis")

        lesson_items = self._normalize_lessons_dates(lesson_items)

        return ScrapyFetchResult(
            scraped_groups=scraped_groups,
            lesson_items=lesson_items,
            unchanged_groups=unchanged_groups,
        )

    def _process_lessons(
        self, lesson_items: List[Dict[str, Any]], scraped_groups: Dict[str, str]
    ) -> List[Lesson]:
        """Process: gather → map → create. Returns new_lessons и mappers (for reuse if needed)."""
        teachers = RelatedObjectsMap(Teacher, ("full_name",))
        classrooms = RelatedObjectsMap(Classroom, ("title",))
        subjects = RelatedObjectsMap(Subject, ("title",))
        periods = RelatedObjectsMap(Period, ("date", "lesson_number"))

        for item in lesson_items:
            teachers.add(item["teacher"])
            classrooms.add(item["classroom"])
            subjects.add(item["subject"])
            periods.add(item["period"])

        logger.info(
            f"Собраны уникальные элементы для маппинга: "
            f"периодов={len(periods.pending_keys)}, "
            f"учителей={len(teachers.pending_keys)}, "
            f"предметов={len(subjects.pending_keys)}, "
            f"кабинетов={len(classrooms.pending_keys)}"
        )

        # Map IDs (bulk resolve)
        teachers.resolve_pending_keys()
        classrooms.resolve_pending_keys()
        subjects.resolve_pending_keys()
        periods.resolve_pending_keys()

        logger.info(
            f"Маппинг уникальных элементов завершен: "
            f"id периодов={len(periods.existing_mappings)}, "
            f"id учителей={len(teachers.existing_mappings)}, "
            f"id предметов={len(subjects.existing_mappings)}, "
            f"id кабинетов={len(classrooms.existing_mappings)}"
        )

        update_time = timezone.now()
        new_lessons = []
        for item in lesson_items:
            if str(item["group_id"]) in scraped_groups and item["period"]["date"] >= self.start_sync_day:
                lesson = Lesson(
                    group_id=item["group_id"],
                    subgroup=item["subgroup"],
                    period_id=periods.get_or_map_id(item["period"]),
                    teacher_id=teachers.get_or_map_id(item["teacher"]),
                    classroom_id=classrooms.get_or_map_id(item["classroom"]),
                    subject_id=subjects.get_or_map_id(item["subject"]),
                    updated_at=update_time,
                )
                new_lessons.append(lesson)

        logger.debug(f"Собрали {len(new_lessons)} объектов уроков")
        return new_lessons

    def _compare_lessons(
        self, new_lessons: List[Lesson], scraped_groups: Dict[str, str]
    ) -> Dict[str, List[Lesson]]:
        """Compare: filter existing + bulk_compare."""
        periods = Period.objects.filter(date__gte=self.start_sync_day)
        groups = scraped_groups.keys()
        existing_lessons = Lesson.objects.filter(
            period__in=periods, group__in=groups, is_active=True
        )

        raw_result = bulk_compare(
            new_models=new_lessons,
            old_models=existing_lessons,
            key_fields=self.COMPARISON_FIELDS,
            ignore_fields=self.COMPARISON_IGNORE_FIELDS,
        )

        return {
            "added": raw_result["added"],
            "updated": raw_result["updated"],
            "removed": list(raw_result["removed"]),
        }

    @transaction.atomic
    def _apply_db_changes(self, comparison_result: Dict[str, List[Lesson]]) -> None:
        """Apply: delete/update/create in batches."""
        if not comparison_result:
            logger.warning("Нет данных для синхронизации")
            return

        to_delete = [l.id for l in comparison_result["removed"] if l.id]
        to_update = comparison_result["updated"]
        to_create = comparison_result["added"]

        logger.info(
            f"Изменения по урокам: "
            f"для удаления={len(to_delete)}, "
            f"для обновления={len(to_update)}, "
            f"для создания={len(to_create)}"
        )

        if to_delete:
            Lesson.objects.filter(id__in=to_delete).delete()
        if to_update:
            Lesson.objects.bulk_update(
                to_update, fields=self.UPDATE_FIELDS, batch_size=self.BATCH_SIZE
            )
        if to_create:
            Lesson.objects.bulk_create(
                to_create, batch_size=self.BATCH_SIZE, ignore_conflicts=False
            )
        logger.info("Изменения отражены в БД.")

    def _save_to_redis(self, scraped_groups: Dict[str, str], unchanged_groups: Set[str]) -> None:
        self._save_page_hashes(scraped_groups)
        self._update_synced_groups_set(scraped_groups, unchanged_groups)

    def _save_page_hashes(self, scraped_groups: Dict[str, str]) -> None:
        """Сохраняет хеши страниц успешно обработанных групп"""
        try:
            with self.redis_client.pipeline() as pipe:
                for group_id, page_hash in scraped_groups.items():
                    pipe.setex(
                        f"{KeyEnum.PAGE_HASH_PREFIX}{group_id}",
                        self.PAGE_HASH_TIMEOUT,
                        page_hash,
                    )
                pipe.execute()
            logger.info(f"Хеши страниц сохранены для {len(scraped_groups)} групп")
        except Exception as e:
            logger.warning(f"Не удалось сохранить хеши страниц в Redis: {e}", exc_info=True)

    def _update_synced_groups_set(self, scraped_groups: Dict[str, str], unchanged_groups: Set[str]) -> None:
        """Добавляет успешно обработанные группы в set по хешу главной страницы"""
        main_hash = self.redis_client.get(KeyEnum.MAIN_PAGE_HASH)

        if not main_hash:
            logger.info("Хеш главной страницы отсутствует → множество не обновляется")
            return

        set_key = f"{KeyEnum.SYNCED_GROUPS_PREFIX}{main_hash}"
        successfully_synced_ids = {group_id for group_id in scraped_groups.keys()} | unchanged_groups

        try:
            added = self.redis_client.sadd(set_key, *successfully_synced_ids)
            self.redis_client.expire(set_key, self.PAGE_HASH_TIMEOUT)

            total_now = self.redis_client.scard(set_key)
            logger.info(
                f"Множество {set_key} обновлено: добавлено {added} новых, всего теперь {total_now}"
            )
        except redis.RedisError as e:
            logger.warning(f"Не удалось обновить множество синхронизированных групп {set_key}: {e}")

    @staticmethod
    def _serialize_summary(
        comparison_result: Dict[str, List[Lesson]],
    ) -> ComparisonSummary:
        serialized = {
            key: [lesson.to_dict() for lesson in lessons]
            for key, lessons in comparison_result.items()
        }
        return serialized

    @staticmethod
    def _normalize_lessons_dates(lesson_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Преобразует строки дат в date-объекты в уроках.
        Использует кэш для уникальных строк дат.
        """
        date_cache: Dict[str, date] = {}  # {date_str: date_obj}

        for item in lesson_items:
            date_str = item["period"]["date"]
            if date_str not in date_cache:
                date_cache[date_str] = date.fromisoformat(date_str)
            item["period"]["date"] = date_cache[date_str]

        return lesson_items
