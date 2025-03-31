from django.urls import path, include
from rest_framework import routers

from scheduler.api.v1.views import GroupViewSet, CustomTokenRefreshView, CustomTokenObtainPairView, BotFacultyView
from scheduler.api.v1.views.views import DeeplinkView, BotAuthView

router = routers.DefaultRouter()
router.register(r'bot-faculties', BotFacultyView, basename='bot-faculties')
router.register(r'groups', viewset=GroupViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),

    path('deeplink/<str:provider>/', DeeplinkView.as_view(), name='generate-deeplink'),
    path('bot/', BotAuthView.as_view(), name='bot-auth'),
]
