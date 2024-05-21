import logging
from datetime import timedelta

import requests
from bs4 import BeautifulSoup
from celery import shared_task
from django.db import transaction, DatabaseError
from django.db.models import Model, Max
from .schedule_parser import fetch_response_from_url

from ..models import Faculty, Group

MAIN_URL = 'https://bincol.ru/rasp/'
GROUPS_PAGE_LINK = 'grupp.php'
DEACTIVATE_PERIOD = timedelta(days=1)

logger = logging.getLogger(__name__)


def parse_faculty_block(block):
    """Парсит блок информации о факультете и возвращает экземпляр факультета и его группы."""
    try:
        faculty_name = block.text.strip().split(' ', 1)[1]
        faculty, created = Faculty.objects.get_or_create(title=faculty_name)
        logger.debug(f"Факультет {'создан' if created else 'обновлен'}: {faculty.title}")

        groups = block.find_next_sibling('p').find_all('a')
        group_data = []
        for group in groups:
            group_name = group.text
            group_url = group['href']
            group_grade = group_name[0] if group_name else ''
            group_data.append({
                'title': group_name,
                'link': group_url,
                'grade': group_grade,
                'faculty': faculty,
            })
        return faculty, group_data
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

        all_group_data = []
        for block in faculty_blocks:
            faculty, group_data = parse_faculty_block(block)
            all_group_data.extend(group_data)
            faculty.calculate_short_title()

        return all_group_data
    except Exception as e:
        logger.error(f"Ошибка при парсинге списка групп: {e}")
        raise


def save_groups(group_data):
    """Сохраняет или обновляет информацию о группах в базе данных."""
    try:
        for data in group_data:
            group, created = Group.objects.update_or_create(
                title=data['title'],
                defaults={
                    'link': data['link'],
                    'grade': data['grade'],
                    'faculty': data['faculty'],
                }
            )
            logger.debug(f"Группа {'создана' if created else 'обновлена'}: {group.title}")
    except DatabaseError as e:
        logger.error(f"Ошибка при сохранении данных группы: {e}")
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


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def update_groups(self):
    try:
        with transaction.atomic():
            group_data = parse_group_list()
            save_groups(group_data)
            deactivate_old_records(Faculty, DEACTIVATE_PERIOD)
            deactivate_old_records(Group, DEACTIVATE_PERIOD)
    except Exception as e:

        logger.error(f"Ошибка при обновлении групп: {e}")
        raise self.retry(exc=e)
