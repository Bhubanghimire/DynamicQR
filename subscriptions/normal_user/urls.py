from rest_framework.routers import DefaultRouter
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from accounts.views import AuthViewSet
from subscriptions.normal_user.views import SubscriptionViewSet

app_name = "accounts_user"

user_qr_router = DefaultRouter()
user_qr_router.register(r'subscription', SubscriptionViewSet, basename='subscription')
user_qr_router.register(r'subscription1', SubscriptionViewSet, basename='projsubscription1')


urlpatterns = [
    path('', include(user_qr_router.urls)),
]

