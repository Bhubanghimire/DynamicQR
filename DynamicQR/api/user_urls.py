from django.urls import include, path

urlpatterns = [
    path("accounts/", include(("accounts.normal_user.urls", "accounts_user"), namespace="accounts_user")),
    path("analytics/", include(("analytics.normal_user.urls", "analytics_user"), namespace="analytics_user")),
    path("", include(("Qr.normal_user.urls", "projects_user"), namespace="projects_user")),
    path("subscriptions/", include(("subscriptions.normal_user.urls", "subscriptions_user"), namespace="subscriptions_user")),

]
