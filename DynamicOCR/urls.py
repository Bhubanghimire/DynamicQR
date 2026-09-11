from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from rest_framework.renderers import JSONOpenAPIRenderer
from rest_framework.permissions import AllowAny
from rest_framework.schemas import get_schema_view
from django.views.generic import TemplateView
from allauth.socialaccount.providers.google.views import oauth2_login, oauth2_callback
from subscriptions.webhooks import dodo_webhook
from django.http import JsonResponse

# Base schema view for the project
base_schema_view = get_schema_view(
    title="DynamicOCR API",
    description="OpenAPI schema for the DynamicOCR backend.",
    version="1.1",
    public=True,
    permission_classes=[AllowAny],
    authentication_classes=[],
    renderer_classes=[JSONOpenAPIRenderer],
)

def schema_filter_view(request):
    # Call the base schema view to get the full OpenAPI schema
    response = base_schema_view(request)

    # Ensure we have a response with data
    if not response or not hasattr(response, 'data'):
        return response

    schema = response.data
    if not isinstance(schema, dict):
        return response

    full_path = request.get_full_path()

    if '/api/admin/schema/' in full_path:
        # Admin view: Only keep paths that start with /api/v1.1/admin/ or contain /admin/
        schema['paths'] = {
            k: v for k, v in schema.get('paths', {}).items()
            if k.startswith('/api/v1.1/admin/') or '/admin/' in k
        }
        schema['info'] = schema.get('info', {})
        schema['info']['title'] = "DynamicOCR Admin API"
        schema['info']['description'] = "Administrative endpoints for DynamicOCR"
    else:
        # User view: Remove paths that start with /api/v1.1/admin/ or contain /admin/
        schema['paths'] = {
            k: v for k, v in schema.get('paths', {}).items()
            if not (k.startswith('/api/v1.1/admin/') or '/admin/' in k)
        }
        schema['info'] = schema.get('info', {})
        schema['info']['title'] = "DynamicOCR User API"
        schema['info']['description'] = "User-facing endpoints for DynamicOCR"

    return JsonResponse(schema)

swagger_view = TemplateView.as_view(
    template_name="swagger-ui.html",
    extra_context={
        "schema_url": "/api/schema/",
        "page_title": "DynamicOCR Swagger - User APIs",
    },
)

admin_swagger_view = TemplateView.as_view(
    template_name="swagger-ui.html",
    extra_context={
        "schema_url": "/api/admin/schema/",
        "page_title": "DynamicOCR Admin Swagger",
    },
)

def home(request):
    return HttpResponse("DynamicOCR API is running.")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home),
    path("api/v1.1/user/accounts/allauth/google/login/", oauth2_login, name="google_login"),
    path("api/v1.1/user/accounts/allauth/google/login/callback/", oauth2_callback, name="google_callback"),
    path("api/v1.1/user/accounts/allauth/", include("allauth.socialaccount.urls")),
    path("api/webhook/dodo/", dodo_webhook, name="dodo_webhook"),

    path("api/v1.1/admin/", include(("DynamicOCR.api.admin_urls", "api_admin"), namespace="api_admin")),
    path("api/category/", include(("system.normal_user.urls", "system_user"), namespace="system_user")),
    path("api/v1.1/user/", include(("DynamicOCR.api.user_urls", "api_user"), namespace="api_user")),
    path("api/schema/", schema_filter_view, name="api-schema"),
    path("swagger/", swagger_view, name="swagger-ui"),
    path("api/admin/schema/", schema_filter_view, name="admin-api-schema"),
    path("admin/swagger/", admin_swagger_view, name="admin-swagger-ui"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
