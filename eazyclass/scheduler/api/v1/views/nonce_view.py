import logging

from drf_spectacular.utils import extend_schema, OpenApiResponse, inline_serializer
from rest_framework import status, views, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from scheduler.api.exceptions import custom_exception_handler
from scheduler.api.v1.serializers import NonceSerializer
from scheduler.api.mixins import PlainApiViewMixin

logger = logging.getLogger(__name__)


class NonceView(PlainApiViewMixin, views.APIView):
    permission_classes = [IsAuthenticated]
    exception_handler = custom_exception_handler
    resource_name = "nonce"

    @extend_schema(
        tags=["Authentication"],
        summary="Bind nonce (non-JSON:API)",
        auth=[],
        methods=["POST"],
        request={"application/json": NonceSerializer},
        responses={
            200: OpenApiResponse(
                        response=inline_serializer(
                            name="NonceResponse",
                            fields={"nonce_status": serializers.CharField()},
                        ),
                    ),
        }
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

        return Response({"nonce_status": nonce_status}, status=status.HTTP_200_OK)
