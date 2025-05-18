import datetime
import hashlib
import logging
from typing import Optional, List, Dict, Iterable, Tuple

from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist
from django.db.models import Max, Count
from django.db.models import Model, ForeignKey, ManyToManyField, OneToOneField
from django.http import Http404
from drf_spectacular.openapi import AutoSchema
from drf_spectacular_jsonapi.schemas.openapi import JsonApiAutoSchema
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework_json_api.parsers import JSONParser as JSONAPIParser
from rest_framework_json_api.renderers import JSONRenderer as JSONAPIRenderer
from rest_framework_json_api.utils import get_included_resources
from rest_framework_json_api.views import (
    AutoPrefetchMixin,
    PreloadIncludesMixin,
    RelatedMixin,
)

logger = logging.getLogger(__name__)


class JsonApiMixin:
    parser_classes = [JSONAPIParser]
    renderer_classes = [JSONAPIRenderer]
    schema = JsonApiAutoSchema()


class PlainApiViewMixin:
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer]
    schema = AutoSchema()


class IncludeMixin(JsonApiMixin, AutoPrefetchMixin, PreloadIncludesMixin, RelatedMixin):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]


class EtagMixin:
    def get_select_related(self, include) -> Optional[List]:
        return getattr(self, "select_for_includes", {}).get(include, None)

    def get_prefetch_related(self, include) -> Optional[List]:
        return getattr(self, "prefetch_for_includes", {}).get(include, None)

    @staticmethod
    def has_field(model_class: Model, field_name: str) -> bool:
        """Проверяет, есть ли поле в модели."""
        try:
            model_class._meta.get_field(field_name)
            return True
        except FieldDoesNotExist:
            return False

    def get_relation_model_map(self, relations: set[str]) -> dict[str, Model]:
        """
        Извлекает все уникальные модели из отношений.

        Пример:
            Вход: {'author__bio', 'publisher'}
            Выход: {'author': Author, 'bio': Bio, 'publisher': Publisher}
        """
        result = {}
        main_model = self.queryset.model

        for relation in relations:
            current_model = main_model
            for part in relation.split("__"):
                try:
                    field = current_model._meta.get_field(part)
                    if isinstance(field, (ForeignKey, ManyToManyField, OneToOneField)):
                        current_model = field.related_model
                        result[part] = current_model
                    else:
                        break
                except FieldDoesNotExist:
                    break
        return result

    def filter_relations_by_fields(
        self, relation_map: Dict[str, Model], required_fields: Iterable[str]
    ) -> List[str]:
        """
        Фильтрует отношения, оставляя только те, где модели содержат нужные поля.

        Пример:
            Вход: {'author': Author, 'bio': Bio}, ['updated_at']
            Выход: ['author', 'bio'] (если обе модели имеют updated_at)
        """
        return [
            relation
            for relation, model in relation_map.items()
            if all(self.has_field(model, field) for field in required_fields)
        ]

    def get_all_relations(self) -> set[str]:
        """Собирает все уникальные отношения из include-правил"""
        relations = set()
        included_resources = get_included_resources(
            self.request, self.get_serializer_class()
        )

        for include in included_resources + ["__all__"]:
            if select_relations := self.get_select_related(include):
                relations.update(select_relations)
            if prefetch_relations := self.get_prefetch_related(include):
                relations.update(
                    rel for rel in prefetch_relations if isinstance(rel, str)
                )

        return relations

    def get_aggregates(self, relations: list[str]) -> dict[str, object]:
        aggregates = {}
        for relation in relations:
            aggregates[f"{relation}_max"] = Max(f"{relation}__updated_at")
            aggregates[f"{relation}_count"] = Count(f"{relation}__id")
        return aggregates

    @staticmethod
    def update_counts_and_max(valid_relations, stats, total_count, max_updated):
        for relation in valid_relations:
            total_count += stats.get(f"{relation}_count", 0)
            rel_max = stats.get(f"{relation}_max")
            if rel_max and rel_max > max_updated:
                max_updated = rel_max
        return total_count, max_updated

    def collect_etag_metrics_for_list(self):
        """
        Собирает данные для ETag:
        - Максимальный updated_at среди всех связанных моделей
        - Общее количество записей во всех связанных моделях
        """
        # 1. Получаем финальный QuerySet
        qs = self.filter_queryset(self.get_queryset())
        qs = self.paginate_queryset(qs) or qs

        if not qs.exists():
            return {"max_updated": 0, "total_count": 0}

        # Собираем все отношения
        relations = self.get_all_relations()
        relation_map = self.get_relation_model_map(relations)
        valid_relations = self.filter_relations_by_fields(relation_map, ("updated_at",))

        aggregates = {
            "main_max": Max("updated_at"),
            "main_count": Count("id"),
            **self.get_aggregates(valid_relations),
        }
        stats = qs.aggregate(**aggregates)

        total_count = stats.get("main_count", 0)
        max_updated = stats.get("main_max") or datetime.datetime.min
        total_count, max_updated = self.update_counts_and_max(
            valid_relations, stats, total_count, max_updated
        )

        return {
            "max_updated": (
                max_updated.timestamp() if max_updated != datetime.datetime.min else 0
            ),
            "total_count": total_count,
        }

    def collect_etag_metrics_for_instance(self):
        """
        Собирает данные для ETag:
        - Максимальный updated_at среди всех связанных моделей
        - Общее количество записей во всех связанных моделях
        """
        try:
            instance = self.get_object()
        except (Http404, ObjectDoesNotExist):
            return {"max_updated": 0, "total_count": 0}

        max_updated = instance.updated_at or datetime.datetime.min
        total_count = 1

        relations = self.get_all_relations()
        relation_map = self.get_relation_model_map(relations)
        valid_relations = self.filter_relations_by_fields(relation_map, ("updated_at",))

        if valid_relations:
            qs = self.filter_queryset(self.get_queryset()).filter(pk=instance.pk)
            aggregates = self.get_aggregates(valid_relations)
            stats = qs.aggregate(**aggregates)
            total_count, max_updated = self.update_counts_and_max(
                valid_relations, stats, total_count, max_updated
            )

        return {
            "max_updated": (
                max_updated.timestamp() if max_updated != datetime.datetime.min else 0
            ),
            "total_count": total_count,
        }

    def get_etag_data(self, many: bool):
        if many:
            return self.collect_etag_metrics_for_list()
        return self.collect_etag_metrics_for_instance()

    def generate_etag(self, many: bool):
        """Генерация ETag на основе аккумулированных данных"""
        etag_data = self.get_etag_data(many)
        request_uri = self.request.build_absolute_uri()
        return hashlib.md5(
            f"{request_uri}-{etag_data['max_updated']}-{etag_data['total_count']}".encode(
                "utf-8"
            )
        ).hexdigest()

    def check_etag(self, many: bool = False) -> Tuple[str, bool]:
        """
        Проверяет ETag из заголовка If-None-Match.
        Возвращает кортеж (etag, is_matched).
        """
        new_etag = self.generate_etag(many)
        client_etag = self.request.headers.get("If-None-Match", "").strip('"')
        is_matched = client_etag is not None and client_etag == new_etag
        return new_etag, is_matched

    def filter_queryset(self, queryset):
        """Переопределяет filter_queryset для использования кэшированного результата."""
        if not hasattr(self, "_cached_filter_queryset"):
            self._cached_filter_queryset = super().filter_queryset(queryset)
        return self._cached_filter_queryset

    def paginate_queryset(self, queryset):
        """Переопределяет paginate_queryset для использования кэшированного результата."""
        if not hasattr(self, "_cached_paginate_queryset"):
            self._cached_paginate_queryset = super().paginate_queryset(queryset)
        return self._cached_paginate_queryset

    def get_object(self):
        if not hasattr(self, "_cached_object"):
            self._cached_object = super().get_object()
        return self._cached_object
