import logging

from rest_framework.permissions import BasePermission

logger = logging.getLogger(__name__)

class IsOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.user == request.user

class IsSelf(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user == obj

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)


class IsAdminOrReadOnly(BasePermission):
    """Разрешает чтение всем, изменение — только админам."""
    def has_permission(self, request, view):
        return request.method in ['GET', 'HEAD', 'OPTIONS'] or request.user.is_staff


class IsHMACAuthenticated(BasePermission):
    def has_permission(self, request, view):
        return request.auth == "hmac"

