from rest_framework import routers

from scheduler.api.v1.views import GroupViewSet

router = routers.DefaultRouter()
router.register(prefix='groups', viewset=GroupViewSet)
