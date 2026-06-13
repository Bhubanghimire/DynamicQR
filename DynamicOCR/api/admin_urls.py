from django.urls import include, path

urlpatterns = [
    path("accounts/", include(("accounts.admin_user.urls", "accounts_admin"), namespace="accounts_admin")),
    path("analytics/", include(("analytics.admin_user.urls", "analytics_admin"), namespace="analytics_admin")),
    path("projects/", include(("projects.admin_user.urls", "projects_admin"), namespace="projects_admin")),
    path("subscriptions/", include(("subscriptions.admin_user.urls", "subscriptions_admin"), namespace="subscriptions_admin")),
    path("system/", include(("system.admin_user.urls", "system_admin"), namespace="system_admin")),
]
