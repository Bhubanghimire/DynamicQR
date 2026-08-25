from django.contrib import admin
from Qr.models import QRCode, Project, QRCodeData, QRDesign, QRSchedule, QRScanSetting, QrMedia, MediaItem, Invitations, SharePermissions, TemplateDesign


# Register your models here.
@admin.register(Project)
class ConfigChoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', "created_at", "updated_at")


@admin.register(QRCode)
class QRCodeAdmin(admin.ModelAdmin):
    list_display = ('id', 'short_code', 'name', 'qr_type', 'link_name', 'status', "created_at", "updated_at")


@admin.register(QRCodeData)
class QRCodeDataAdmin(admin.ModelAdmin):
    list_display = ['id', "qr_code", "created_at", "updated_at"]


@admin.register(QRSchedule)
class QRScheduleAdmin(admin.ModelAdmin):
    list_display = ['id', "qr_code", "created_at", "updated_at"]


@admin.register(QRScanSetting)
class QRScanSettingAdmin(admin.ModelAdmin):
    list_display = ['id', "qr_code", "created_at", "updated_at"]


@admin.register(QRDesign)
class QRDesignAdmin(admin.ModelAdmin):
    list_display = ['id', "qr_code", "created_at", "updated_at"]


@admin.register(QrMedia)
class QrMediaAdmin(admin.ModelAdmin):
    list_display = ['id', "qr_code", "created_at", "updated_at"]


@admin.register(MediaItem)
class MediaItemAdmin(admin.ModelAdmin):
    list_display = ['id', "qr_media", "created_at", "updated_at"]


@admin.register(Invitations)
class InvitationsAdmin(admin.ModelAdmin):
    list_display = ["id", "email", "created_at", "updated_at"]


@admin.register(SharePermissions)
class SharePermissionsAdmin(admin.ModelAdmin):
    list_display = ['id', "user_id", "created_at", "updated_at"]



from django.contrib import admin

from .models import QRImportJob


@admin.register(QRImportJob)
class QRImportJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "project",
        "qr_type",
        "status",
        "total_rows",
        "processed_rows",
        "successful_rows",
        "failed_rows",
        "progress",
        "created_at",
        "started_at",
        "completed_at",
    )

    list_filter = (
        "status",
        "qr_type",
        "project",
        "created_at",
    )

    search_fields = (
        "id",
        "user__email",
        "project__name",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
    )

    ordering = ("-created_at",)

@admin.register(TemplateDesign)
class TemplateDesignAdmin(admin.ModelAdmin):
    list_display = (
        "id","qr_code","created_at","updated_at",
    )