import logging
from collections import defaultdict
from datetime import datetime

from django.db import connection
from django.db import transaction

from scheduler.models import LessonBuffer

logger = logging.getLogger(__name__)


class ScheduleDataSaver:
    def __init__(self):
        self.today = datetime.now().date()

    def save_lessons(self):
        try:
            with transaction.atomic():
                LessonBuffer.objects.bulk_create(self.lesson_model_objects)
                synchronize_lessons(self.scraped_groups)
                LessonBuffer.objects.all().delete()
            logger.info(f"Данные обновлены для {len(self.scraped_groups)} групп")
        except Exception as e:
            logger.error(f"Ошибка при обновлении данных в БД: {str(e)}")
            raise


def synchronize_lessons(group_ids):
    today = datetime.now().date()
    affected_entities_map = {
        'Group': defaultdict(set),
        'Teacher': defaultdict(set)
    }

    try:
        with connection.cursor() as cursor:
            # Проверка наличия данных в буфере
            cursor.execute("SELECT COUNT(*) FROM scheduler_lessonbuffer")
            if cursor.fetchone()[0] == 0:
                logger.info("Буфер пуст. Пропуск вставки и обновления уроков.")
            else:
                # Обновление измененных уроков
                cursor.execute("""
                WITH updated AS (
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
                    RETURNING l.group_id, l.teacher_id, lb.period_id
                )
                SELECT u.group_id, u.teacher_id, lt.date
                FROM updated u
                JOIN scheduler_period lt ON u.period_id = lt.id
                """)
                for group_id, teacher_id, date in cursor.fetchall():
                    affected_entities_map['Group'][group_id].add(date)
                    affected_entities_map['Teacher'][teacher_id].add(date)
                logger.info(f"Обновление измененных уроков завершено успешно: {cursor.rowcount} шт.")

                # Вставка новых уроков из буфера
                cursor.execute("""
                WITH inserted AS (
                    INSERT INTO scheduler_lesson (group_id, period_id, subject_id, classroom_id, teacher_id,
                        subgroup, is_active)
                    SELECT lb.group_id, lb.period_id, lb.subject_id, lb.classroom_id, 
                        lb.teacher_id, lb.subgroup, true
                    FROM scheduler_lesson_buffer lb
                    WHERE NOT EXISTS (
                        SELECT 1 FROM scheduler_lesson l
                        WHERE l.group_id = lb.group_id AND l.period_id = lb.period_id
                    )
                    RETURNING group_id, teacher_id, period_id
                )
                SELECT i.group_id, i.teacher_id, lt.date
                FROM inserted i
                JOIN scheduler_period lt ON i.period_id = lt.id
                """)
                for group_id, teacher_id, date in cursor.fetchall():
                    affected_entities_map['Group'][group_id].add(date)
                    affected_entities_map['Teacher'][teacher_id].add(date)
                logger.info(f"Вставка новых уроков завершена успешно: {cursor.rowcount} шт.")

            # Деактивация отмененных уроков
            cursor.execute("""
            WITH deactivated AS (
                UPDATE scheduler_lesson l
                SET is_active = false
                FROM scheduler_lesson l_sub
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
                RETURNING l.group_id, l.teacher_id, lt.date
            )
            SELECT d.group_id, d.teacher_id, d.date
            FROM deactivated d
            """, [tuple(group_ids), today])
            for group_id, teacher_id, date in cursor.fetchall():
                affected_entities_map['Group'][group_id].add(date)
                affected_entities_map['Teacher'][teacher_id].add(date)
            logger.info(f"Деактивация уроков завершена успешно: {cursor.rowcount} шт.")

    except Exception as e:
        logger.error(f"Ошибка при синхронизации уроков: {e}")
        raise

    return affected_entities_map
