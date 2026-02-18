from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework import routers

from scheduler.api.permissions import IsAdmin
from scheduler.api.v1.views import (
    AuthView,
    AuthWithNonceView,
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
    DeeplinkView,
    FacultyViewSet,
    GroupSubscriptionViewSet,
    GroupViewSet,
    LessonViewSet,
    LogoutView,
    NonceView,
    SubscriptionViewSet,
    SocialAccountViewSet,
    TeacherSubscriptionViewSet,
    TeacherViewSet,
    TelegramTokenObtainView,
    UserViewSet,
)

router = routers.DefaultRouter()
router.register(r"lessons", LessonViewSet, basename="lessons")
router.register(r"groups", GroupViewSet, basename="groups")
router.register(r"faculties", FacultyViewSet, basename="faculties")
router.register(r"teachers", TeacherViewSet, basename="teachers")
router.register(r"users", UserViewSet, basename="users")
router.register(r"subscriptions", SubscriptionViewSet, basename="subscription")   # GET, DELETE
router.register(r"social-accounts", SocialAccountViewSet, basename="social-accounts")
router.register(r'group-subscriptions', GroupSubscriptionViewSet, basename='group-subscriptions')  # POST, PATCH, DELETE
router.register(r'teacher-subscriptions', TeacherSubscriptionViewSet, basename='teacher-subscriptions')  # POST, PATCH, DELETE

public_urlpatterns = [
    # роутеры
    path("", include(router.urls)),
    # представления
    path("token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", CustomTokenRefreshView.as_view(), name="token_refresh"),
    path("token/logout/", LogoutView.as_view(), name="token_logout"),
    path("deeplink/<str:platform>/", DeeplinkView.as_view(), name="generate-deeplink"),
]

internal_urlpatterns = [
    path("auth/", AuthView.as_view(), name="auth"),
    path(
        "auth_with_nonce/",
        AuthWithNonceView.as_view(),
        name="auth-with-nonce",
    ),
    path("bind_nonce/", NonceView.as_view(), name="nonce"),
    path("token/twa/", TelegramTokenObtainView.as_view(), name="twa-auth"),
]

urlpatterns = [
    path("", include(public_urlpatterns)),
    path("", include(internal_urlpatterns)),

    # Публичная API схема
    path(
        'schema/',
        SpectacularAPIView.as_view(
            urlconf=public_urlpatterns,
            custom_settings={
                'SCHEMA_PATH_PREFIX_INSERT': '/api/v1',
            }
        ),
        name='schema-public',
    ),
    path(
        'docs/swagger/',
        SpectacularSwaggerView.as_view(url_name='schema-public'),
        name='swagger-public',
    ),
    path(
        'docs/redoc/',
        SpectacularRedocView.as_view(url_name='schema-public'),
        name='redoc-public',
    ),

    # Внутренняя API схема
    path(
        'schema/internal/',
        SpectacularAPIView.as_view(permission_classes=[IsAdmin]),
        name='schema-internal',
    ),
    path(
        'docs/internal/swagger/',
        SpectacularSwaggerView.as_view(url_name='schema-internal'),
        name='swagger-internal',
    ),
    path(
        'docs/internal/redoc/',
        SpectacularRedocView.as_view(url_name='schema-internal'),
        name='redoc-internal',
    ),
]
