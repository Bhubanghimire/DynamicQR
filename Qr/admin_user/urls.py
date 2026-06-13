from django.urls import path, include
from rest_framework.routers import DefaultRouter
from accounts.views import AuthViewSet

app_name = "accounts_admin"

account_router = DefaultRouter()
account_router.register(r'auth', AuthViewSet, basename='auth')
# account_router.register(r'main_dashboard', MainViewSet, basename='main_dashboard')
# account_router.register(r'profile', ProfileViewSet, basename='profile')
# account_router.register(r'chat', ChatViewSet, basename='chat')
# account_router.register(r'fcm_token', FCMDeviceViewSet, basename='fcm_token')
# account_router.register(r'dashboard', GlobalSearchViewSet, basename='global_search')

urlpatterns = [
    path('', include(account_router.urls)),
]
