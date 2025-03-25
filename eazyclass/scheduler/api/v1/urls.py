from django.urls import path, include
from rest_framework import routers

from scheduler.api.v1.views import GroupViewSet, AuthViewSet, CustomTokenRefreshView, CustomTokenObtainPairView

router = routers.DefaultRouter()
router.register(prefix='auth', viewset=AuthViewSet, basename='auth')
router.register(prefix='groups', viewset=GroupViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('/token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),

    # path('deeplink/<str:provider>/', GenerateDeeplinkView.as_view(), name='generate-deeplink'),
    # path('auth-bot/', BotAuthView.as_view(), name='bot-auth'),
    # path('auth-status/', CheckAuthStatusView.as_view(), name='check-auth-status'),
]
