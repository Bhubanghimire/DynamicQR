from django.contrib import admin
from .models import (
    AnalyticsDimension,
    AnalyticsTime,
    QRAnalytics,
    ScanEvent,
    Visitor,
)


@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = ("visitor_hash", "first_seen", "last_seen", "total_scans", "created_at", "updated_at")
    search_fields = ("visitor_hash",)
    list_filter = ("first_seen", "last_seen", "created_at", "updated_at")


@admin.register(QRAnalytics)
class QRAnalyticsAdmin(admin.ModelAdmin):
    list_display = ("qr", "total_scans", "unique_scans", "first_scan_at", "last_scan_at", "created_at", "updated_at")
    search_fields = ("qr__id", "qr__name")
    list_filter = ("created_at", "updated_at", "first_scan_at", "last_scan_at")


@admin.register(ScanEvent)
class ScanEventAdmin(admin.ModelAdmin):
    list_display = ("qr", "visitor", "scanned_at", "ip_address", "country_code", "city", "browser", "os", "device_type", "is_bot")
    search_fields = ("qr__id", "qr__name", "visitor__visitor_hash", "ip_address", "country", "city", "browser", "os")
    list_filter = ("scanned_at", "country_code", "country", "city", "browser", "os", "device_type", "is_bot")


@admin.register(AnalyticsTime)
class AnalyticsTimeAdmin(admin.ModelAdmin):
    list_display = ("qr", "date", "hour", "total_scans", "unique_scans")
    search_fields = ("qr__id", "qr__name")
    list_filter = ("date", "hour")


@admin.register(AnalyticsDimension)
class AnalyticsDimensionAdmin(admin.ModelAdmin):
    list_display = ("qr", "dimension_type", "value", "parent", "total_scans", "unique_scans")
    search_fields = ("qr__id", "qr__name", "dimension_type", "value", "parent")
    list_filter = ("dimension_type", "parent")
