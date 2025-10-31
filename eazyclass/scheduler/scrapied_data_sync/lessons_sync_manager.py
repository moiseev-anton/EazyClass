import logging
import pickle
from datetime import date
from typing import Any, Dict, List, Optional

from bulk_sync import bulk_compare
from django.db import transaction
from django.utils import timezone

from scheduler.models import Classroom, Lesson, Period, Subject, Teacher
from scheduler.scrapied_data_sync.related_objects_map import RelatedObjectsMap
from scrapy_app.spiders import (
    PAGE_HASH_KEY_PREFIX,
    SCRAPED_GROUPS_KEY,
    SCRAPED_LESSONS_KEY,
)
from utils import RedisClientManager

logger = logging.getLogger(__name__)

SCHEDULE_CHANGES_KEY = "schedule_changes"
ComparisonSummary = Dict[str, List[Dict[str, Any]]]


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

        self._last_scraped_groups: dict[int, str] | None = None
        self._last_scraped_lessons: list[dict[str, Any]] | None = None

    def update_schedule(self) -> ComparisonSummary:
        """Основной пайплайн: fetch → process → apply → serialize."""
        scraped_groups, lesson_items = self._fetch_data()

        if not scraped_groups:
            logger.info("Перечень групп пуст.")
            return self.EMPTY_SUMMARY

        new_lessons = self._process_lessons(lesson_items, scraped_groups)
        comparison_result = self._compare_lessons(new_lessons, scraped_groups)
        self._apply_db_changes(comparison_result)
        serialized_summary = self._serialize_summary(comparison_result)
        self._save_to_redis(scraped_groups)

        return serialized_summary

    def _fetch_data(self) -> tuple[Dict[int, str], List[Dict[str, Any]]]:
        """Получает данные из Redis и десериализует их."""
        lessons_pickle = self.redis_client.get(SCRAPED_LESSONS_KEY)
        groups_pickle = self.redis_client.get(SCRAPED_GROUPS_KEY)
        if not lessons_pickle or not groups_pickle:
            raise ValueError("Данные для обработки отсутствуют в Redis")

        lesson_items = pickle.loads(lessons_pickle)  # [{lesson_dict},...]
        scraped_groups = pickle.loads(groups_pickle)  # {group_id: last_content_hash}
        logger.info("Данные скрайпинга загружены из Redis")

        self._last_scraped_groups = scraped_groups
        self._last_lessons = lesson_items

        return scraped_groups, lesson_items

    def _process_lessons(
        self, lesson_items: List[Dict[str, Any]], scraped_groups: Dict[int, str]
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
            if (
                item["group_id"] in scraped_groups
                and item["period"]["date"] >= self.start_sync_day
            ):
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
        self, new_lessons: List[Lesson], scraped_groups: Dict[int, str]
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

    def _save_to_redis(self, scraped_groups: Dict[int, str]) -> None:
        """Save page hashes"""
        try:
            with self.redis_client.pipeline() as pipe:
                for group_id, page_hash in scraped_groups.items():
                    pipe.setex(
                        f"{PAGE_HASH_KEY_PREFIX}{group_id}",
                        self.PAGE_HASH_TIMEOUT,
                        page_hash,
                    )
                pipe.execute()
            logger.info(f"Хеши страниц сохранены для {len(scraped_groups)} групп")
        except Exception as e:
            logger.warning(
                f"Не удалось сохранить хеши страниц в Redis: {e}", exc_info=True
            )

    @staticmethod
    def _serialize_summary(
        comparison_result: Dict[str, List[Lesson]],
    ) -> ComparisonSummary:
        serialized = {
            key: [lesson.to_dict() for lesson in lessons]
            for key, lessons in comparison_result.items()
        }
        return serialized

    @property
    def fetched_data_summary(self):
        lessons_count = len(self._last_scraped_lessons) if self._last_scraped_lessons else 0
        groups_count = len(self._last_scraped_groups) if self._last_scraped_groups else 0

        return {
            "lessons_count": lessons_count,
            "groups_count": groups_count,
        }
