import logging

from drf_spectacular.utils import extend_schema
from rest_framework import status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from scheduler.api.v1.serializers import (
    NonceSerializer,
    NonceBindOutputSerializer,
)

logger = logging.getLogger(__name__)


class NonceView(views.APIView):
    permission_classes = [IsAuthenticated]
    resource_name = "nonce"

    @extend_schema(
        tags=["Authentication"],
        summary="Bind Nonce",
        auth=[],
        methods=["POST"],
        request=NonceSerializer,
        responses={
            200: NonceBindOutputSerializer(many=False),
            # 400: OpenApiResponse(description="Bad Request"),
            # 403: OpenApiResponse(description="Forbidden")
        },
    )
    def post(self, request: Request) -> Response:
        """
        Bind a one-time nonce to the authenticated user.
        Requires a valid nonce in the request body.
        """
        user_id = str(request.user.id)
        serializer = NonceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        nonce_status = serializer.save_nonce(user_id=user_id, timeout=300)

        output_serializer = NonceBindOutputSerializer({"nonce_status": nonce_status})
        return Response(output_serializer.data, status=status.HTTP_200_OK)
