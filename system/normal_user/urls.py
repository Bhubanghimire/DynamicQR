from django.urls import include, path
from rest_framework.routers import DefaultRouter

from system.views import ConfigCategoryViewSet

app_name = "system_user"

system_router = DefaultRouter()
system_router.register(r'config-categories', ConfigCategoryViewSet, basename='config-category')

urlpatterns = [
    path('', include(system_router.urls)),
]
