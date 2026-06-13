from rest_framework.routers import DefaultRouter
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from accounts.views import AuthViewSet
from analytics.normal_user.views import AnalyticsViewSet
from Qr.normal_user.views import ProjectViewSet

app_name = "accounts_user"

user_qr_router = DefaultRouter()
user_qr_router.register(r'analytics', AnalyticsViewSet, basename='project')
user_qr_router.register(r'analytics1', AnalyticsViewSet, basename='project1')


urlpatterns = [
    path('', include(user_qr_router.urls)),
]
