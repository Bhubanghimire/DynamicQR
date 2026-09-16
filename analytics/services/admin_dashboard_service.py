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
    def get_top_power_users(cls, request) -> Dict[str, Any]:
        from accounts.models import User
        from subscriptions.models import Subscription
        from django.db.models import Count

        # Get top users by QR count and total scans
        # Based on the error message choices, the reverse relation is 'qrcode'
        top_users = (
            User.objects.annotate(
                qr_count=Count('qrcode', distinct=True),
                total_scans=Count('qrcode__scan_events')
            )
            .order_by('-qr_count', '-total_scans')[:20]
        )

        power_users = []
        for user in top_users:
            # Get current active plan
            sub = Subscription.get_active_subscription_for_user(user)
            plan_name = sub.package_plan.package.title if sub else "No Active Plan"

            power_users.append({
                "name": user.full_name,
                "email": user.email,
                "current_plan": plan_name,
                "qr_count": user.qr_count,
                "total_scans": user.total_scans,
            })

        return {
            "data": power_users,
            "message": "Top power user accounts fetched successfully."
        }

    @classmethod
    def get_os_browser_distribution(cls, request) -> Dict[str, Any]:
        period = request.query_params.get("period")
        date_range = cls.resolve_date_range(period, request)

        from analytics.models import ScanEvent
        from django.db.models import Count

        scan_filter = {}
        if date_range:
            scan_filter['scanned_at__date__gte'] = date_range.start_date
            scan_filter['scanned_at__date__lte'] = date_range.end_date

        # OS Distribution
        os_data = (
            ScanEvent.objects.filter(**scan_filter)
            .values('os')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Browser Distribution
        browser_data = (
            ScanEvent.objects.filter(**scan_filter)
            .values('browser')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Format the data, handling empty/null values as "Unknown"
        def format_distribution(queryset, field_name):
            result = []
            for item in queryset:
                name = item[field_name] or "Unknown"
                result.append({
                    "name": name,
                    "count": item['count']
                })
            return result

        return {
            "data": {
                "os": format_distribution(os_data, 'os'),
                "browser": format_distribution(browser_data, 'browser'),
            },
            "message": "OS and Browser distribution fetched successfully."
        }

    @classmethod
    def get_plan_metrics(cls, request) -> Dict[str, Any]:
        period = request.query_params.get("period")
        date_range = cls.resolve_date_range(period, request)

        from subscriptions.models import Package, Subscription
        from analytics.models import ScanEvent
        from django.db.models import Count

        # 1. Get all active packages
        packages = Package.objects.filter(is_active=True)
        package_list = list(packages)

        # 2. Get all active subscriptions to map users to packages
        # Subscription -> PackagePlan -> Package
        active_subs = Subscription.objects.filter(
            status='active',
            package_plan__package__is_active=True
        ).values('user_id', 'package_plan__package_id')

        user_to_package_map = {sub['user_id']: sub['package_plan__package_id'] for sub in active_subs}

        # 3. Calculate user count per package
        package_user_counts = {}
        for sub in active_subs:
            pkg_id = sub['package_plan__package_id']
            package_user_counts[pkg_id] = package_user_counts.get(pkg_id, 0) + 1

        # 4. Calculate scan count per package
        scan_filter = {}
        if date_range:
            scan_filter['scanned_at__date__gte'] = date_range.start_date
            scan_filter['scanned_at__date__lte'] = date_range.end_date

        # Get scans and their creator (User)
        scans = ScanEvent.objects.filter(**scan_filter).values_list('qr__created_by_id', flat=True)

        package_scan_counts = {}
        for creator_id in scans:
            pkg_id = user_to_package_map.get(creator_id)
            if pkg_id:
                package_scan_counts[pkg_id] = package_scan_counts.get(pkg_id, 0) + 1

        # 5. Assemble final data
        metrics = []
        for pkg in package_list:
            metrics.append({
                "package": pkg.title,
                "user_count": package_user_counts.get(pkg.id, 0),
                "scan_count": package_scan_counts.get(pkg.id, 0),
            })

        return {
            "data": metrics,
            "message": "Plan metrics fetched successfully."
        }

    @classmethod
    def get_user_activities(cls, request) -> Dict[str, Any]:
        period = request.query_params.get("period")
        date_range = cls.resolve_date_range(period, request)

        if date_range is None:
            return {
                "data": [],
                "message": "No date range provided. Please specify a period (e.g., today, 30d, custom)."
            }

        start_date = date_range.start_date
        end_date = date_range.end_date

        # Count users registered per day
        from accounts.models import User
        from django.db.models import Count
        from django.db.models.functions import TruncDate

        registrations = (
            User.objects.filter(date_joined__date__range=(start_date, end_date))
            .annotate(date=TruncDate("date_joined"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        reg_by_date = {row["date"]: row["count"] for row in registrations}

        # Fill gaps to ensure continuous timeline
        timeline = []
        current_date = start_date
        while current_date <= end_date:
            timeline.append({
                "date": current_date.isoformat(),
                "count": reg_by_date.get(current_date, 0)
            })
            current_date += timedelta(days=1)

        return {
            "data": timeline,
            "message": "User registration activities fetched successfully."
        }
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
