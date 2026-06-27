from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from rest_framework.renderers import JSONOpenAPIRenderer
from rest_framework.permissions import AllowAny
from rest_framework.schemas import get_schema_view
from django.views.generic import TemplateView

schema_view = get_schema_view(title="DynamicOCR API", description="OpenAPI schema for the DynamicOCR backend.",
                              version="1.1", public=True, permission_classes=[AllowAny], authentication_classes=[],
                              renderer_classes=[JSONOpenAPIRenderer], )

swagger_view = TemplateView.as_view(
    template_name="swagger-ui.html",
    extra_context={
        "schema_url": "/api/schema/",
        "page_title": "DynamicOCR Swagger",
    },
)
def home(request):
    return HttpResponse("DynamicOCR API is running.")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home),

    # path("api/v1.1/admin/", include(("DynamicOCR.api.admin_urls", "api_admin"), namespace="api_admin")),
    path("api/v1.1/user/", include(("DynamicOCR.api.user_urls", "api_user"), namespace="api_user")),
    path("api/schema/", schema_view, name="api-schema"),
    path("swagger/", swagger_view, name="swagger-ui"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
