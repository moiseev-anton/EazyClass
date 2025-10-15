import hashlib
import json
import logging
from datetime import datetime
from typing import Dict, Set, Tuple
from django.utils import timezone

from django.db import models
from django.db.models import Max, Count, Value
from django.db.models.functions import Coalesce
from django.utils.module_loading import import_string
from drf_spectacular.openapi import AutoSchema
from drf_spectacular_jsonapi.schemas.openapi import JsonApiAutoSchema
from rest_framework import status
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework_json_api.parsers import JSONParser as JSONAPIParser
from rest_framework_json_api.renderers import JSONRenderer as JSONAPIRenderer
from rest_framework_json_api.utils import get_included_resources

logger = logging.getLogger(__name__)


MIN_AWARE_DATETIME = timezone.make_aware(datetime(1970, 1, 1))


class JsonApiMixin:
    parser_classes = [JSONAPIParser]
    renderer_classes = [JSONAPIRenderer]
    schema = JsonApiAutoSchema()


class PlainApiViewMixin:
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer]
    schema = AutoSchema()


class ETagMixin:
    """
    Миксин для поддержки ETag в DRF с drf-jsonapi.
    Генерирует weak/strong ETag на основе агрегации (MAX(updated_at) + COUNT(id)) для main и relations.
    - Reverse relations (обратные связи) агрегируются всегда (для catch изменений в relationships IDs).
    - Forward relations (прямые связи) — только если в ?include (для catch изменений в included data).
    Использование: Наследуйте в ViewSet, e.g., class MyViewSet(ModelViewSet, ETagListModelMixin, ETagRetrieveModelMixin).
    Настройка: self.use_id_hash = True для stronger ETag (hash IDs, если qs small).
    """

    use_id_hash = False
    weak_etag = True

    def get_object(self):
        if not hasattr(self, "_cached_object"):
            self._cached_object = super().get_object()
        return self._cached_object

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

    def get_reverse_relations_from_serializer(self) -> dict[str, str]:
        """
        Возвращает обратные связи модели, которые реально объявлены в сериализаторе
        и имеют updated_at. Формат: {accessor_name: accessor_name}
        """
        reverse_rels: dict[str, str] = {}
        serializer_class = self.get_serializer_class()

        # Берём все поля сериализатора, исключая write_only
        declared_fields = {
            name
            for name, field in serializer_class().get_fields().items()
            if not getattr(field, "write_only", False)
        }

        try:
            # Определяем основную модель
            model = getattr(
                serializer_class.Meta, "model", getattr(self.queryset, "model", None)
            )
            if model is None:
                logger.warning("No model found for reverse relations extraction")
                return set()

            # Перебираем все связанные reverse-объекты модели
            for rel in model._meta.related_objects:
                accessor = rel.get_accessor_name()
                related_model = rel.related_model

                # Отбираем те, что реально отображаются в сериализаторе и имеют updated_at
                if accessor in declared_fields and hasattr(related_model, "updated_at"):
                    reverse_rels[accessor] = accessor

        except Exception as e:
            logger.warning(f"Error extracting reverse relations: {e}")

        logger.info(f"[ETagMixin] Reverse_relations fields: {reverse_rels}")
        return reverse_rels

    def get_valid_included_fields(self) -> dict[str, str]:
        serializer_class = self.get_serializer_class()
        included_serializers = getattr(serializer_class, "included_serializers", {})

        # include из запроса
        included_paths: Set[str] = set(
            get_included_resources(self.request, serializer_class)
        )
        included_paths = {part for path in included_paths for part in path.split(".")}

        model = getattr(
            serializer_class.Meta, "model", getattr(self.queryset, "model", None)
        )

        valid_included: dict[str, str] = {}

        for name, serializer_ref in included_serializers.items():
            if name not in included_paths:
                continue

            try:
                serializer_cls = (
                    import_string(serializer_ref)
                    if isinstance(serializer_ref, str)
                    else serializer_ref
                )
                related_model = serializer_cls.Meta.model
            except Exception as e:
                logger.warning(f"[ETagMixin] Failed to load serializer '{name}': {e}")
                continue

            if related_model is None or not hasattr(related_model, "updated_at"):
                continue

            # --- пытаемся найти путь от base_model к related_model ---
            relation_path = None
            try:
                # если прямое поле (FK/OneToOne)
                field = model._meta.get_field(name)
                if isinstance(
                    field,
                    (
                        models.ForeignKey,
                        models.OneToOneField,
                        models.ManyToManyField,
                    ),
                ):
                    relation_path = name
            except Exception:
                # если это не прямое поле, возможно, это связано через подтип (полиморфную модель)
                for rel in model._meta.related_objects:
                    accessor = rel.get_accessor_name()
                    rel_model = rel.related_model
                    if any(
                        f.name == name
                        for f in rel_model._meta.get_fields()
                        if isinstance(f, (models.ForeignKey, models.OneToOneField))
                    ):
                        relation_path = f"{accessor}__{name}"
                        break

            if relation_path:
                valid_included[name] = relation_path

        logger.info(f"[ETagMixin] Valid included fields: {valid_included}")
        return valid_included

    def get_aggregates(self, relations: dict[str, str]) -> Dict:
        """
        Генерирует агрегаты (MAX(updated_at), COUNT(id)) по relations paths.
        - Coalesce для fallback (min datetime, если null/empty).
        - Distinct COUNT для 1:N (избегает дубликатов).
        Возврат: Dict[str, Expression] для qs.aggregate(**this).
        """
        aggregates = {}
        for name, path in relations.items():
            aggregates[f"{name}_max"] = Max(f"{path}__updated_at")
            aggregates[f"{name}_count"] = Count(f"{path}__id")
        return aggregates

    @staticmethod
    def update_counts_and_max(
        relations: dict[str, str], stats: Dict, total_count: int, max_updated: datetime
    ) -> Tuple[int, datetime]:
        """
        Обновляет total_count (сумма counts) и max_updated (max из rel_max) из aggregate stats.
        Помогает аккумулировать метрики для ETag.
        """
        for rel in relations.keys():
            total_count += stats.get(f"{rel}_count", 0)
            rel_max = stats.get(f"{rel}_max")
            if rel_max > max_updated:
                max_updated = rel_max
        logger.info(f"Добавляем total_count={total_count}, max_updated={max_updated}")
        return total_count, max_updated

    def _get_id_hash(self, qs):
        """
        Hash sorted IDs queryset для stronger ETag (catch delete/add точно).
        - Только если self.use_id_hash=True (heavy для large qs).
        """
        if not self.use_id_hash:
            return ""
        ids = sorted(qs.values_list("id", flat=True))  # Fast list IDs
        return hashlib.md5(json.dumps(list(ids)).encode()).hexdigest()

    def collect_etag_metrics(self, many: bool = False) -> Dict:
        """
        Собирает метрики для ETag в list (коллекция).
        - Main aggregate всегда.
        - Forward: Только если in ?include (экономия, catch included changes).
        - Reverse: Всегда (catch relationships IDs changes).
        - На filtered qs (до paginate, full коллекция).
        Возврат: Dict с max_updated (timestamp), total_count, id_hash.
        """
        qs = self.filter_queryset(self.get_queryset())

        if not many:
            pk = self.kwargs.get(self.lookup_field)
            if pk is not None:
                qs = qs.filter(pk=pk)

        if not qs.exists():
            return {"max_updated": 0, "total_count": 0, "id_hash": ""}

        # Main всегда
        main_stats = qs.aggregate(
            max_updated=Coalesce(Max("updated_at"), Value(MIN_AWARE_DATETIME)),
            count=Count("id"),
        )

        max_updated = main_stats["max_updated"]
        total_count = main_stats["count"]
        logger.info(f"Main stats: max_updated={max_updated}, total_count={total_count}")

        # === Reverse relations ===
        reverse_rels = self.get_reverse_relations_from_serializer()

        # === Forward relations ===
        included_fields = self.get_valid_included_fields()

        forward_rels = {
            k: v for k, v in included_fields.items() if k not in reverse_rels
        } # Исключаем reverse из include

        # Forward: агрегируем только если есть в include
        if forward_rels:
            fwd_aggregates = self.get_aggregates(forward_rels)
            fwd_stats = qs.aggregate(**fwd_aggregates)
            logger.info(f"Forward stats: {fwd_stats}")
            total_count, max_updated = self.update_counts_and_max(
                forward_rels, fwd_stats, total_count, max_updated
            )

        # Reverse: добавляем если есть независимо от include
        if reverse_rels:
            rev_aggregates = self.get_aggregates(reverse_rels)
            rev_stats = qs.aggregate(**rev_aggregates)
            logger.info(f"Reverse stats: {rev_stats}")
            total_count, max_updated = self.update_counts_and_max(
                reverse_rels, rev_stats, total_count, max_updated
            )

        id_hash = self._get_id_hash(qs)

        return {
            "max_updated": (
                max_updated.timestamp()
                if max_updated != Value(MIN_AWARE_DATETIME)
                else 0
            ),
            "total_count": total_count,
            "id_hash": id_hash,
        }

    def generate_etag(self, many: bool, weak: bool) -> str:
        """Генерация ETag на основе аккумулированных данных"""
        etag_metrics = self.collect_etag_metrics(many)
        request_uri = self.request.build_absolute_uri()
        data_str = (
            f"{request_uri}-"
            f"{etag_metrics['max_updated']}-"
            f"{etag_metrics['total_count']}-"
            f"{etag_metrics['id_hash']}"
        )
        etag = hashlib.md5(data_str.encode("utf-8")).hexdigest()
        return f"W/{etag}" if weak else etag

    def check_etag(self, many: bool = False) -> Tuple[str, bool]:
        """
        Проверяет ETag из заголовка If-None-Match.
        Возвращает кортеж (etag, is_matched).
        """
        new_etag = self.generate_etag(many, weak=True)
        client_etag = self.request.META.get("HTTP_IF_NONE_MATCH", "").strip('"')
        is_matched = client_etag == new_etag
        logger.info(
            f"ETag ({'list' if many else 'retrieve'}): Client={client_etag}, New={new_etag}, Matched={is_matched}"
        )
        return new_etag, is_matched


class ETagListModelMixin(ListModelMixin):
    """
    List a queryset.
    """
    def list(self, request, *args, **kwargs):
        etag, is_matched = self.check_etag(many=True)
        if is_matched:
            return Response(status=status.HTTP_304_NOT_MODIFIED)

        response = super().list(request, *args, **kwargs)
        if response.status_code == 200:
            response["ETag"] = etag
        return response


class ETagRetrieveModelMixin(RetrieveModelMixin):
    def retrieve(self, request, *args, **kwargs):
        etag, is_matched = self.check_etag()
        if is_matched:
            return Response(status=status.HTTP_304_NOT_MODIFIED)

        response = super().retrieve(request, *args, **kwargs)
        if response.status_code == 200:
            response["ETag"] = etag
        return response
