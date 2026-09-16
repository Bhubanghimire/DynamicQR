from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, Dict, Any

from django.db.models import Sum
from django.utils import timezone

from accounts.models import User
from Qr.models import QRCode
from analytics.models import ScanEvent
from subscriptions.models import Invoice

@dataclass(frozen=True)
class DateRange:
    start_date: Optional[date]
    end_date: Optional[date]

class AdminDashboardService:
    PERIOD_MAP = {
        "today": 0,
        "yesterday": 1,
        "7d": 7,
        "30d": 30,
        "90d": 90,
        "365d": 365,
    }

    @classmethod
    def resolve_date_range(cls, period: Optional[str], request) -> Optional[DateRange]:
        today = timezone.localdate()

        if not period:
            return None

        if period == "today":
            return DateRange(start_date=today, end_date=today)

        if period == "yesterday":
            day = today - timedelta(days=1)
            return DateRange(start_date=day, end_date=day)

        if period in cls.PERIOD_MAP:
            days = cls.PERIOD_MAP[period]
            start_date = today - timedelta(days=days - 1)
            return DateRange(start_date=start_date, end_date=today)

        if period == "custom":
            start_date_str = request.query_params.get("start_date")
            end_date_str = request.query_params.get("end_date")
            if not start_date_str or not end_date_str:
                return None
            try:
                start_date = date.fromisoformat(start_date_str)
                end_date = date.fromisoformat(end_date_str)
            except ValueError:
                return None
            return DateRange(start_date=start_date, end_date=end_date)

        return None

    @classmethod
    def get_summary(cls, request) -> Dict[str, Any]:
        period = request.query_params.get("period")
        date_range = cls.resolve_date_range(period, request)

        # Default range: all time if no period provided
        start_date = date_range.start_date if date_range else None
        end_date = date_range.end_date if date_range else None

        # Total Users
        user_filter = {}
        if start_date: user_filter['date_joined__date__gte'] = start_date
        if end_date: user_filter['date_joined__date__lte'] = end_date
        total_users = User.objects.filter(**user_filter).count()

        # Total QR Codes
        qr_filter = {}
        if start_date: qr_filter['created_at__date__gte'] = start_date
        if end_date: qr_filter['created_at__date__lte'] = end_date
        total_qrs = QRCode.objects.filter(**qr_filter).count()

        # Total Scans
        scan_filter = {}
        if start_date: scan_filter['scanned_at__date__gte'] = start_date
        if end_date: scan_filter['scanned_at__date__lte'] = end_date
        total_scans = ScanEvent.objects.filter(**scan_filter).count()

        # Total Revenue
        revenue_filter = {'status': 'paid'}
        if start_date: revenue_filter['issued_at__date__gte'] = start_date
        if end_date: revenue_filter['issued_at__date__lte'] = end_date
        revenue_data = Invoice.objects.filter(**revenue_filter).aggregate(total=Sum('total'))
        total_revenue = revenue_data['total'] or 0.0

        return {
            "total_scans": total_scans,
            "total_users": total_users,
            "total_qr_codes": total_qrs,
            "total_revenue": float(total_revenue),
            "currency": "NPR",
            "filter": {
                "period": period,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
            }
        }
