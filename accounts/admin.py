from django import forms
from django.db import models
from django.contrib import admin

from accounts.models import ContactUs, FAQ, NotificationPreference, OTP, User, Workspace, BillingAddress


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "full_name",  "phone", "is_active", "is_staff", "date_joined")
    search_fields = ("email", "full_name",  "phone")
    list_filter = ("is_active", "is_staff", "gender", "user_type")
    ordering = ("id",)


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "otp", "created_at", "is_used")
    search_fields = ("email", "otp")
    list_filter = ("is_used", "created_at")
    ordering = ("-created_at",)


@admin.register(ContactUs)
class ContactUsAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "email", "phone", "subject", "created_at")
    search_fields = ("full_name", "email", "phone", "subject", "message")
    ordering = ("-created_at",)


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("id", "question", "is_active", "display_order", "created_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("question", "answer")
    ordering = ("display_order", "id")
    formfield_overrides = {
        models.TextField: {
            "widget": forms.Textarea(attrs={"rows": 12, "cols": 100})
        },
    }


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "scan_alert",
        "weekly_performance",
        "product_updates",
        "security_alerts",
        "updated_at",
    )
    search_fields = ("user__email", "user__full_name")
    list_filter = (
        "scan_alert",
        "weekly_performance",
        "product_updates",
        "security_alerts",
    )
    ordering = ("user__email",)


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ['id',"name"]




@admin.register(BillingAddress)
class BillingAddressAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "full_name",
        "company_name",
        "city",
        "state_province",
        "country",
        "postal_code",
        "phone",
        "updated_at",
    )

    list_filter = (
        "country",
        "state_province",
    )

    search_fields = (
        "user__email",
        "user__username",
        "full_name",
        "company_name",
        "city",
        "postal_code",
        "phone",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "User",
            {
                "fields": ("user",),
            },
        ),
        (
            "Billing Information",
            {
                "fields": (
                    "full_name",
                    "company_name",
                    "phone",
                ),
            },
        ),
        (
            "Address",
            {
                "fields": (
                    "address_line_1",
                    "address_line_2",
                    "city",
                    "state_province",
                    "postal_code",
                    "country",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )