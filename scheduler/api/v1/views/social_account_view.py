from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated

from rest_framework_json_api.views import ReadOnlyModelViewSet

from scheduler.api.mixins import JsonApiMixin
from scheduler.api.v1.serializers import SocialAccountSerializer
from scheduler.models import SocialAccount


class SocialAccountViewSet(
    JsonApiMixin,
    ReadOnlyModelViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = SocialAccountSerializer
    queryset = SocialAccount.objects.filter()

    http_method_names = ["get"]

    select_for_includes = {
        "__all__": [],
        "user": ["user"],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(user=self.request.user)


    @extend_schema(
        tags=["Social Account"],
        summary="List current user's social accounts",
        description="Returns all social accounts linked to the authenticated user.",
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        tags=["Social Account"],
        summary="Retrieve a social account",
        description="Returns a specific social account belonging to the authenticated user.",
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)