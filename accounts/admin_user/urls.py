from django.urls import path, include
from rest_framework.routers import DefaultRouter
from accounts.admin_user.views import UserAdminViewSet

app_name = "accounts_admin"

account_router = DefaultRouter()
account_router.register(r'users', UserAdminViewSet, basename='users')

urlpatterns = [
    path('', include(account_router.urls)),
]
