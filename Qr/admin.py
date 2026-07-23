from django.contrib import admin
from Qr.models import QRCode, Project, QRCodeData, QRDesign, QRSchedule, QRScanSetting, QrMedia, MediaItem


# Register your models here.
@admin.register(Project)
class ConfigChoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', "created_at", "updated_at")


@admin.register(QRCode)
class QRCodeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'status', "created_at", "updated_at")


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
