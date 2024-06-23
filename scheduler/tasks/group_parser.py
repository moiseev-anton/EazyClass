import logging
from datetime import timedelta

from bs4 import BeautifulSoup
from celery import shared_task
from django.db import transaction, DatabaseError
from django.db.models import Model, Max
from .schedule_parser import fetch_response_from_url
from django.utils import timezone

from ..models import Faculty, Group

MAIN_URL = 'https://bincol.ru/rasp/'
GROUPS_PAGE_LINK = 'grupp.php'
DEACTIVATE_PERIOD = timedelta(days=1)

logger = logging.getLogger(__name__)


def save_or_update_group(grop_data: dict):
    existing_group = Group.objects.filter(
        title=grop_data['title'],
        link=grop_data['link'],
        is_active=True
    ).first()

    if existing_group:
        existing_group.updated_at = timezone.now()
        existing_group.save(update_fields=['updated_at'])
        logger.debug(f"Группа обновлена: {existing_group.title}")
    else:
        Group(**grop_data).save()
        logger.debug(f"Группа создана: {grop_data['title']}")


def parse_faculty_block(block):
    """Парсит блок информации о факультете и возвращает экземпляр факультета и его группы."""
    try:
        faculty_name = block.text.strip().split(' ', 1)[1]
        faculty, created = Faculty.objects.get_or_create(title=faculty_name)
        logger.debug(f"Факультет {'создан' if created else 'обновлен'}: {faculty.title}")

        groups = block.find_next_sibling('p').find_all('a')
        for group in groups:
            group_data = {
                'title': group.text,
                'grade': group.text[0] or '',
                'link': group['href'],
                'faculty': faculty
            }
            save_or_update_group(group_data)

        if created:
            faculty.calculate_short_title()
        else:
            faculty.updated_at = timezone.now()
            faculty.is_active = True
            faculty.save(update_fields=['updated_at', 'is_active'])

    except Exception as e:
        logger.error(f"Ошибка при парсинге блока факультета: {e}")
        raise


def parse_group_list():
    """Парсит список групп и возвращает данные о группах."""
    url = f'{MAIN_URL}{GROUPS_PAGE_LINK}'
    try:
        response = fetch_response_from_url(url)
        soup = BeautifulSoup(response.content, 'lxml')
        faculty_blocks = soup.find_all('p', class_='shadow')

        for block in faculty_blocks:
            parse_faculty_block(block)

    except Exception as e:
        logger.error(f"Ошибка при парсинге списка групп: {e}")
        raise


def deactivate_old_records(model: Model, delta: timedelta):
    """Деактивирует записи, которые не обновлялись в течение заданного временного интервала."""
    try:
        latest_update = model.objects.aggregate(latest=Max('updated_at'))['latest']
        if latest_update:
            threshold_date = latest_update - delta
            model.objects.filter(updated_at__lt=threshold_date, is_active=True).update(is_active=False)
    except DatabaseError as e:
        logger.error(f"Ошибка при деактивации старых записей для модели {model.__name__}: {e}")
        raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue='periodic_tasks')
def update_groups(self):
    try:
        with transaction.atomic():
            parse_group_list()
            deactivate_old_records(Faculty, DEACTIVATE_PERIOD)
            deactivate_old_records(Group, DEACTIVATE_PERIOD)
    except Exception as e:

        logger.error(f"Ошибка при обновлении групп: {e}")
        raise self.retry(exc=e)


def deactivate_all_records(model: Model):
    """Деактивирует все записи в таблице."""
    try:
        model.objects.filter(is_active=True).update(is_active=False)
    except DatabaseError as e:
        logger.error(f"Ошибка при деактивации всех записей {model.__name__}: {e}")
        raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue='periodic_tasks')
def deactivate_all_groups():
    with transaction.atomic():
        deactivate_all_records(Group)
        deactivate_all_records(Faculty)
