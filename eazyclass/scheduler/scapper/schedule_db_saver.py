import logging
from datetime import datetime
from datetime import date as DateClass

from django.db import connection
from django.db import transaction

from scheduler.models import LessonBuffer, Lesson

logger = logging.getLogger(__name__)


class ScheduleDataSaver:
    def __init__(self, lessons: list[Lesson], group_ids: set[int]):
        self.lessons = lessons
        self.group_ids = tuple(group_ids)

    def save_lessons(self):
        if not self.group_ids:
            logger.info("Нет данных для сохранения. Операция пропущена.")
            return

        try:
            with transaction.atomic():
                LessonBuffer.objects.bulk_create(self.lessons)
                self.synchronize_lessons()
                LessonBuffer.objects.all().delete()
            logger.info(f"Данные успешно обновлены для {len(self.group_ids)} групп.")
        except Exception as e:
            logger.error(f"Ошибка при обновлении данных в БД: {str(e)}")
            raise

    def synchronize_lessons(self):
        try:
            with connection.cursor() as cursor:
                if self.is_buffer_empty(cursor):
                    logger.info("Буфер пуст. Обновление и вставка пропускаятся.")
                else:
                    self.update_existing_lessons(cursor)
                    self.insert_new_lessons(cursor)
                self.delete_outdated_lessons(cursor)
        except Exception as e:
            logger.error(f"Ошибка при синхронизации уроков: {str(e)}")
            raise

    @staticmethod
    def is_buffer_empty(cursor):
        cursor.execute("SELECT COUNT(*) FROM scheduler_lesson_buffer")
        return cursor.fetchone()[0] == 0

    @staticmethod
    def update_existing_lessons(cursor):
        cursor.execute("""
            UPDATE scheduler_lesson l
            SET subject_id = lb.subject_id,
                classroom_id = lb.classroom_id,
                teacher_id = lb.teacher_id,
                subgroup = lb.subgroup,
                is_active = true
            FROM scheduler_lesson_buffer lb
            WHERE l.group_id = lb.group_id AND
                  l.period_id = lb.period_id AND
                  l.subgroup = lb.subgroup AND
                  (l.subject_id != lb.subject_id OR
                   l.classroom_id != lb.classroom_id OR
                   l.teacher_id != lb.teacher_id)
        """)
        logger.info(f"Обновлено уроков: {cursor.rowcount}")

    @staticmethod
    def insert_new_lessons(cursor):
        cursor.execute("""
            INSERT INTO scheduler_lesson (group_id, period_id, subject_id, classroom_id, teacher_id,
                subgroup, is_active)
            SELECT lb.group_id, lb.period_id, lb.subject_id, lb.classroom_id, 
                lb.teacher_id, lb.subgroup, true
            FROM scheduler_lesson_buffer lb
            WHERE NOT EXISTS (
                SELECT 1 FROM scheduler_lesson l
                WHERE l.group_id = lb.group_id AND l.period_id = lb.period_id
            )
        """)
        logger.info(f"Добавлено новых уроков: {cursor.rowcount}.")

    def delete_outdated_lessons(self, cursor):
        cursor.execute("""
            DELETE FROM scheduler_lesson l
            USING scheduler_lesson l_sub
            JOIN scheduler_period lt ON l_sub.period_id = lt.id
            LEFT JOIN scheduler_lesson_buffer lb ON l_sub.group_id = lb.group_id 
                AND l_sub.period_id = lb.period_id
            WHERE l_sub.group_id = l.group_id
                AND l_sub.period_id = l.period_id
                AND l_sub.group_id IN %s
                AND lt.date >= %s
                AND lb.group_id IS NULL
                AND lb.period_id IS NULL
                AND l.is_active = true
        """, [self.group_ids, DateClass.today()])
        logger.info(f"Удалено неактуальных уроков: {cursor.rowcount} шт.")

