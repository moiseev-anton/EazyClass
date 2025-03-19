from django.urls import path
from rest_framework import routers

from .lessons import GroupViewSet

router = routers.DefaultRouter()
router.register(prefix='groups', viewset=GroupViewSet)

# urlpatterns = [
#     path('groups/', GroupViewSet.as_view({'get': 'list'})),
#     path('groups/<int:pk>', GroupViewSet.as_view({'get': 'retrieve'})),
# ]