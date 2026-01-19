import logging
from typing import Any

from django.db import connection
from django.db.models import Q

logger = logging.getLogger(__name__)


class IDMappableMixin:
    """Миксин для маппинга ID с упрощенным адаптивным подходом."""

    def map_values_to_ids(self, values_set: set[tuple[Any]], field_names: tuple, batch_size=1000) -> dict:
        """
        Получает маппинг значений {значение -> id} с упрощенным адаптивным подходом.
        """
        if not values_set or not field_names:
            return {}

        # Определяем стратегию в зависимости от количества значений
        if len(values_set) <= 10:
            logger.debug("Значений меньше 10 применяем _get_id_map_small")
            return self._get_id_map_for_small_set(values_set, field_names)
        else:
            logger.debug("Значений больше 10 применяем пакетную обработку")
            return self._get_id_map_batched(values_set, field_names, batch_size)

    def _get_id_map_for_small_set(self, values_set: set[tuple[Any]], field_names: tuple) -> dict:
        """
        Использует OR-фильтры для небольших наборов данных.
        """
        q_objects = Q()
        for key in values_set:
            q_filter = Q()
            for i, field in enumerate(field_names):
                q_filter &= Q(**{field: key[i]})
            q_objects |= q_filter

        existing_objects = self.filter(q_objects).values_list(*field_names, 'id')
        return {tuple(key): obj_id for *key, obj_id in existing_objects}

    def _get_id_map_batched(self, values_set: set[tuple[Any]], field_names: tuple, batch_size: int) -> dict:
        """
        Использует временную таблицу с пакетной обработкой для больших наборов данных.
        """
        id_map = {}
        values_list = list(values_set)
        for i in range(0, len(values_list), batch_size):
            batch = values_list[i:i + batch_size]
            id_map.update(self._get_id_map_for_batch(batch, field_names))
        return id_map

    def _get_id_map_for_batch(self, values_set: list[tuple[Any]], field_names: tuple) -> dict:
        """
        Использует временную таблицу для обработки одного пакета данных.
        """
        table_name = self.model._meta.db_table  # Имя таблицы модели
        id_field = "id"  # Поле, содержащее ID

        # Формируем массивы значений для каждого поля
        field_values = {
            field: [key[i] for key in values_set]
            for i, field in enumerate(field_names)
        }

        # Генерируем SQL-запрос с параметрами
        sql_query = f"""
            WITH temp_pairs AS (
                SELECT {', '.join(f"unnest(%s) AS {field}" for field in field_names)}
            )
            SELECT p.{', p.'.join(field_names)}, p.{id_field}
            FROM {table_name} p
            JOIN temp_pairs t
            ON {" AND ".join(f"p.{field} = t.{field}" for field in field_names)};
        """

        # Выполняем SQL-запрос с параметрами
        with connection.cursor() as cursor:
            cursor.execute(sql_query, [field_values[field] for field in field_names])
            rows = cursor.fetchall()

        # Возвращаем словарь { (значение1, значение2): id }
        return {tuple(row[:-1]): row[-1] for row in rows}
