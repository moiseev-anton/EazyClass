import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from django.db import transaction

from ..models import Teacher, Classroom, Subject, Lesson

DELETE_INACTIVE_PERIOD = timedelta(days=365)
UPDATE_ACTIVE_PERIOD = timedelta(weeks=1)

logger = logging.getLogger(__name__)


@shared_task(queue='periodic_tasks')
def update_last_active_records():
    """
    Обновляет поле `last_active` для учителей, кабинетов и предметов,
    которые были использованы в уроках за последнюю неделю.
    """
    start_date = timezone.now() - UPDATE_ACTIVE_PERIOD
    current_time = timezone.now()

    # Идентификация активных объектов по урокам за последнюю неделю
    active_lessons = Lesson.objects.filter(date__gte=start_date)
    active_teachers = set(active_lessons.values_list('teacher_id', flat=True))
    active_classrooms = set(active_lessons.values_list('classroom_id', flat=True))
    active_subjects = set(active_lessons.values_list('subject_id', flat=True))

    # Обновление поля last_active для активных записей в транзакции
    with transaction.atomic():
        Teacher.objects.filter(id__in=active_teachers).update(last_active=current_time)
        Classroom.objects.filter(id__in=active_classrooms).update(last_active=current_time)
        Subject.objects.filter(id__in=active_subjects).update(last_active=current_time)
        logger.info(f"Обновлено last_active для {len(active_teachers)} учителей,"
                    f" {len(active_classrooms)} кабинетов,"
                    f" {len(active_subjects)} предметов.")


@shared_task
def delete_inactive_records():
    """Удаляет записи учителей, кабинетов и предметов, которые не использовались более года."""
    one_year_ago = timezone.now() - DELETE_INACTIVE_PERIOD

    with transaction.atomic():
        # Удаление записей, неактивных более года
        deleted_teachers_count, _ = Teacher.objects.filter(last_active__lt=one_year_ago).delete()
        deleted_classrooms_count, _ = Classroom.objects.filter(last_active__lt=one_year_ago).delete()
        deleted_subjects_count, _ = Subject.objects.filter(last_active__lt=one_year_ago).delete()
        logger.info(f"Удалено {deleted_teachers_count} учителей,"
                    f" {deleted_classrooms_count} кабинетов,"
                    f" {deleted_subjects_count} предметов.")
