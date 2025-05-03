import logging
import uuid

from django.conf import settings
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
)
from rest_framework import status, views
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from scheduler.api.v1.serializers import (
    DeeplinkOutputSerializer,
    DeeplinkParamsSerializer,
)
from scheduler.models import Platform

logger = logging.getLogger(__name__)


class DeeplinkFactory:
    @classmethod
    def generate(cls, platform: str, nonce: str) -> str:
        templates = getattr(settings, "AUTH_DEEPLINK_TEMPLATES", {})
        if platform not in templates:
            raise ValueError(f"Invalid platform: {platform}")
        return templates[platform].format(nonce=nonce)


class DeeplinkView(views.APIView):
    permission_classes = [AllowAny]
    resource_name = "deeplink"

    @extend_schema(
        tags=["Authentication"],
        summary="Get deeplink",
        auth=[],
        methods=["GET"],
        parameters=[
            OpenApiParameter(
                name="platform",
                type=str,
                location=OpenApiParameter.PATH,
                enum=Platform.values,
                description="Platform to generate deeplink for",
            )
        ],
        responses={
            200: DeeplinkOutputSerializer(many=False),
        },
    )
    def get(self, request: Request, platform: str):
        """
        Returns a platform-specific deeplink and nonce to initiate authentication via app.
        """
        serializer = DeeplinkParamsSerializer(data={"platform": platform})
        serializer.is_valid(raise_exception=True)
        validated_platform = serializer.validated_data["platform"]

        nonce = str(uuid.uuid4())
        deeplink = DeeplinkFactory.generate(validated_platform, nonce)
        logger.info(f"Generated deeplink for platform {platform} with nonce {nonce}")
        response_serializer = DeeplinkOutputSerializer(
            {"deeplink": deeplink, "nonce": nonce}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)
