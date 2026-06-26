from rest_framework.routers import DefaultRouter
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from accounts.views import AuthViewSet
from Qr.normal_user.views import ProjectViewSet

app_name = "accounts_user"

user_qr_router = DefaultRouter()
user_qr_router.register(r'project', ProjectViewSet, basename='project')
user_qr_router.register(r'qr1', ProjectViewSet, basename='project1')


urlpatterns = [
    path('', include(user_qr_router.urls)),
]
