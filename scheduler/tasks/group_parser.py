import logging
from datetime import timedelta

import requests
from bs4 import BeautifulSoup
from celery import shared_task
from django.db import transaction
from django.db.models import Model, Max

from ..models import Faculty, Group

MAIN_URL = 'https://bincol.ru/rasp/'
GROUPS_PAGE_LINK = 'grupp.php'

logger = logging.getLogger(__name__)

# TODO: попробовать применить redis кэш для факультетов и групп

def get_soup_from_url(url: str) -> BeautifulSoup:
    """
    Получает содержимое веб-страницы по указанному URL и возвращает объект BeautifulSoup.

    Parameters:
    url (str): URL-адрес веб-страницы.

    Returns:
    BeautifulSoup: Объект BeautifulSoup, представляющий содержимое веб-страницы.

    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'lxml')
    except requests.RequestException as e:
        logger.error(f"Ошибка при запросе к {url}: {str(e)}")
        return BeautifulSoup()

def parse_group_list():
    url = MAIN_URL + GROUPS_PAGE_LINK
    soup = get_soup_from_url(url)
    faculty_blocks = soup.find_all('p', class_='shadow')

    for block in faculty_blocks:
        faculty_name = block.text.strip().split(' ', 1)[1]
        faculty, created = Faculty.objects.get_or_create(title=faculty_name)
        logger.debug(f"Faculty {'created' if created else 'updated'}: {faculty.title}")

        groups = block.find_next_sibling('p').find_all('a')
        for group in groups:
            group_name = group.text
            group_url = group['href']
            group_grade = group_name[0] if group_name else ''
            Group.objects.update_or_create(
                title=group_name,
                faculty=faculty,
                defaults={
                    'link': group_url,
                    'grade': group_grade,
                }
            )
            logger.debug(f"Group {'created' if created else 'updated'}: {group.title}")
        faculty.calculate_short_title()

def deactivate_old_records(model: Model, delta: timedelta):
    """
    Деактивирует записи, которые не обновлялись в течение заданного временного интервала.

    Args:
    model (Model): Класс модели Django, который нужно обновить.
    delta (timedelta): Временной интервал, после которого записи считаются устаревшими.
    """
    latest_update = model.objects.aggregate(latest=Max('updated_at'))['latest']
    threshold_date = latest_update - delta
    model.objects.filter(updated_at__lt=threshold_date, is_active=True).update(is_active=False)

@shared_task
def update_groups():
    with transaction.atomic():
        parse_group_list()
        deactivate_old_records(Faculty, timedelta(days=1))  # потом попробудем брать timedelta из celery-beat
        deactivate_old_records(Group, timedelta(days=1))