# import hashlib
# import json
# import logging
# from datetime import datetime
#
# import requests
# from bs4 import BeautifulSoup
# from celery import shared_task, group
# from django.core.cache import cache
# from django.db.models import Model
# from django.utils import timezone
#
# from ..models import Group, Subject, Lesson, Classroom, Teacher, LessonTime
#
# MAIN_URL = 'https://bincol.ru/rasp/'
# CACHE_TIMEOUT = 60 * 60 * 24 * 30
#
# logger = logging.getLogger(__name__)
#
#
# def get_response_from_url(url: str) -> requests.Response:
#     """Отправляет HTTP-запрос GET к указанному URL и возвращает ответ.
#
#     Args:
#         url (str): URL-адрес для запроса.
#
#     Returns:
#         requests.Response: Объект ответа от сервера.
#
#     Raises:
#         requests.RequestException: Ошибка при выполнении запроса.
#     """
#     try:
#         response = requests.get(url, timeout=10)
#         response.raise_for_status()
#         return response
#     except requests.RequestException as e:
#         logger.error(f"Ошибка доступа к {url}: {str(e)}")
#         raise
#
#
# def get_soup_from_url(url: str) -> BeautifulSoup:
#     """
#     Получает HTML страницы по URL и возвращает объект BeautifulSoup.
#
#     Args:
#         url (str): URL-адрес веб-страницы.
#
#     Returns:
#         BeautifulSoup: Объект BeautifulSoup, представляющий содержимое веб-страницы.
#     """
#     try:
#         response = get_response_from_url(url)
#         return BeautifulSoup(response.content, 'lxml')
#     except Exception as e:
#         logger.error(f"Ошибка создания BeautifulSoup из {url}: {str(e)}")
#         return BeautifulSoup()
#
#
# def generate_cache_key(model_class: Model, params: dict) -> str:
#     """
#     Генерирует уникальный ключ кэша для заданной модели и параметров.
#
#     Args:
#         model:
#         params (dict): Словарь параметров, которые идентифицируют объект модели.
#
#     Returns:
#         str: Уникальный ключ кэша.
#     """
#     if params.get('date'):
#         params['date'] = params['date'].isoformat()
#     params_string = json.dumps(params, sort_keys=True)
#     key = model_class.__name__ + params_string
#     hash_digest = hashlib.md5(key.encode()).hexdigest()
#     return hash_digest
#
#
# def get_or_create_cached(model_class: Model, defaults: dict, timeout: int = CACHE_TIMEOUT) -> Model:
#     """
#     Получает из кэша или создает объект модели в БД с кэшированием, используя словарь атрибутов.
#
#     Args:
#         model (Model): Класс модели Django, например, Teacher, Subject или Classroom.
#         defaults (dict): Словарь с полями и значениями для поиска или создания объекта.
#         timeout (int): Время жизни кэша в секундах.
#
#     Returns:
#         Model: Экземпляр найденного или созданного объекта.
#     """
#     key = generate_cache_key(model_class, defaults)
#     obj = cache.get(key)
#     if not obj:
#         obj, created = model_class.objects.get_or_create(**defaults)
#         cache.set(key, obj, timeout=timeout)  # Установка кэша с заданным тайм-аутом
#     return obj
#
#
# def get_cached_by_id(model: Model, obj_id: int, timeout: int = CACHE_TIMEOUT) -> Model:
#     """
#     Получает объект модели из кэша по ID или из базы данных.
#
#     Args:
#         model (Model): Класс модели Django.
#         obj_id (int): Идентификатор объекта.
#         timeout (int): Время жизни кэша в секундах.
#
#     Returns:
#         Model: Экземпляр объекта модели.
#     """
#     obj_params = {model.__name__: obj_id}
#     cache_key = generate_cache_key(model, obj_params)
#     obj = cache.get(cache_key)
#     if obj:
#         logger.debug(f"{model.__name__} с ID {obj_id} получен из кэша.")
#         return obj
#
#     try:
#         obj = model.objects.get(id=obj_id)
#         cache.set(cache_key, obj, timeout=timeout)
#         logger.debug(f"{model.__name__} с ID {obj_id} получен из БД и кэширован.")
#     except model.DoesNotExist:
#         logger.error(f"{model.__name__} с ID {obj_id} не найден в БД.")
#         return None
#
#
# def parse_group_schedule_soup(group_id: int, soup: BeautifulSoup) -> list[dict]:
#     """
#     Парсит данные расписания из объекта BeautifulSoup для определённой группы.
#     Обрабатывает каждую строку таблицы расписания, извлекая даты и информацию об уроках.
#
#     Args:
#         group_id (int): Идентификатор группы, для которой происходит парсинг расписания.
#         soup (BeautifulSoup): Объект BeautifulSoup, содержащий HTML-код страницы расписания.
#
#     Returns:
#         list[dict]: Список словарей, где каждый словарь содержит информацию о конкретном уроке.
#                     Ключи словаря включают 'date', 'lesson_number', 'subject_title',
#                     'classroom_title', 'teacher_name', и 'subgroup'.
#     """
#     current_date = None
#     lessons_data = []
#     for row in soup.find_all('tr', class_='shadow'):
#         if row.find(attrs={"colspan": True}):
#             current_date = None
#             try:
#                 date_str = row.text.strip().split(' - ')[0]
#                 current_date = datetime.strptime(date_str, '%d.%m.%Y').date()
#             except ValueError as e:
#                 logger.error(f"Не удалось получить дату из строки '{date_str}': {str(e)}")
#                 continue
#         elif current_date:
#             cells = row.find_all('td')
#             if len(cells) == 5:
#                 lesson_dict = {
#                     'date': current_date,
#                     'lesson_number': cells[0].text.strip(),
#                     'subject_title': cells[1].text.strip() or 'не указано',
#                     'classroom_title': cells[2].text.strip() or '(дист)',
#                     'teacher_name': cells[3].text.strip() or 'не указано',
#                     'subgroup': cells[4].text.strip() or '0',
#                     'group_id': group_id
#                 }
#                 lessons_data.append(lesson_dict)
#     logger.debug(f"Выполнен парсинг для группы c ID {group_id}: получили {len(lessons_data)} строки.")
#     return lessons_data
#
#
# @shared_task
# def parse_group_lessons_data(group_id: int) -> list[dict]:
#     """
#     Парсит данные уроков для конкретной группы и возвращает список уроков в виде словарей.
#
#     Args:
#         group_id (int): id группы, для которой происходит парсинг уроков.
#
#     Returns:
#         list[dict]: Список словарей, каждый из которых содержит данные об уроке.
#     """
#     group_ = get_cached_by_id(Group, group_id, timeout=CACHE_TIMEOUT)
#     if not group_:
#         return []
#
#     url = MAIN_URL + group_.link
#     schedule_soup = get_soup_from_url(url)
#     if not schedule_soup:
#         return []
#
#     lessons_data = parse_group_schedule_soup(group_id, schedule_soup)
#
#     # Если расписание доступно, но пустое, значит надо все равно вернуть id группы
#     # для деактивации занятий (очищаем расписание на эти дни)
#     if not lessons_data:
#         lessons_data.append({'group_id': group_id})
#
#     return lessons_data
#
#
# def get_lesson_from_data(data: dict, timeout=CACHE_TIMEOUT) -> Lesson:
#     teacher = get_or_create_cached(Teacher, {'full_name': data['teacher_name']}, timeout)
#     classroom = get_or_create_cached(Classroom, {'title': data['classroom_title']}, timeout)
#     subject = get_or_create_cached(Subject, {'title': data['subject_title']}, timeout)
#     lesson_time = get_or_create_cached(
#         LessonTime,
#         {'date': data['date'], 'lesson_number': data['lesson_number']},
#         timeout
#     )
#     group_ = get_cached_by_id(Group, data['group_id'], timeout)
#
#     if not group_:
#         return None
#
#     lesson = Lesson(
#         group=group_,
#         subgroup=data['subgroup'],
#         lesson_time=lesson_time,
#         teacher=teacher,
#         classroom=classroom,
#         subject=subject
#     )
#
#     return lesson
#
#
# def save_lessons(group_id: int, lessons_data: list[dict]):
#     """
#     Сохраняет данные новых уроков в базе данных.
#
#     Args:
#         lessons_data (list[dict]): Список словарей, содержащий данные уроков.
#
#     Returns:
#         set: Множество дат, для которых обнаружены изменения.
#     """
#     today = timezone.now().date()
#     existing_lessons = Lesson.objects.filter(group__id=group_id, lesson_time__date__gte=today, is_active=True)
#     existing_lessons_map = {lesson: lesson for lesson in existing_lessons}
#
#     new_lessons = []
#     processed_lessons = set()
#     affected_dates = set()
#
#     for data in lessons_data:
#         if 'date' not in data:
#             continue  # Пропускаем данные без даты (т.е. только с идентификатором группы)
#
#         lesson = get_lesson_from_data(data)
#         if lesson:
#             if lesson in existing_lessons_map:
#                 processed_lessons.add(existing_lessons_map[lesson])
#             else:
#                 new_lessons.append(lesson)
#                 affected_dates.add(lesson.lesson_time.date)
#
#     if new_lessons:
#         Lesson.objects.bulk_create(new_lessons)
#
#     lessons_to_deactivate = set(existing_lessons) - processed_lessons
#     if lessons_to_deactivate:
#         lesson_ids_to_deactivate = []
#         for lesson in lessons_to_deactivate:
#             lesson_ids_to_deactivate.append(lesson.id)
#             affected_dates.add(lesson.lesson_time.date)
#         Lesson.objects.filter(id__in=lesson_ids_to_deactivate).update(is_active=False)
#
#     return affected_dates
#
#
# @shared_task
# def process_group_lessons_data(lessons_data: list[dict]):
#     """
#     Обрабатывает данные уроков для группы, сохраняя новые уроки и деактивируя отменённые.
#
#     Args:
#         lessons_data (list[dict]): Список словарей, содержащий данные об уроке.
#     """
#     if lessons_data:
#         group_id = lessons_data[0]['group_id']
#         affected_dates = save_lessons(group_id, lessons_data)
#         if affected_dates:
#             pass
#     # notify_users(group_id, affected_dates)
#
#
# @shared_task
# def update_schedule():
#     """
#     Обновляет данные уроков для всех активных групп.
#
#     Выполняет также деактивацию отмененных занятий.
#     """
#     try:
#         get_response_from_url(MAIN_URL)
#         logger.info(f"Сайт {MAIN_URL} доступен. Начинается обновление уроков.")
#     except requests.RequestException as e:
#         logger.error(f"Обновление уроков не выполнено: {str(e)}.")
#         return
#
#     group_ids = Group.objects.filter(is_active=True).values_list('id', flat=True)
#     tasks = [parse_group_lessons_data.s(group_id).set(link=process_group_lessons_data.s()) for group_id in
#              group_ids]
#     group(tasks).apply_async()
#
#     logger.info(f"Запущены задачи для обновления уроков для {len(group_ids)} групп.")
