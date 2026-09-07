from django.views.generic import TemplateView
from rest_framework.routers import DefaultRouter
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from accounts.views import AuthViewSet
from Qr.normal_user.views import ProjectViewSet, QRCodeViewSet, QRRecycleBinViewSet, TemplateViewSet, VideoViewSet, ProjectInvitationViewSet, \
    QRCodeBulkImportViewSet, CustomDomainViewSet

app_name = "accounts_user"

user_qr_router = DefaultRouter()
user_qr_router.register(r'project', ProjectViewSet, basename='project')
user_qr_router.register(r'project-invitation', ProjectInvitationViewSet, basename='invitation')
user_qr_router.register(r'qr', QRCodeViewSet, basename='Qr')
user_qr_router.register(r'qr/recycle-bin', QRRecycleBinViewSet, basename='qr-recycle-bin')
user_qr_router.register(r'template', TemplateViewSet, basename='template_design')
user_qr_router.register(r'qr/video', VideoViewSet, basename='video')
user_qr_router.register(r'bulk_import', QRCodeBulkImportViewSet, basename='import')
user_qr_router.register(r'domains', CustomDomainViewSet, basename='custom-domains')


urlpatterns = [
    path('', include(user_qr_router.urls)),
]
