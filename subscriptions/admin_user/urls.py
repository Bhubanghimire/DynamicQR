from django.urls import path, include
from rest_framework.routers import DefaultRouter
from subscriptions.admin_user.views import DurationViewSet, PackageViewSet, PackagePlanViewSet, InvoiceViewSet

app_name = "subscriptions_admin"

subscription_router = DefaultRouter()
subscription_router.register(r'durations', DurationViewSet, basename='durations')
subscription_router.register(r'packages', PackageViewSet, basename='packages')
subscription_router.register(r'package-plans', PackagePlanViewSet, basename='package-plans')
subscription_router.register(r'invoices', InvoiceViewSet, basename='invoices')

urlpatterns = [
    path('', include(subscription_router.urls)),
]
