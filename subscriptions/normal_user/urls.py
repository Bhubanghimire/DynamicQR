from django.urls import path, include
from rest_framework.routers import DefaultRouter
from subscriptions.normal_user.views import DurationViewSet, InvoiceViewSet, PackageViewSet, PaymentViewSet, UsageViewSet

app_name = "accounts_user"

user_qr_router = DefaultRouter()
user_qr_router.register(r'payments', PaymentViewSet, basename='payments')
user_qr_router.register(r'durations', DurationViewSet, basename='durations')
user_qr_router.register(r'packages', PackageViewSet, basename='packages')
user_qr_router.register(r'invoices', InvoiceViewSet, basename='invoices')
user_qr_router.register(r'usage', UsageViewSet, basename='usage')
# user_qr_router.register(r'subscription', SubscriptionViewSet, basename='subscription')
# user_qr_router.register(r'subscription1', SubscriptionViewSet, basename='projsubscription1')


urlpatterns = [
    path('', include(user_qr_router.urls)),
]
