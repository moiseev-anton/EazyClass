import logging

from drf_spectacular.utils import extend_schema
from rest_framework import views
from rest_framework.request import Request
from rest_framework.response import Response

from scheduler.api.mixins import JsonApiMixin
from scheduler.api.permissions import IsHMACAuthenticated
from scheduler.api.v1.serializers import (
    AuthResult,
    AuthSerializer,
    AuthWithNonceSerializer,
    SocialAccountAuthSerializer,
    SocialAccountAuthWithNonceSerializer,
)

logger = logging.getLogger(__name__)


class AuthView(JsonApiMixin, views.APIView):
    permission_classes = [IsHMACAuthenticated]
    resource_name = "social-accounts"
    serializer_class = SocialAccountAuthSerializer

    @extend_schema(
        tags=["Authentication"],
        summary="Register/Auth user",
        methods=["POST"],
        auth=[],
        request=AuthSerializer,
        responses={
            200: serializer_class(many=False),
            # 201: serializer_class(many=False),
            # 400: OpenApiResponse(description="Bad Request"),
            # 403: OpenApiResponse(description="Forbidden (invalid HMAC)"),
        },
    )
    def post(self, request: Request) -> Response:
        """Register or authenticate user"""
        serializer = AuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if request.user.is_authenticated:
            platform = serializer.validated_data["platform"]
            social_id = serializer.validated_data["social_id"]

            social_account = request.user.accounts.get(
                platform=platform,
                social_id=social_id,
            )

            auth_result = AuthResult(
                user=request.user, social_account=social_account, created=False
            )
        else:
            auth_result = serializer.save()
            # важно для возможной обработки nonce в RegisterWithNonceView
            request.user = auth_result.user

        logger.info(
            f"User {auth_result.user.id} {'created' if auth_result.created else 'retrieved'} via bot auth"
        )

        if not auth_result.created:
            serializer.update(auth_result.social_account)

        serializer = self.serializer_class(
            auth_result.social_account, context={"created": auth_result.created}
        )
        response_data = serializer.data
        logger.info(response_data)

        return Response(response_data, status=auth_result.status_code)


class AuthWithNonceView(AuthView):
    # permission_classes = [IsHMACAuthenticated]
    serializer_class = SocialAccountAuthWithNonceSerializer

    @extend_schema(
        tags=["Authentication"],
        summary="Register/Auth user with Nonce",
        auth=[],
        methods=["POST"],
        request=AuthWithNonceSerializer,
        responses={
            200: serializer_class(many=False),
            # 201: serializer_class(many=False),
            # 400: OpenApiResponse(description="Bad Request"),
            # 403: OpenApiResponse(description="Forbidden (invalid HMAC)"),
        },
    )
    def post(self, request: Request) -> Response:
        """
        Register a new user and immediately bind a nonce.
        Used when both registration and nonce binding are needed in a single call.
        """
        # Отделяем nonce от тела изначального запроса
        nonce_value = request.data.pop("nonce")

        auth_response = super().post(request)

        # Подменяем тело запроса и имитируем отдельный фейковый POST запрос к NonceView
        request._full_data = {"type": "nonce", "nonce": nonce_value}
        from .nonce_view import NonceView

        nonce_response = NonceView().post(request)

        # Дополняем результат Auth результатом NonceView
        auth_response.data.update(nonce_response.data)

        # Далее на основании meta_fields сериализатора, указанного в serializer_class
        # рендерер сам сформирует meta ресурса (не документа!)
        return auth_response
