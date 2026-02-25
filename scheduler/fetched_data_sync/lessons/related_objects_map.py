import logging
from typing import Any, Callable

from django.db import transaction
from django.db.models import Model

logger = logging.getLogger(__name__)


class RelatedObjectsMap:
    """Класс для управления маппингом значений на связанные объекты из базы данных."""
    __slots__ = ('model', 'fields', 'existing_mappings', 'pending_keys', 'skip_if')

    def __init__(self, model: type[Model], fields: tuple[str, ...], skip_if: Callable[[dict], bool] | None = None):
        """
        Инициализирует объект маппера.

        Args:
            model (Type[Model]): Модель, для которой создается маппинг.
            fields (tuple[str, ...]): Перечень полей для создания ключей.
        """
        self.model = model
        self.fields = fields
        self.existing_mappings = {}  # {mapping_key: id}
        self.pending_keys = set()  # Ключи для маппинга
        self.skip_if = skip_if

    def _generate_key(self, data: dict[str, Any]) -> tuple:
        """Создает ключ в соответствии с `fields`."""
        missing_fields = [field for field in self.fields if field not in data]
        if missing_fields:
            raise ValueError(
                f"Отсутствуют необходимые поля: {', '.join(missing_fields)} в данных: {data}"
            )
        return tuple(data[field] for field in self.fields)

    def _should_skip(self, data: dict) -> bool:
        return bool(self.skip_if and self.skip_if(data))

    def add(self, data: dict):
        """Добавляет ключ для маппинга."""
        if self._should_skip(data):
            return

        key = self._generate_key(data)
        if key not in self.existing_mappings:
            self.pending_keys.add(key)

    def get_or_map_id(self, data: dict, default=None) -> int | None:
        """Получает ID для заданных данных."""
        if self._should_skip(data):
            return None

        key = self._generate_key(data)
        if key in self.pending_keys:
            self.resolve_pending_keys()
        return self.existing_mappings.get(key, default)

    def resolve_pending_keys(self) -> None:
        """
        Получить маппинг существующих объектов и создать недостающие.
        """
        self.fetch_existing_mappings()

        if self.pending_keys:
            with transaction.atomic():
                new_objects = self.create_new_objects()
                self.model.objects.bulk_create(new_objects)
                logger.info(f"Создано {len(new_objects)} новых записей '{self.model.__name__}'")

            self.fetch_existing_mappings()

    def fetch_existing_mappings(self):
        new_map = self.model.objects.map_values_to_ids(self.pending_keys, self.fields)
        self.existing_mappings.update(new_map)

        # Удаляем значения для которых получили id из БД
        self.pending_keys -= set(new_map.keys())

    def create_new_objects(self) -> list:
        new_objects = []
        for item in self.pending_keys:
            obj = self.model(**dict(zip(self.fields, item)))
            if hasattr(obj, 'pre_save_actions'):
                try:
                    obj.pre_save_actions()
                except Exception as e:
                    logger.error(f"Ошибка в pre_save_actions для {obj}: {e}")
                    raise
            new_objects.append(obj)
        return new_objects
