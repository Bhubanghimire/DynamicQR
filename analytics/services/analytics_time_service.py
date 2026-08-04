from django.db.models import F
from django.utils import timezone

from analytics.models import AnalyticsTime


class AnalyticsTimeService:

    def __init__(self, context):
        self.context = context

    def update(self):
        scanned_at = getattr(self.context.scan_event, "scanned_at", None) or timezone.now()
        scan_date = scanned_at.date()
        scan_hour = scanned_at.hour
        is_unique_scan = bool(self.context.is_unique_scan)

        self.context.scan_date = scan_date
        self.context.scan_hour = scan_hour

        daily, created = AnalyticsTime.objects.get_or_create(
            qr=self.context.qr,
            date=scan_date,
            hour=None,
            defaults={
                "total_scans": 1,
                "unique_scans": 1 if is_unique_scan else 0,
            },
        )
        if not created:
            AnalyticsTime.objects.filter(pk=daily.pk).update(
                total_scans=F("total_scans") + 1,
                unique_scans=F("unique_scans") + (1 if is_unique_scan else 0),
            )
            daily.refresh_from_db()

        hourly, created = AnalyticsTime.objects.get_or_create(
            qr=self.context.qr,
            date=scan_date,
            hour=scan_hour,
            defaults={
                "total_scans": 1,
                "unique_scans": 1 if is_unique_scan else 0,
            },
        )
        if not created:
            AnalyticsTime.objects.filter(pk=hourly.pk).update(
                total_scans=F("total_scans") + 1,
                unique_scans=F("unique_scans") + (1 if is_unique_scan else 0),
            )
            hourly.refresh_from_db()

        self.context.analytics_time_daily = daily
        self.context.analytics_time_hourly = hourly
        return daily, hourly
