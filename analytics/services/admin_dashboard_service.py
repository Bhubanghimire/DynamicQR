from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, Dict, Any

from django.db.models import Count, Sum, Q
from django.utils import timezone

from accounts.models import User
from Qr.models import QRCode
from analytics.models import ScanEvent
from subscriptions.models import Invoice
from system.models import ConfigChoice

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
    def get_qr_generation_trend(cls, request) -> Dict[str, Any]:
        period = request.query_params.get("period")
        date_range = cls.resolve_date_range(period, request)

        if date_range is None:
            return {
                "data": [],
                "message": "No date range provided. Please specify a period (e.g., today, 30d, custom)."
            }

        start_date = date_range.start_date
        end_date = date_range.end_date

        from Qr.models import QRCode
        from django.db.models import Count
        from django.db.models.functions import TruncDate

        # Count QRs created per day
        qrs = (
            cls._filtered_qrs(request).filter(created_at__date__range=(start_date, end_date))
            .annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        qr_by_date = {row["date"]: row["count"] for row in qrs}

        # Fill gaps to ensure continuous timeline
        timeline = []
        current_date = start_date
        while current_date <= end_date:
            timeline.append({
                "date": current_date.isoformat(),
                "count": qr_by_date.get(current_date, 0)
            })
            current_date += timedelta(days=1)

        return {
            "data": timeline,
            "message": "QR generation trend fetched successfully."
        }

    @classmethod
    def get_qr_type_usage(cls, request) -> Dict[str, Any]:
        qrs = cls._filtered_qrs(request)
        qr_type_counts = {row["qr_type_id"]: row["count"] for row in
                          qrs.values("qr_type_id").annotate(count=Count("id"))}
        total_qr = sum(qr_type_counts.values())

        qr_types = ConfigChoice.objects.filter(
            category__name="qr_type",
        ).order_by("name")
        qr_type = request.query_params.get("qr_type")
        if qr_type:
            qr_types = qr_types.filter(Q(id=qr_type) | Q(name__icontains=qr_type))

        data = []
        for qr_type in qr_types:
            count = qr_type_counts.get(qr_type.id, 0)
            percentage = round((count / total_qr) * 100, 2) if total_qr else 0
            data.append(
                {
                    "qr_type_id": str(qr_type.id),
                    "qr_type": qr_type.name,
                    "count": count,
                    "percentage": percentage,
                }
            )

        return {
            "data": data,
            "message": "QR type usage fetched successfully.",
        }

    @classmethod
    def get_top_performing_qrs(cls, request) -> Dict[str, Any]:
        qrs = (
            cls._filtered_qrs(request).select_related("qr_type")
            .annotate(total_scans=Count("scan_events"))
            .order_by("-total_scans", "name", "id")
        )

        data = [
            {
                "qr_id": str(qr.id),
                "name": qr.name,
                "type": qr.qr_type.name if qr.qr_type else None,
                "total_scans": qr.total_scans,
            }
            for qr in qrs
        ]

        return {
            "data": data,
            "message": "Top performing QR codes fetched successfully.",
        }

    @classmethod
    def get_top_power_users(cls, request) -> Dict[str, Any]:
        from accounts.models import User
        from subscriptions.models import Subscription
        from django.db.models import Count

        # Get top users by QR count and total scans
        # Based on the error message choices, the reverse relation is 'qrcode'
        users = User.objects.all()
        search = request.query_params.get("search")
        if search:
            users = users.filter(Q(email__icontains=search) | Q(full_name__icontains=search) | Q(phone__icontains=search))
        if request.query_params.get("user_id"):
            users = users.filter(id=request.query_params["user_id"])
        if request.query_params.get("status") in {"active", "inactive"}:
            users = users.filter(is_active=request.query_params["status"] == "active")
        top_users = (
            users.annotate(
                qr_count=Count('qrcode', distinct=True),
                total_scans=Count('qrcode__scan_events')
            )
            .order_by('-qr_count', '-total_scans')
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
        scans = cls._filtered_scans(request, scan_filter)
        os_data = (
            scans
            .values('os')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Browser Distribution
        browser_data = (
            scans
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
        packages = Package.objects.all()
        package_status = request.query_params.get("package_status", request.query_params.get("status"))
        if package_status in {"active", "inactive"}:
            packages = packages.filter(is_active=package_status == "active")
        search = request.query_params.get("search")
        if search:
            packages = packages.filter(title__icontains=search)
        package_list = list(packages)

        # 2. Get all active subscriptions to map users to packages
        # Subscription -> PackagePlan -> Package
        subscription_status = request.query_params.get("subscription_status", "active")
        active_subs = Subscription.objects.filter(
            status=subscription_status,
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
        scans = cls._filtered_scans(request, scan_filter).values_list('qr__created_by_id', flat=True)

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

        users = User.objects.filter(date_joined__date__range=(start_date, end_date))
        search = request.query_params.get("search")
        if search:
            users = users.filter(Q(email__icontains=search) | Q(full_name__icontains=search))
        if request.query_params.get("user_id"):
            users = users.filter(id=request.query_params["user_id"])
        if request.query_params.get("status") in {"active", "inactive"}:
            users = users.filter(is_active=request.query_params["status"] == "active")

        registrations = (
            users
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

    @classmethod
    def get_summary(cls, request) -> Dict[str, Any]:
        period = request.query_params.get("period")
        date_range = cls.resolve_date_range(period, request)

        # No period means all-time totals. A recognized period limits each
        # metric to records whose relevant timestamp falls in that range.
        start_date = date_range.start_date if date_range else None
        end_date = date_range.end_date if date_range else None

        user_filter = {}
        if start_date:
            user_filter["date_joined__date__gte"] = start_date
        if end_date:
            user_filter["date_joined__date__lte"] = end_date
        total_users = User.objects.filter(**user_filter).count()

        qr_filter = {}
        if start_date:
            qr_filter["created_at__date__gte"] = start_date
        if end_date:
            qr_filter["created_at__date__lte"] = end_date
        total_qrs = QRCode.objects.filter(**qr_filter).count()

        scan_filter = {}
        if start_date:
            scan_filter["scanned_at__date__gte"] = start_date
        if end_date:
            scan_filter["scanned_at__date__lte"] = end_date
        total_scans = ScanEvent.objects.filter(**scan_filter).count()

        revenue_filter = {"status": "paid"}
        if start_date:
            revenue_filter["issued_at__date__gte"] = start_date
        if end_date:
            revenue_filter["issued_at__date__lte"] = end_date
        total_revenue = Invoice.objects.filter(**revenue_filter).aggregate(
            total=Sum("total")
        )["total"] or 0.0

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
            },
        }

    @classmethod
    def _filtered_qrs(cls, request):
        qrs = QRCode.objects.all()
        search = request.query_params.get("search")
        if search:
            qrs = qrs.filter(Q(name__icontains=search) | Q(short_code__icontains=search) |
                             Q(created_by__email__icontains=search) | Q(created_by__full_name__icontains=search))
        if request.query_params.get("user_id"):
            qrs = qrs.filter(created_by_id=request.query_params["user_id"])
        if request.query_params.get("status") in {"active", "inactive"}:
            qrs = qrs.filter(status=request.query_params["status"] == "active")
        if request.query_params.get("qr_status") in {"active", "inactive"}:
            qrs = qrs.filter(status=request.query_params["qr_status"] == "active")
        if request.query_params.get("qr_type"):
            value = request.query_params["qr_type"]
            qrs = qrs.filter(Q(qr_type_id=value) | Q(qr_type__name__icontains=value))
        return qrs

    @classmethod
    def _filtered_scans(cls, request, filters=None):
        scans = ScanEvent.objects.filter(**(filters or {}))
        if request.query_params.get("user_id"):
            scans = scans.filter(qr__created_by_id=request.query_params["user_id"])
        for param, field in (("country", "country"), ("city", "city"), ("browser", "browser"),
                             ("os", "os"), ("device_type", "device_type"), ("is_bot", "is_bot")):
            value = request.query_params.get(param)
            if value is not None:
                if param == "is_bot":
                    scans = scans.filter(**{field: value.lower() in {"1", "true", "yes"}})
                else:
                    scans = scans.filter(**{f"{field}__icontains": value})
        return scans
