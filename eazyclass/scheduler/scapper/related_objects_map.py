import logging
from typing import Any

from bulk_sync import bulk_sync
from django.db.models import Model

logger = logging.getLogger(__name__)


class RelatedObjectsMap:
    """Класс для управления маппингом значений на связанные объекты из базы данных."""
    __slots__ = ('model', 'fields', 'mapping', 'unmapped_keys')

    def __init__(self, model: Model, fields: list[str]):
        """
        Инициализирует объект маппера.

        Args:
            model (Type[Model]): Модель, для которой создается маппинг.
            fields (list[str]): Список полей для создания ключей.
        """
        self.model = model
        self.fields = fields
        self.mapping = {}  # {mapping_key: id}
        self.unmapped_keys = set()  # Ключи для маппинга

    def _create_key(self, data: dict[str, Any]) -> tuple:
        """Создает ключ в соответствии с `fields`."""
        missing_fields = [field for field in self.fields if field not in data]
        if missing_fields:
            raise ValueError(
                f"Отсутствуют необходимые поля: {', '.join(missing_fields)} в данных: {data}"
            )
        return tuple(data[field] for field in self.fields)

    def add(self, data: dict):
        """Добавляет ключ для маппинга."""
        key = self._create_key(data)
        if key not in self.mapping:
            self.unmapped_keys.add(key)

    def map(self) -> None:
        """
        Получает или создает недостающие объекты и обновляет маппинг.

        Использует `bulk_sync` для синхронизации объектов с базой данных.
        """
        if self.unmapped_keys:
            keys_as_dicts = [dict(key) for key in self.unmapped_keys]
            new_objects = [self.model(**key) for key in keys_as_dicts]

            synced_objects = bulk_sync(
                new_models=new_objects,
                filters={},
                key_fields=self.fields,
                skip_deletes=True,
            )

            new_mappings = {
                tuple((field, getattr(obj, field)) for field in self.fields): obj.id
                for obj in synced_objects
            }

            self.mapping.update(new_mappings)
            self.unmapped_keys.clear()

    def get_id(self, data: dict, default=None) -> int:
        """Получает ID для заданных данных."""
        key = self._create_key(data)
        if key in self.unmapped_keys:
            self.map()
        return self.mapping.get(key, default)
