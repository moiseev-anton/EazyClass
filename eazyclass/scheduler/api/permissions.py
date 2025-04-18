from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.user == request.user


class IsAdminOrReadOnly(BasePermission):
    """Разрешает чтение всем, изменение — только админам."""
    def has_permission(self, request, view):
        return request.method in ['GET', 'HEAD', 'OPTIONS'] or request.user.is_staff
