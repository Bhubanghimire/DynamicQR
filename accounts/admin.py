from django.contrib import admin
from accounts.models import OTP, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "first_name", "last_name", "phone", "is_active", "is_staff", "date_joined")
    search_fields = ("email", "first_name", "last_name", "phone")
    list_filter = ("is_active", "is_staff", "gender", "user_type")
    ordering = ("id",)


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "otp", "created_at", "is_used")
    search_fields = ("email", "otp")
    list_filter = ("is_used", "created_at")
    ordering = ("-created_at",)
