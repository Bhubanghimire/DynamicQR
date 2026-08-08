from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from django.db.models import Avg, Max, Min, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from Qr.models import QRCode, Project
from analytics.models import AnalyticsTime, QRAnalytics


@dataclass(frozen=True)
class DateRange:
    start_date: Optional[object]
    end_date: Optional[object]


class DashboardSummaryService:
    PERIOD_MAP = {
        "today": 0,
        "yesterday": 1,
        "7d": 7,
        "30d": 30,
        "90d": 90,
        "365d": 365,
    }

    @classmethod
    def execute(cls, user, request):
        qr_queryset = cls._get_qr_queryset(user=user, request=request)
        qr_ids = qr_queryset.values_list("id", flat=True)

        period = request.query_params.get("period")
        date_range = cls._resolve_date_range(period, request)

        if date_range is None:
            summary = QRAnalytics.objects.filter(qr_id__in=qr_ids).aggregate(
                total_scans=Coalesce(Sum("total_scans"), 0),
                unique_scans=Coalesce(Sum("unique_scans"), 0),
            )
            busiest_day = cls._get_busiest_day(qr_ids, None, None)
            average_daily_scans = cls._get_average_daily_scans(qr_ids, None, None)
        else:
            daily_rows = cls._daily_queryset(qr_ids, date_range.start_date, date_range.end_date)
            summary = daily_rows.aggregate(
                total_scans=Coalesce(Sum("total_scans"), 0),
                unique_scans=Coalesce(Sum("unique_scans"), 0),
            )
            busiest_day = cls._get_busiest_day(qr_ids, date_range.start_date, date_range.end_date)
            average_daily_scans = cls._get_average_daily_scans(qr_ids, date_range.start_date, date_range.end_date)

        return {
            "total_qrs": qr_queryset.count(),
            "total_scans": summary["total_scans"] or 0,
            "unique_scans": summary["unique_scans"] or 0,
            "busiest_day": busiest_day,
            "average_daily_scans": average_daily_scans,
        }

    @classmethod
    def timeline(cls, user, request):
        qr_queryset = cls._get_qr_queryset(user=user, request=request)
        qr_ids = qr_queryset.values_list("id", flat=True)

        period = request.query_params.get("period")
        date_range = cls._resolve_date_range(period, request)

        if date_range is None:
            bounds = cls._daily_queryset(qr_ids, None, None).aggregate(
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

        daily_rows = cls._daily_queryset(qr_ids, date_range.start_date, date_range.end_date)
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
    def qr_types(cls, user, request):
        qr_queryset = cls._get_qr_queryset(user=user, request=request)
        qr_ids = qr_queryset.values_list("id", flat=True)

        period = request.query_params.get("period")
        date_range = cls._resolve_date_range(period, request)

        if date_range is None:
            grouped_rows = (
                QRAnalytics.objects.filter(qr_id__in=qr_ids)
                .values("qr__qr_type_id", "qr__qr_type__name")
                .annotate(total_scans=Coalesce(Sum("total_scans"), 0))
                .order_by("-total_scans", "qr__qr_type__name")
            )
            overall_total = QRAnalytics.objects.filter(qr_id__in=qr_ids).aggregate(
                total_scans=Coalesce(Sum("total_scans"), 0)
            )["total_scans"] or 0
        else:
            daily_rows = cls._daily_queryset(qr_ids, date_range.start_date, date_range.end_date)
            grouped_rows = (
                daily_rows.values("qr__qr_type_id", "qr__qr_type__name")
                .annotate(total_scans=Coalesce(Sum("total_scans"), 0))
                .order_by("-total_scans", "qr__qr_type__name")
            )
            overall_total = daily_rows.aggregate(
                total_scans=Coalesce(Sum("total_scans"), 0)
            )["total_scans"] or 0

        data = []
        for row in grouped_rows:
            type_total_scans = row["total_scans"] or 0
            percentage = 0 if not overall_total else round((type_total_scans / overall_total) * 100, 2)
            data.append(
                {
                    "id": row["qr__qr_type_id"],
                    "type": row["qr__qr_type__name"],
                    "total_scans": type_total_scans,
                    "percentage": percentage,
                }
            )

        return data

    @classmethod
    def top_qrs(cls, user, request):
        qr_queryset = cls._get_qr_queryset(user=user, request=request)
        qr_ids = qr_queryset.values_list("id", flat=True)

        period = request.query_params.get("period")
        date_range = cls._resolve_date_range(period, request)

        if date_range is None:
            rows = (
                QRAnalytics.objects.filter(qr_id__in=qr_ids)
                .select_related("qr", "qr__qr_type")
                .order_by("-total_scans", "qr__name", "qr_id")[:10]
            )

            return [
                {
                    "id": row.qr_id,
                    "name": row.qr.name,
                    "type": row.qr.qr_type.name if row.qr.qr_type else None,
                    "total_scans": row.total_scans,
                }
                for row in rows
            ]

        daily_rows = cls._daily_queryset(qr_ids, date_range.start_date, date_range.end_date)
        rows = (
            daily_rows.values("qr_id", "qr__name", "qr__qr_type__name")
            .annotate(total_scans=Coalesce(Sum("total_scans"), 0))
            .order_by("-total_scans", "qr__name", "qr_id")[:10]
        )

        return [
            {
                "id": row["qr_id"],
                "name": row["qr__name"],
                "type": row["qr__qr_type__name"],
                "total_scans": row["total_scans"] or 0,
            }
            for row in rows
        ]

    @classmethod
    def _get_qr_queryset(cls, user, request):
        queryset = QRCode.objects.filter(created_by=user, is_deleted=False)

        project_id = request.query_params.get("project")
        if project_id:
            project = Project.objects.filter(
                pk=project_id,
                owner=user,
                is_deleted=False,
            ).first()
            if project is not None:
                queryset = queryset.filter(project=project)
            else:
                queryset = queryset.none()

        return queryset

    @classmethod
    def _resolve_date_range(cls, period, request):
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
            start_date = request.query_params.get("start_date")
            end_date = request.query_params.get("end_date")
            if not start_date or not end_date:
                return None
            return DateRange(start_date=start_date, end_date=end_date)

        return None

    @staticmethod
    def _daily_queryset(qr_ids, start_date, end_date):
        queryset = AnalyticsTime.objects.filter(qr_id__in=qr_ids, hour__isnull=True)
        if start_date is not None:
            queryset = queryset.filter(date__gte=start_date)
        if end_date is not None:
            queryset = queryset.filter(date__lte=end_date)
        return queryset

    @classmethod
    def _get_busiest_day(cls, qr_ids, start_date, end_date):
        queryset = cls._daily_queryset(qr_ids, start_date, end_date)
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
    def _get_average_daily_scans(cls, qr_ids, start_date, end_date):
        queryset = cls._daily_queryset(qr_ids, start_date, end_date)
        value = queryset.aggregate(avg_scans=Coalesce(Avg("total_scans"), 0.0))["avg_scans"] or 0
        return value
