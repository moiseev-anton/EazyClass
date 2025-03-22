"""
URL configuration for eazyclass project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings

from scheduler.api.v1.router import router
from scheduler.api.v1.views import GenerateDeeplinkView, BotAuthView, CheckAuthStatusView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include(router.urls)),
    path('api/v1/generate-deeplink/<str:provider>/', GenerateDeeplinkView.as_view(), name='generate-deeplink'),
    path('api/v1/bot-auth/', BotAuthView.as_view(), name='bot-auth'),
    path('api/v1/check-auth-status/', CheckAuthStatusView.as_view(), name='check-auth-status'),

    path('scheduler/', include('scheduler.urls')),
    path('telegrambot/', include('telegrambot.urls')),
    # path('api/v1/', include('scheduler.api.v1.api_urls'))
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns
