from rest_framework.routers import DefaultRouter
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from accounts.views import AuthViewSet
# from analytics.normal_user.views import AnalyticsViewSet
from Qr.normal_user.views import ProjectViewSet
from analytics.normal_user.views import AnalyticsDashboardViewSet, QRAnalyticsViewSet

app_name = "accounts_user"

user_qr_router = DefaultRouter()
user_qr_router.register(r'dashboard', AnalyticsDashboardViewSet, basename='dashboard')
user_qr_router.register(r'details', QRAnalyticsViewSet, basename='details')


urlpatterns = [
    path('', include(user_qr_router.urls)),
]
