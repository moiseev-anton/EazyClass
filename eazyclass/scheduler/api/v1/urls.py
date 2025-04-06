from django.urls import path, include
from rest_framework import routers

from scheduler.api.v1.views import (
    GroupViewSet,
    CustomTokenRefreshView,
    CustomTokenObtainPairView,
    BotFacultyView,
    BotTeacherView,
    LessonViewSet
)
from scheduler.api.v1.views.auth_views import DeeplinkView, BotAuthView

router = routers.DefaultRouter()
router.register(r'lessons', LessonViewSet, basename='lessons')
router.register(r'bot-faculties', BotFacultyView, basename='bot-faculties')
router.register(r'bot-teachers', BotTeacherView, basename='bot-teachers')
router.register(r'groups', viewset=GroupViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),

    path('deeplink/<str:platform>/', DeeplinkView.as_view(), name='generate-deeplink'),
    path('bot/', BotAuthView.as_view(), name='bot-auth'),
]
