import logging

from drf_spectacular.utils import extend_schema
from rest_framework import views
from rest_framework.request import Request
from rest_framework.response import Response

from scheduler.api.permissions import IsHMACAuthenticated
from scheduler.api.v1.serializers import (
    RegisterSerializer,
    UserOutputSerializer,
    UserOutputWithNonceSerializer,
    AuthResult,
    RegisterWithNonceSerializer,
)
from scheduler.api.mixins import JsonApiMixin

logger = logging.getLogger(__name__)


class RegisterView(JsonApiMixin, views.APIView):
    # permission_classes = [IsHMACAuthenticated]
    resource_name = "user"
    serializer_class = UserOutputSerializer

    @extend_schema(
        tags=["Authentication"],
        summary="Register User",
        methods=["POST"],
        auth=[],
        request=RegisterSerializer,
        responses={
            200: serializer_class(many=False),
            # 201: UserOutputSerializer(many=False),
            # 400: OpenApiResponse(description="Bad Request"),
            # 403: OpenApiResponse(description="Forbidden (invalid HMAC)"),
        },
    )
    def post(self, request: Request) -> Response:
        """Register or authenticate user"""
        if request.user.is_authenticated:
            auth_result = AuthResult(user=request.user, created=False)
        else:
            serializer = RegisterSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            auth_result = serializer.save()
            logger.info(
                f"User {auth_result.user.id} {'created' if auth_result.created else 'retrieved'} via bot auth"
            )
            request.user = auth_result.user  # важно для обработки nonce

        serializer = self.serializer_class(auth_result.user, context={"created": auth_result.created})
        response_data = serializer.data
        logger.info(response_data)

        return Response(response_data, status=auth_result.status_code)


class RegisterWithNonceView(RegisterView):
    # permission_classes = [IsHMACAuthenticated]
    resource_name = "user"
    serializer_class = UserOutputWithNonceSerializer

    @extend_schema(
        tags=["Authentication"],
        summary="Register with Nonce",
        auth=[],
        methods=["POST"],
        request=RegisterWithNonceSerializer,
        responses={
            200: UserOutputWithNonceSerializer(many=False),
            # 201: UserOutputSerializer(many=False),
            # 400: OpenApiResponse(description="Bad Request"),
            # 403: OpenApiResponse(description="Forbidden (invalid HMAC)"),
        },
    )
    def post(self, request: Request) -> Response:
        """
        Register a new user and immediately bind a nonce.
        Used when both registration and nonce binding are needed in a single call.
        """
        user_response = super().post(request)

        # Имитируем отдельный фейковый запрос к NonceView
        nonce_value = request.data.get("nonce")
        request._full_data = {"type": "nonce", "nonce": nonce_value}

        from .nonce_view import NonceView
        nonce_response = NonceView().post(request)

        # Объединяем результаты Register и NonceView
        # Далее на основании meta_fields сериализатора рендерер сам сформирует meta ресурса (не документа!)
        user_data: dict = user_response.data
        user_data.update(nonce_response.data)

        return user_response
