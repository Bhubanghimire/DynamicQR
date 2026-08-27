from django.contrib import admin

from .models import (
    Invoice,
    Package,
    PackageFeature,
    PackageLimit,
    PackagePlan,
    Payment,
    Subscription,
)

admin.site.register(
    [
        Package,
        PackagePlan,
        PackageLimit,
        PackageFeature,
        Subscription,
        Invoice,
        Payment,
    ]
)
