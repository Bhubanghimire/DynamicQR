from django.db.models import F
from django.utils import timezone

from analytics.models import QRAnalytics


class QRAnalyticsService:

    def __init__(self, context):
        self.context = context

    def update(self):
        qr = self.context.qr
        now = getattr(self.context.scan_event, "scanned_at", None) or timezone.now()
        is_unique_scan = bool(self.context.is_unique_scan)

        summary, created = QRAnalytics.objects.get_or_create(
            qr=qr,
            defaults={
                "total_scans": 1,
                "unique_scans": 1 if is_unique_scan else 0,
                "first_scan_at": now,
                "last_scan_at": now,
            },
        )

        if not created:
            QRAnalytics.objects.filter(pk=summary.pk).update(
                total_scans=F("total_scans") + 1,
                unique_scans=F("unique_scans") + (1 if is_unique_scan else 0),
                first_scan_at=summary.first_scan_at or now,
                last_scan_at=now,
            )
            summary.refresh_from_db()

        self.context.qr_analytics = summary
        return summary
