import logging
from typing import Any

from django.db.models import Model

logger = logging.getLogger(__name__)


class RelatedObjectsMap:
    __slots__ = ('model', 'mapping', 'unmapped_keys')
    """
    Класс для управления маппингом значений на связанные объекты из базы данных.
    """

    def __init__(self, model: Model, enforce_check=True):
        self.model = model
        self.mapping = {}
        self.unmapped_keys = set()

        # Опциональная проверка содержит ли модель метод маппинга ID. По умолчанию ВКЛ
        if enforce_check and not hasattr(self.model.objects, "get_or_create_objects_map"):
            raise AttributeError(
                f"Менеджер модели '{self.model.__name__}' не реализует 'get_or_create_objects_map'"
            )

    def add(self, key: str | tuple):
        if key not in self.mapping:
            self.unmapped_keys.add(key)

    def add_set(self, keys: set[str | tuple]):
        self.unmapped_keys.update(keys)

    def map(self):
        if self.unmapped_keys:
            new_mappings = self.model.objects.get_or_create_objects_map(self.unmapped_keys)
            self.mapping.update(new_mappings)
            self.unmapped_keys.clear()

    def get_id(self, key: Any, default=None) -> int:
        if key in self.unmapped_keys:
            self.map()
        return self.mapping.get(key, default)
