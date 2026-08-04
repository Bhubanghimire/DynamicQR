from datetime import timedelta

from django.db.models import Avg, Count, Max, Sum, Min
from django.db.models.functions import Coalesce, ExtractHour, ExtractWeekDay, TruncDate

from analytics.models import AnalyticsTime, QRAnalytics, ScanEvent
from analytics.services.dashboard_summary_service import DateRange
from analytics.services.dashboard_summary_service import DashboardSummaryService


WEEKDAY_NAMES = {
    1: "Sunday",
    2: "Monday",
    3: "Tuesday",
    4: "Wednesday",
    5: "Thursday",
    6: "Friday",
    7: "Saturday",
}


class QRAnalyticsSummaryService:
    @classmethod
    def execute(cls, qr_queryset, request):
        period = request.query_params.get("period")
        date_range = DashboardSummaryService._resolve_date_range(period, request)
        qr_type_scope = qr_queryset.values_list("qr_type__name", flat=True).first()

        if qr_queryset.count() == 1:
            qr = qr_queryset.select_related("qr_type", "project").first()
            return {
                "qr": cls.get_qr_information(qr),
                "summary": cls.get_summary_statistics(qr_queryset, date_range),
            }

        return {
            "qr_type": qr_type_scope,
            "total_qrs": qr_queryset.count(),
            "summary": cls.get_summary_statistics(qr_queryset, date_range),
        }

    @classmethod
    def timeline(cls, qr_queryset, request):
        period = request.query_params.get("period")
        date_range = DashboardSummaryService._resolve_date_range(period, request)
        qr_ids = qr_queryset.values_list("id", flat=True)

        if date_range is None:
            bounds = DashboardSummaryService._daily_queryset(qr_ids, None, None).aggregate(
                start_date=Min("date"),
                end_date=Max("date"),
            )
            if not bounds["start_date"] or not bounds["end_date"]:
                return {
                    "period": period,
                    "timeline": [],
                }
            date_range = DateRange(
                start_date=bounds["start_date"],
                end_date=bounds["end_date"],
            )

        if date_range.start_date is None or date_range.end_date is None:
            return {
                "period": period,
                "timeline": [],
            }

        daily_rows = DashboardSummaryService._daily_queryset(
            qr_ids,
            date_range.start_date,
            date_range.end_date,
        )
        aggregated_rows = (
            daily_rows.values("date")
            .annotate(
                total_scans=Coalesce(Sum("total_scans"), 0),
                unique_scans=Coalesce(Sum("unique_scans"), 0),
            )
            .order_by("date")
        )

        rows_by_date = {
            row["date"]: {
                "date": row["date"],
                "total_scans": row["total_scans"] or 0,
                "unique_scans": row["unique_scans"] or 0,
            }
            for row in aggregated_rows
        }

        timeline = []
        current_date = date_range.start_date
        while current_date <= date_range.end_date:
            timeline.append(
                rows_by_date.get(
                    current_date,
                    {
                        "date": current_date,
                        "total_scans": 0,
                        "unique_scans": 0,
                    },
                )
            )
            current_date += timedelta(days=1)

        return {
            "period": period,
            "timeline": timeline,
        }

    @classmethod
    def get_qr_information(cls, qr):
        if qr is None:
            return None
        return {
            "id": qr.id,
            "name": qr.name,
            "type": qr.qr_type.name if qr.qr_type else None,
            "created_at": qr.created_at,
            "last_scanned_at": cls._get_last_scanned_at([qr.id]),
            "project": qr.project_id,
        }

    @classmethod
    def get_summary_statistics(cls, qr_queryset, date_range):
        qr_ids = qr_queryset.values_list("id", flat=True)
        if date_range is None:
            summary = QRAnalytics.objects.filter(qr_id__in=qr_ids).aggregate(
                total_scans=Coalesce(Sum("total_scans"), 0),
                unique_scans=Coalesce(Sum("unique_scans"), 0),
            )
            scans = ScanEvent.objects.filter(qr_id__in=qr_ids)
            busiest_day = cls.get_busiest_day(qr_ids, None, None)
            average_daily_scans = cls.get_average_daily_scans(qr_ids, None, None)
        else:
            daily_rows = DashboardSummaryService._daily_queryset(
                qr_ids,
                date_range.start_date,
                date_range.end_date,
            )
            summary = daily_rows.aggregate(
                total_scans=Coalesce(Sum("total_scans"), 0),
                unique_scans=Coalesce(Sum("unique_scans"), 0),
            )
            scans = ScanEvent.objects.filter(
                qr_id__in=qr_ids,
                scanned_at__date__gte=date_range.start_date,
                scanned_at__date__lte=date_range.end_date,
            )
            busiest_day = cls.get_busiest_day(qr_ids, date_range.start_date, date_range.end_date)
            average_daily_scans = cls.get_average_daily_scans(qr_ids, date_range.start_date, date_range.end_date)

        total_scans = summary["total_scans"] or 0
        unique_scans = summary["unique_scans"] or 0
        if total_scans and not unique_scans:
            unique_scans = scans.aggregate(
                unique_scans=Count("id")
            )["unique_scans"] or 0

        return {
            "total_scans": total_scans,
            "unique_scans": unique_scans,
            "busiest_day": busiest_day,
            "average_daily_scans": average_daily_scans,
            "peak_scan_day": cls.get_peak_scan_day(scans),
            "peak_scan_hour": cls.get_peak_scan_hour(scans),
        }

    @classmethod
    def get_busiest_day(cls, qr_ids, start_date, end_date):
        queryset = DashboardSummaryService._daily_queryset(qr_ids, start_date, end_date)
        row = (
            queryset.values("date")
            .annotate(total_scans=Coalesce(Sum("total_scans"), 0))
            .order_by("-total_scans", "date")
            .first()
        )
        if not row:
            return None
        return {
            "date": row["date"],
            "total_scans": row["total_scans"] or 0,
        }

    @classmethod
    def get_average_daily_scans(cls, qr_ids, start_date, end_date):
        queryset = DashboardSummaryService._daily_queryset(qr_ids, start_date, end_date)
        return queryset.aggregate(avg_scans=Coalesce(Avg("total_scans"), 0.0))["avg_scans"] or 0

    @classmethod
    def get_peak_scan_day(cls, scan_events):
        row = (
            scan_events.annotate(
                weekday=ExtractWeekDay("scanned_at"),
                date=TruncDate("scanned_at"),
            )
            .values("weekday", "date")
            .annotate(total_scans=Count("id"))
            .order_by("-total_scans", "date")
            .first()
        )
        if not row:
            return None
        return {
            "date": row["date"],
            "weekday": WEEKDAY_NAMES.get(row["weekday"]),
            "total_scans": row["total_scans"],
        }

    @classmethod
    def get_peak_scan_hour(cls, scan_events):
        row = (
            scan_events.annotate(hour=ExtractHour("scanned_at"))
            .values("hour")
            .annotate(total_scans=Count("id"))
            .order_by("-total_scans", "hour")
            .first()
        )
        if not row:
            return None
        hour = row["hour"]
        label_hour = hour % 12 or 12
        suffix = "AM" if hour < 12 else "PM"
        return {
            "hour": hour,
            "label": f"{label_hour}:00 {suffix}",
            "total_scans": row["total_scans"],
        }

    @classmethod
    def _get_last_scanned_at(cls, qr_ids):
        return QRAnalytics.objects.filter(qr_id__in=qr_ids).aggregate(
            last_scanned_at=Max("last_scan_at")
        )["last_scanned_at"]
