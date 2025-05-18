from rest_framework import mixins
from rest_framework.viewsets import GenericViewSet
from rest_framework_json_api.views import AutoPrefetchMixin, PreloadIncludesMixin, RelatedMixin

from scheduler.api.mixins import ETagRetrieveModelMixin, ETagListModelMixin, ETagMixin


class ETagReadOnlyModelViewSet(
    ETagMixin, ETagRetrieveModelMixin, ETagListModelMixin, GenericViewSet
):
    """
    ReadOnly ViewSet с поддержкой ETag.
    """

    pass


class ETagModelViewSet(
    ETagMixin,
    mixins.CreateModelMixin,
    ETagRetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    ETagListModelMixin,
    GenericViewSet,
):
    """
    Полноценный ViewSet с поддержкой ETag в list и retrieve.
    """

    pass


class ReadOnlyModelViewSet(
    AutoPrefetchMixin, PreloadIncludesMixin, RelatedMixin, ETagReadOnlyModelViewSet
):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]


class ModelViewSet(
    AutoPrefetchMixin, PreloadIncludesMixin, RelatedMixin, ETagModelViewSet
):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
