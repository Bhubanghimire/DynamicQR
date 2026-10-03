from django.urls import path, include
from rest_framework.routers import DefaultRouter
from analytics.admin_user.views import AnalyticsDashboardViewSet

app_name = "analytics_admin"

router = DefaultRouter()
router.register(r'dashboard', AnalyticsDashboardViewSet, basename='dashboard')

urlpatterns = [
    path('', include(router.urls)),
]
