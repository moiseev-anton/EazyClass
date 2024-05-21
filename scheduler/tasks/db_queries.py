import logging
from collections import defaultdict
from datetime import datetime
from django.db import connection, transaction
from ..models import LessonBuffer

logger = logging.getLogger(__name__)


def synchronize_lessons(group_ids):
    today = datetime.now().date()
    affected_groups_dates = defaultdict(set)
    try:
        with connection.cursor() as cursor:
            if not LessonBuffer.objects.exists():
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
                    FROM scheduler_lessonbuffer lb
                    WHERE l.group_id = lb.group_id AND
                          l.lesson_time_id = lb.lesson_time_id AND
                          l.subgroup = lb.subgroup AND
                          (l.subject_id != lb.subject_id OR
                           l.classroom_id != lb.classroom_id OR
                           l.teacher_id != lb.teacher_id)
                    RETURNING l.group_id, l.lesson_time_id
                )
                SELECT u.group_id, lt.date
                FROM updated u
                JOIN scheduler_lessontime lt ON u.lesson_time_id = lt.id;
                """)
                rows = cursor.fetchall()
                for row in rows:
                    affected_groups_dates[row[0]].add(row[1])
                logger.info(f"Обновление измененных уроков завершено успешно: {len(rows)} шт")

                # Вставка новых уроков из буфера
                cursor.execute("""
                WITH inserted AS (
                    INSERT INTO scheduler_lesson (group_id, lesson_time_id, subject_id, classroom_id, teacher_id, subgroup, is_active)
                    SELECT lb.group_id, lb.lesson_time_id, lb.subject_id, lb.classroom_id, lb.teacher_id, lb.subgroup, true
                    FROM scheduler_lessonbuffer lb
                    LEFT JOIN scheduler_lesson l ON lb.group_id = l.group_id AND lb.lesson_time_id = l.lesson_time_id
                    WHERE l.group_id IS NULL AND l.lesson_time_id IS NULL
                    RETURNING group_id, lesson_time_id
                )
                SELECT i.group_id, lt.date
                FROM inserted i
                JOIN scheduler_lessontime lt ON i.lesson_time_id = lt.id;
                """)
                rows = cursor.fetchall()
                for row in rows:
                    affected_groups_dates[row[0]].add(row[1])
                logger.info(f"Вставка новых уроков завершена успешно: {len(rows)} шт")

            # Деактивация отмененных уроков
            cursor.execute("""
            WITH deactivated AS (
                UPDATE scheduler_lesson l
                SET is_active = false
                FROM scheduler_lesson l_sub
                JOIN scheduler_lessontime lt ON l_sub.lesson_time_id = lt.id
                LEFT JOIN scheduler_lessonbuffer lb ON l_sub.group_id = lb.group_id AND l_sub.lesson_time_id = lb.lesson_time_id
                WHERE l_sub.group_id = l.group_id AND l_sub.lesson_time_id = l.lesson_time_id
                AND l_sub.group_id IN %s AND lt.date >= %s AND lb.group_id IS NULL AND lb.lesson_time_id IS NULL
                RETURNING l.group_id, l.lesson_time_id
            )
            SELECT d.group_id, lt.date
            FROM deactivated d
            JOIN scheduler_lessontime lt ON d.lesson_time_id = lt.id;
            """, [tuple(group_ids), today])
            rows = cursor.fetchall()
            for row in rows:
                affected_groups_dates[row[0]].add(row[1])
            logger.info(f"Деактивация уроков завершена успешно: {len(rows)} шт")

    except Exception as e:
        logger.error(f"Ошибка при синхронизации буфера уроков: {e}")
        raise

    return affected_groups_dates
