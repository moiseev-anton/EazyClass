import logging
from datetime import date as DateClass
from typing import Dict, Any, Optional, Tuple

from django.contrib.auth.models import BaseUserManager
from django.db import models
from django.db.models import Max, Q

from scheduler.utils import cache_data, invalidate_cache

CACHE_TIMEOUT = 86400  # 24 часа
USER_DATA_CACHE_TIMEOUT = 3600  # 1 час
KEYBOARD_DATA_CACHE_TIMEOUT = 82800  # 23 часа
GROUP_DATA_CACHE_TIMEOUT = 82800  # 23 часа

logger = logging.getLogger(__name__)


class IDMappableMixin:
    """ Миксин для маппинга ID"""

    def get_objects_map(self, values_set: set[tuple[Any]], field_names: tuple) -> dict:
        """
        Получить маппинг значений из БД: {значение поля -> id}.
        """
        filters = {
            f"{field}__in": {key[i] for key in values_set}
            for i, field in enumerate(field_names)
        }

        existing_objects = self.filter(**filters).values_list(*field_names, 'id')
        return {tuple(key): obj_id for *key, obj_id in existing_objects}

    def get_or_create_objects_map(self, unique_values_set: set[tuple[Any]], field_names: tuple) -> dict:
        """
        Получить маппинг существующих объектов и создать недостающие.
        """
        objects_map = self.get_objects_map(unique_values_set, field_names)

        # Определяем недостающие значения
        missing_set = unique_values_set - set(objects_map.keys())

        if missing_set:
            new_objects = self.build_model_objects(missing_set, field_names)
            self.bulk_create(new_objects)
            logger.info(f"Создано {len(missing_set)} новых записей '{self.model.__name__}'")

            # Обновляем маппинг
            objects_map.update(self.get_objects_map(missing_set, field_names))

        return objects_map

    def build_model_objects(self, values_set: set[tuple[Any]], field_names: tuple) -> list:
        new_objects = []
        for item in values_set:
            if len(item) != len(field_names):
                raise ValueError(f'Несоответствие полей {field_names} и значений {item}')

            obj = self.model(**dict(zip(field_names, item)))
            if hasattr(obj, 'pre_save_actions'):
                obj.pre_save_actions()
            new_objects.append(obj)
        return new_objects


class BaseManager(models.Manager):
    def active_keyboard_data(self):
        raise NotImplementedError("Subclasses must implement fetch_active_data method")

    def get_or_create_cached_id(self):
        raise NotImplementedError("Subclasses must implement fetch_active_data method")


class GroupManager(BaseManager):
    def active_keyboard_data(self):
        return (self.filter(is_active=True).values('id', 'title', 'grade', 'faculty__short_title')
                .order_by('faculty__short_title', 'grade', 'title'))

    @cache_data('group_links', GROUP_DATA_CACHE_TIMEOUT, 'default')
    def link_map(self):
        return list(self.filter(is_active=True).values_list('id', 'link'))


class TeacherManager(BaseManager, IDMappableMixin):
    def active_keyboard_data(self):
        return self.filter(is_active=True).values('id', 'short_name').order_by('short_name')

    @cache_data("teacher:{full_name}", timeout=CACHE_TIMEOUT)
    def get_or_create_cached_id(self, full_name: str) -> int:
        obj, created = self.get_or_create(full_name=full_name)
        return obj.id

    def get_or_create_id_map(self, unique_teachers_set):
        return super().get_or_create_objects_map(unique_teachers_set, ('full_name',))


class ClassroomManager(BaseManager, IDMappableMixin):
    @cache_data("classroom:{title}", timeout=CACHE_TIMEOUT)
    def get_or_create_cached_id(self, title: str) -> int:
        obj, created = self.get_or_create(title=title)
        return obj.id

    def get_or_create_id_map(self, unique_classroom_set):
        return super().get_or_create_objects_map(unique_classroom_set, ('title',))


class SubjectManager(BaseManager, IDMappableMixin):
    @cache_data("subject:{title}", timeout=CACHE_TIMEOUT)
    def get_or_create_cached_id(self, title: str) -> int:
        obj, created = self.get_or_create(title=title)
        return obj.id

    def get_or_create_id_map(self, unique_subject_set):
        return super().get_or_create_objects_map(unique_subject_set, ('title',))


class PeriodManager(BaseManager, IDMappableMixin):
    def get_max_date(self) -> DateClass:
        """
        Возвращает максимальную дату, которая есть в таблице LessonTime.
        Если записей нет, возвращает None.
        """
        return self.aggregate(max_date=Max('date'))['max_date']

    @cache_data("period:{date_str}{lesson_number}", timeout=CACHE_TIMEOUT)
    def get_or_create_cached_id(self, date: DateClass, lesson_number: str) -> int:
        obj, created = self.get_or_create(date=date, lesson_number=lesson_number)
        return obj.id

    def get_or_create_id_map(self, unique_periods_set: set[tuple[Any]]) -> dict:
        return super().get_or_create_objects_map(unique_periods_set, ('date', 'lesson_number'))

    # def build_period(self, date: DateClass, lesson_number: int) -> 'Period':
    #     """
    #     Создает объект Period, заполняя start_time и end_time из шаблона, если он доступен.
    #     Если шаблон отсутствует, start_time и end_time остаются None.
    #     """
    #     template = PeriodTemplateManager().get_template_for_day(date=date, lesson_number=lesson_number)
    #     start_time, end_time = (None, None) if not template else (template.start_time, template.end_time)
    #     return self.model(date=date, lesson_number=lesson_number, start_time=start_time, end_time=end_time)
    #
    # def get_map(self, period_set: set[tuple[DateClass, int]]) -> dict[tuple[DateClass, int], int]:
    #     """
    #     Возвращает словарь {(date, lesson_number): id} для существующих записей.
    #     Принимает множество кортежей вида {(date_str, lesson_number)}.
    #     """
    #     # Создаем список условий для фильтрации
    #     filters = models.Q()
    #     for date, lesson_number in period_set:
    #         filters |= models.Q(date=date, lesson_number=lesson_number)
    #
    #     # Применяем фильтры, получаем кортежи (date, lesson_number, id)
    #     existing_periods = self.filter(filters).values_list("date", "lesson_number", "id")
    #     return {(date, lesson_number): period_id for date, lesson_number, period_id in existing_periods}
    #
    # def get_or_create_map(self, unique_periods: set[tuple[DateClass, int]]) -> dict[tuple[DateClass, int], int]:
    #     """
    #     Возвращает словарь {(date, lesson_number): id}, создавая недостающие записи.
    #     Принимает множество кортежей вида {(date_str, lesson_number)}.
    #     """
    #     # Получаем существующие записи
    #     periods_map = self.get_map(unique_periods)
    #
    #     # Определяем недостающие элементы
    #     missing_periods = unique_periods - set(periods_map.keys())
    #     if missing_periods:
    #         new_periods = [self.build_period(date, lesson_number) for date, lesson_number in missing_periods]
    #         self.bulk_create(new_periods)
    #         logger.info(f"Создано {len(new_periods)} новых записей в Periods")
    #
    #         # Обновляем словарь с добавленными объектами
    #         periods_map.update(self.get_map(missing_periods))
    #
    #     return periods_map


class PeriodTemplateManager(models.Manager):
    def get_template_for_day(self, date: DateClass, lesson_number: int) -> Optional['PeriodTemplate']:
        """
        Возвращает подходящий шаблон для номера урока и дня недели (по дате).
        """
        day_of_week_number = date.weekday()  # 0 - понедельник, 6 - воскресенье

        # Получаем все шаблоны, соответствующие номеру урока и диапазону дат
        return self.filter(
            lesson_number=lesson_number,
            start_date__lte=date,
            end_date__gte=date,
        ).filter(
            # Поскольку дни недели теперь хранятся в связанной таблице PeriodTemplateWeekDay,
            # мы фильтруем по день недели через связь many-to-one
            weekdays__day_of_week=day_of_week_number
        ).first()

    def overlapping(self, lesson_number: int, start_date: DateClass, end_date: Optional[DateClass], exclude_pk: Optional[int] = None):
        """
        Возвращает пересекающиеся шаблоны с заданным периодом действия.

        Период считается пересекающимся, если:
        - Номер урока совпадает.
        - Начало периода не позже конца другого периода.
        - Конец периода не раньше начала другого периода или конец другого периода не указан.

        Args:
            lesson_number (int): Номер урока, для которого нужно проверить пересечение.
            start_date (date): Дата начала искомого периода.
            end_date (Optional[date]): Дата окончания искомого периода, может быть None.
            exclude_pk (Optional[int]): Исключить текущий объект по первичному ключу, если есть.

        Returns:
            QuerySet: Пересекающиеся записи из модели `PeriodTemplate`.
        """
        query = Q(lesson_number=lesson_number) & (
                Q(start_date__lte=end_date if end_date else start_date) &
                (Q(end_date__gte=start_date) | Q(end_date__isnull=True))
        )

        if exclude_pk:
            query &= ~Q(pk=exclude_pk)

        return self.filter(query)

    # def get_template_dict(self) -> dict:
    #     """
    #     Возвращает данные шаблона в виде словаря, где ключ — день недели,
    #     а значение — список словарей с данными уроков.
    #     """
    #     templates = self.get_queryset().all()
    #     template_dict = {}
    #     for template in templates:
    #         template_dict.setdefault(template.day_of_week, []).append({
    #             "lesson_number": template.lesson_number,
    #             "start_time": template.start_time,
    #             "end_time": template.end_time,
    #         })
    #     return template_dict


class SubscriptionManager(models.Manager):
    def invalidate_all_subscriptions(self, user_id: int):
        self.filter(user_id=user_id).delete()


class UserManager(BaseUserManager):
    @cache_data('user_data_{telegram_id}', timeout=USER_DATA_CACHE_TIMEOUT, cache_name='telegrambot_cache')
    def get_user_data_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        user = self.filter(telegram_id=telegram_id).first()
        if user is None:
            logger.warning(f'Пользователь с telegram_id {telegram_id} не найден.')
            return None
        logger.info(f'Получены данные пользователя с telegram_id {telegram_id} из БД.')
        return user.to_dict()

    def reset_subgroup(self, user_id: int):
        self.filter(id=user_id).update(subgroup='0')

    def get_or_create_by_telegram_user(self, telegram_user) -> Tuple['User', bool]:
        try:
            user, created = self.get_or_create(
                telegram_id=telegram_user.id,
                defaults={
                    'first_name': telegram_user.first_name or '',
                    'last_name': telegram_user.last_name or '',
                    'is_active': True
                }
            )
            if created:
                logger.info(f"Создан новый пользователь Telegram: {user.username} (ID: {user.id})")
            else:
                logger.info(f"Пользователь Telegram найден: {user.username} (ID: {user.id})")
            return user, created
        except Exception as e:
            logger.error(f"Ошибка при создании пользователя через Telegram: {e}")
            raise

    @invalidate_cache('user_data_{0}', cache_name='telegrambot_cache')
    def update_contact(self, telegram_id: int, contact) -> Optional['User']:
        user = self.filter(telegram_id=telegram_id).first()
        if user:
            user.phone = contact.phone_number
            user.first_name = contact.first_name or user.first_name
            user.last_name = contact.last_name or user.last_name
            user.save(update_fields=['phone', 'first_name', 'last_name'])
            logger.info(f"Контактные данные обновлены для пользователя Telegram ID {telegram_id}.")
            return user
        logger.warning(f'Не найден пользователь для обновления контактов по telegram_id {telegram_id}.')
        return None

    @invalidate_cache('user_data_{0}', cache_name='telegrambot_cache')
    def reset_subgroup(self, user_id: int) -> int:
        updated_count = self.filter(id=user_id).update(subgroup='0')
        logger.debug(f"Сброшена подгруппа для пользователя с ID {user_id}")
        return updated_count

    def create_user(self, username: str, password: Optional[str] = None, **extra_fields) -> 'User':
        if not username:
            raise ValueError('Имя пользователя (username) обязательно для создания учетной записи')

        user = self.model(username=username, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        logger.info(f"Создан новый пользователь: {user.username} (ID: {user.id})")
        return user

    def create_superuser(self, username: str, password: str, **extra_fields) -> 'User':
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Суперпользователь должен иметь is_staff=True')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Суперпользователь должен иметь is_superuser=True')

        return self.create_user(username, password, **extra_fields)
