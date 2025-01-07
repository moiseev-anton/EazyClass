from django.urls import path

from scheduler.views.base_views import home_view

urlpatterns = [
    path('test/', home_view, name='test'),
    path('schedule/', home_view, name='test'),
    path('list/', home_view, name='test'),
    path('notifications/', home_view, name='test'),
]