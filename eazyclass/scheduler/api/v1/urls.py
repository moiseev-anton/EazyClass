from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from rest_framework import routers

from scheduler.api.v1.views import (
    GroupViewSet,
    CustomTokenRefreshView,
    CustomTokenObtainPairView,
    # BotFacultyView,
    BotTeacherView,
    LessonViewSet,
    SubscriptionViewSet,
)
from scheduler.api.v1.views.auth_views import DeeplinkView, BotAuthView

router = routers.DefaultRouter()
router.register(r"subscriptions", SubscriptionViewSet, basename="subscription")
router.register(r"lessons", LessonViewSet, basename="lessons")
# router.register(r"bot-faculties", BotFacultyView, basename="bot-faculties")
router.register(r"bot-teachers", BotTeacherView, basename="bot-teachers")
router.register(r"groups", GroupViewSet, basename="groups")


urlpatterns = [
    # роутеры
    path("", include(router.urls)),

    # представления
    path("token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", CustomTokenRefreshView.as_view(), name="token_refresh"),
    path("deeplink/<str:platform>/", DeeplinkView.as_view(), name="generate-deeplink"),
    path("bot/", BotAuthView.as_view(), name="bot-auth"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui",),
    path("schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
