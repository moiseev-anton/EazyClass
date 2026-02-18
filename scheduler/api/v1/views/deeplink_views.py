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
from scheduler.api.mixins import PlainApiViewMixin
from scheduler.models.social_account_model import Platform

logger = logging.getLogger(__name__)


class DeeplinkFactory:
    @classmethod
    def generate(cls, platform: str, nonce: str) -> dict:
        platforms = getattr(settings, "AUTH_PLATFORMS", {})
        config = platforms.get(platform)

        if not config:
            raise ValueError(f"Invalid platform: {platform}")

        deeplink = config["deeplink_template"].format(nonce=nonce)

        return {
            "platform": platform,
            "deeplink": deeplink,
            "bot_url": config["bot_url"],
            "bot_username": config["bot_username"],
        }


class DeeplinkView(PlainApiViewMixin, views.APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Authentication"],
        summary="Get deeplink (non-JSON:API)",
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

        nonce = uuid.uuid4()

        data = DeeplinkFactory.generate(validated_platform, str(nonce))
        response_serializer = DeeplinkOutputSerializer({**data, "nonce": nonce})

        logger.debug(
            "Generated deeplink",
            extra={
                "platform": validated_platform,
                "nonce": str(nonce),
            },
        )

        return Response(response_serializer.data, status=status.HTTP_200_OK)
