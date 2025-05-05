import logging

from drf_spectacular.utils import extend_schema
from rest_framework import views
from rest_framework.request import Request
from rest_framework.response import Response

from scheduler.api.permissions import IsHMACAuthenticated
from scheduler.api.v1.serializers import (
    RegisterSerializer,
    UserOutputSerializer,
    AuthResult,
    RegisterWithNonceSerializer,
)
from scheduler.api.v1.views.mixins import JsonApiViewMixin

logger = logging.getLogger(__name__)


class RegisterView(JsonApiViewMixin, views.APIView):
    permission_classes = [IsHMACAuthenticated]
    resource_name = "user"

    @extend_schema(
        tags=["Authentication"],
        summary="Register User",
        methods=["POST"],
        auth=[],
        request=RegisterSerializer,
        responses={
            200: UserOutputSerializer(many=False),
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

        response_data = UserOutputSerializer(auth_result.user).data
        response_data["meta"] = {"created": auth_result.created}

        return Response(response_data, status=auth_result.status_code)


class RegisterWithNonceView(views.APIView):
    permission_classes = [IsHMACAuthenticated]
    resource_name = "user"

    @extend_schema(
        tags=["Authentication"],
        summary="Register with Nonce",
        auth=[],
        methods=["POST"],
        request=RegisterWithNonceSerializer,
        responses={
            200: UserOutputSerializer(many=False),
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
        logger.info("Вызывается общий метод")
        user_response = RegisterView().post(request)

        nonce_value = request.data.get("nonce")
        request._full_data = {"type": "nonce", "nonce": nonce_value}

        from .nonce_view import NonceView

        logger.info("Закрепляем nonce")
        nonce_response = NonceView().post(request)

        user_data: dict = user_response.data
        meta = user_data.setdefault("meta", {})
        meta.update(nonce_response.data)

        return user_response
