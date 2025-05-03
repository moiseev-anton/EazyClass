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
    LessonViewSet,
    SubscriptionViewSet,
    TeacherViewSet,
    UserViewSet,
    DeeplinkView,
    RegisterView,
    NonceView,
    RegisterWithNonceView,
)

router = routers.DefaultRouter()
router.register(r"subscriptions", SubscriptionViewSet, basename="subscription")
router.register(r"lessons", LessonViewSet, basename="lessons")
router.register(r"groups", GroupViewSet, basename="groups")
router.register(r"teachers", TeacherViewSet, basename="teachers")
router.register(r"users", UserViewSet, basename="users")


urlpatterns = [
    # роутеры
    path("", include(router.urls)),
    # представления
    path("token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", CustomTokenRefreshView.as_view(), name="token_refresh"),
    path("deeplink/<str:platform>/", DeeplinkView.as_view(), name="generate-deeplink"),
    path("register/", RegisterView.as_view(), name="register"),
    path(
        "register_with_nonce/",
        RegisterWithNonceView.as_view(),
        name="register-with-nonce",
    ),
    path("bind_nonce/", NonceView.as_view(), name="nonce"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"
    ),
]
