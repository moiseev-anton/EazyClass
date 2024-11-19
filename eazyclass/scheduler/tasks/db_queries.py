import logging
from collections import defaultdict
from datetime import datetime

from django.core.cache import caches
from django.db import connection
from eazyclass.telegrambot import ContentTypeService

logger = logging.getLogger(__name__)
cache = caches['telegrambot_cache']

CACHE_TIMEOUT = 86400  # 24 часа


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
                    FROM scheduler_lessonbuffer lb
                    WHERE l.group_id = lb.group_id AND
                          l.lesson_time_id = lb.lesson_time_id AND
                          l.subgroup = lb.subgroup AND
                          (l.subject_id != lb.subject_id OR
                           l.classroom_id != lb.classroom_id OR
                           l.teacher_id != lb.teacher_id)
                    RETURNING l.group_id, l.teacher_id, lb.lesson_time_id
                )
                SELECT u.group_id, u.teacher_id, lt.date
                FROM updated u
                JOIN scheduler_lessontime lt ON u.lesson_time_id = lt.id
                """)
                for group_id, teacher_id, date in cursor.fetchall():
                    affected_entities_map['Group'][group_id].add(date)
                    affected_entities_map['Teacher'][teacher_id].add(date)
                logger.info(f"Обновление измененных уроков завершено успешно: {cursor.rowcount} шт.")

                # Вставка новых уроков из буфера
                cursor.execute("""
                WITH inserted AS (
                    INSERT INTO scheduler_lesson (group_id, lesson_time_id, subject_id, classroom_id, teacher_id, subgroup, is_active)
                    SELECT lb.group_id, lb.lesson_time_id, lb.subject_id, lb.classroom_id, lb.teacher_id, lb.subgroup, true
                    FROM scheduler_lessonbuffer lb
                    WHERE NOT EXISTS (
                        SELECT 1 FROM scheduler_lesson l
                        WHERE l.group_id = lb.group_id AND l.lesson_time_id = lb.lesson_time_id
                    )
                    RETURNING group_id, teacher_id, lesson_time_id
                )
                SELECT i.group_id, i.teacher_id, lt.date
                FROM inserted i
                JOIN scheduler_lessontime lt ON i.lesson_time_id = lt.id
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
                JOIN scheduler_lessontime lt ON l_sub.lesson_time_id = lt.id
                LEFT JOIN scheduler_lessonbuffer lb ON l_sub.group_id = lb.group_id AND l_sub.lesson_time_id = lb.lesson_time_id
                WHERE l_sub.group_id = l.group_id
                    AND l_sub.lesson_time_id = l.lesson_time_id
                    AND l_sub.group_id IN %s
                    AND lt.date >= %s
                    AND lb.group_id IS NULL
                    AND lb.lesson_time_id IS NULL
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


def fetch_subscribers_for_type(model_name: str, object_ids: list) -> dict:
    content_type_id = ContentTypeService.get_content_type_id(app_label='scheduler', model_name=model_name)
    subscribers = defaultdict(set)

    try:
        with connection.cursor() as cursor:
            # Сбор пользователей, подписанных на затронутые объекты
            if object_ids:
                cursor.execute("""
                    SELECT u.telegram_id, s.object_id
                FROM scheduler_subscriptions s
                JOIN scheduler_user u ON s.user_id = u.id
                WHERE s.content_type_id = %s AND s.object_id IN %s
                      AND u.notify_on_schedule_change = True
                      AND u.is_active = True;
                """, [content_type_id, tuple(object_ids)])
                for user_id, object_id in cursor.fetchall():
                    subscribers[object_id].add(user_id)

        return subscribers

    except Exception as e:
        logger.error(f"Ошибка при получении данных подписчиков: {e}")
        raise


def fetch_all_subscribers(affected_entities_map):
    subscribers_map = defaultdict(dict)
    for model_name, model_map in affected_entities_map.items():
        object_ids = model_map.keys()
        type_subscribers = fetch_subscribers_for_type(model_name, object_ids)
        subscribers_map[model_name] = type_subscribers

    return subscribers_map
