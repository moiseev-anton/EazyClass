import logging
from typing import Any

from bulk_sync import bulk_sync
from django.db.models import Model

logger = logging.getLogger(__name__)


class RelatedObjectsMap:
    """Класс для управления маппингом значений на связанные объекты из базы данных."""
    __slots__ = ('model', 'fields', 'existing_mappings', 'pending_keys')

    def __init__(self, model: Model, fields: tuple[str]):
        """
        Инициализирует объект маппера.

        Args:
            model (Type[Model]): Модель, для которой создается маппинг.
            fields (list[str]): Список полей для создания ключей.
        """
        self.model = model
        self.fields = fields
        self.existing_mappings = {}  # {mapping_key: id}
        self.pending_keys = set()  # Ключи для маппинга

    def _generate_key(self, data: dict[str, Any]) -> tuple:
        """Создает ключ в соответствии с `fields`."""
        missing_fields = [field for field in self.fields if field not in data]
        if missing_fields:
            raise ValueError(
                f"Отсутствуют необходимые поля: {', '.join(missing_fields)} в данных: {data}"
            )
        return tuple(data[field] for field in self.fields)

    def add(self, data: dict):
        """Добавляет ключ для маппинга."""
        key = self._generate_key(data)
        if key not in self.existing_mappings:
            self.pending_keys.add(key)

    def get_or_map_id(self, data: dict, default=None) -> int:
        """Получает ID для заданных данных."""
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
            new_objects = self.create_new_objects()
            self.bulk_create(new_objects)
            logger.info(f"Создано {len(new_objects)} новых записей '{self.model.__name__}'")

            self.fetch_existing_mappings()

    def fetch_existing_mappings(self):
        new_map = self.model.get_id_map(self.pending_keys, self.fields)
        self.existing_mappings.update(new_map)

        # Удаляем значения для которых получили id из БД
        self.pending_keys -= set(new_map.keys())

    def create_new_objects(self) -> list:
        new_objects = []
        for item in self.pending_keys:
            obj = self.model(**dict(zip(self.fields, item)))
            if hasattr(obj, 'pre_save_actions'):
                obj.pre_save_actions()
            new_objects.append(obj)
        return new_objects
