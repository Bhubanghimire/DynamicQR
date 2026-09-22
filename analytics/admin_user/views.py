from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from DynamicQR.pagination import CustomPagination
from analytics.services.admin_dashboard_service import AdminDashboardService
from accounts.views import AdminAutoSchema, admin_query_parameter


PERIOD_VALUES = ["today", "yesterday", "7d", "30d", "90d", "365d", "custom"]
SUBSCRIPTION_STATUS_VALUES = ["active", "expired", "cancelled", "pending", "failed", "grace_period"]

PAGE_PARAMETERS = [
    admin_query_parameter("page", "Page number for the paginated result.", value_type="integer", example=1),
    admin_query_parameter(
        "page_size",
        "Number of results per page (maximum 100).",
        value_type="integer",
        example=10,
    ),
]
OPTIONAL_DATE_RANGE_PARAMETERS = [
    admin_query_parameter(
        "period",
        "Date filter. Use `custom` together with both `start_date` and `end_date`.",
        enum=PERIOD_VALUES,
        example="30d",
    ),
    admin_query_parameter(
        "start_date",
        "Start date in YYYY-MM-DD format; used when `period=custom`.",
        value_format="date",
        example="2026-09-01",
    ),
    admin_query_parameter(
        "end_date",
        "End date in YYYY-MM-DD format; used when `period=custom`.",
        value_format="date",
        example="2026-09-21",
    ),
]
REQUIRED_DATE_RANGE_PARAMETERS = [
    {
        **OPTIONAL_DATE_RANGE_PARAMETERS[0],
        "required": True,
        "description": "Required date filter. Use `custom` together with both `start_date` and `end_date`.",
    },
    *OPTIONAL_DATE_RANGE_PARAMETERS[1:],
]
QR_FILTER_PARAMETERS = [
    admin_query_parameter(
        "search",
        "Case-insensitive search across QR name, short code, creator email, and creator full name.",
        example="campaign",
    ),
    admin_query_parameter(
        "user_id",
        "Filter by exact QR creator UUID.",
        value_format="uuid",
        example="123e4567-e89b-12d3-a456-426614174000",
    ),
    admin_query_parameter(
        "qr_status",
        "Filter by QR active state.",
        enum=["active", "inactive"],
        example="active",
    ),
    admin_query_parameter(
        "status",
        "Alias of `qr_status`; filter by QR active state.",
        enum=["active", "inactive"],
        example="active",
    ),
    admin_query_parameter(
        "qr_type",
        "Filter by exact QR type UUID or a case-insensitive partial QR type name.",
        example="website",
    ),
]
SCAN_FILTER_PARAMETERS = [
    admin_query_parameter(
        "user_id",
        "Filter scans by exact QR creator UUID.",
        value_format="uuid",
        example="123e4567-e89b-12d3-a456-426614174000",
    ),
    admin_query_parameter("country", "Case-insensitive partial country match.", example="Nepal"),
    admin_query_parameter("city", "Case-insensitive partial city match.", example="Kathmandu"),
    admin_query_parameter("browser", "Case-insensitive partial browser match.", example="Chrome"),
    admin_query_parameter("os", "Case-insensitive partial operating-system match.", example="Android"),
    admin_query_parameter("device_type", "Case-insensitive partial device-type match.", example="mobile"),
    admin_query_parameter(
        "is_bot",
        "Filter bot scans. `1`, `true`, and `yes` mean true; `0`, `false`, and `no` mean false.",
        enum=["true", "false", "1", "0", "yes", "no"],
        example="false",
    ),
]
USER_FILTER_PARAMETERS = [
    admin_query_parameter(
        "search",
        "Case-insensitive search across user email and full name.",
        example="alex@example.com",
    ),
    admin_query_parameter(
        "user_id",
        "Filter by exact user UUID.",
        value_format="uuid",
        example="123e4567-e89b-12d3-a456-426614174000",
    ),
    admin_query_parameter(
        "status",
        "Filter by user active state.",
        enum=["active", "inactive"],
        example="active",
    ),
]

class AnalyticsDashboardSchema(AdminAutoSchema):
    pass

class AnalyticsDashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAdminUser]
    schema = AnalyticsDashboardSchema()
    swagger_query_parameters = {
        "summary": OPTIONAL_DATE_RANGE_PARAMETERS,
        "top_power_users": [
            *PAGE_PARAMETERS,
            {
                **USER_FILTER_PARAMETERS[0],
                "description": "Case-insensitive search across user email, full name, and phone.",
            },
            *USER_FILTER_PARAMETERS[1:],
        ],
        "code_generation_trend": [
            *PAGE_PARAMETERS,
            *REQUIRED_DATE_RANGE_PARAMETERS,
            *QR_FILTER_PARAMETERS,
        ],
        "qr_type_usage": [*PAGE_PARAMETERS, *QR_FILTER_PARAMETERS],
        "top_performing_qrs": [*PAGE_PARAMETERS, *QR_FILTER_PARAMETERS],
        "os_browser_share": [
            *PAGE_PARAMETERS,
            *OPTIONAL_DATE_RANGE_PARAMETERS,
            *SCAN_FILTER_PARAMETERS,
        ],
        "plan_metrics": [
            *PAGE_PARAMETERS,
            *OPTIONAL_DATE_RANGE_PARAMETERS,
            admin_query_parameter(
                "search",
                "Case-insensitive search by package title.",
                example="Pro",
            ),
            admin_query_parameter(
                "package_status",
                "Filter packages by active state.",
                enum=["active", "inactive"],
                example="active",
            ),
            admin_query_parameter(
                "status",
                "Alias of `package_status`; filter packages by active state.",
                enum=["active", "inactive"],
                example="active",
            ),
            admin_query_parameter(
                "subscription_status",
                "Filter subscriptions included in user counts by exact status. Defaults to `active`.",
                enum=SUBSCRIPTION_STATUS_VALUES,
                example="active",
            ),
            *SCAN_FILTER_PARAMETERS,
        ],
        "user_activities": [
            *PAGE_PARAMETERS,
            *REQUIRED_DATE_RANGE_PARAMETERS,
            *USER_FILTER_PARAMETERS,
        ],
    }

    @staticmethod
    def _paginate(request, result):
        """Paginate the list in a service result while preserving its message."""
        data = result.get("data", [])
        if not isinstance(data, list):
            return Response(result, status=status.HTTP_200_OK)
        paginator = CustomPagination()
        page = paginator.paginate_queryset(data, request, view=None)
        response = paginator.get_paginated_response(page)
        response.data["message"] = result.get("message")
        return response

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        try:
            data = AdminDashboardService.get_summary(request)
            return Response(
                {
                    "data": data,
                    "message": "Admin dashboard summary fetched successfully."
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "data": {},
                    "message": f"Error fetching summary: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='top-power-users')
    def top_power_users(self, request):
        try:
            result = AdminDashboardService.get_top_power_users(request)
            return self._paginate(request, result)
        except Exception as e:
            return Response(
                {
                    "data": [],
                    "message": f"Error fetching top power users: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='qr-generation-trend')
    def code_generation_trend(self, request):
        try:
            result = AdminDashboardService.get_qr_generation_trend(request)
            return self._paginate(request, result)
        except Exception as e:
            return Response(
                {
                    "data": [],
                    "message": f"Error fetching top power users: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='qr-type-usage')
    def qr_type_usage(self, request):
        try:
            result = AdminDashboardService.get_qr_type_usage(request)
            return self._paginate(request, result)
        except Exception as e:
            return Response(
                {
                    "data": [],
                    "message": f"Error fetching QR type usage: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='top-performing-qrs')
    def top_performing_qrs(self, request):
        try:
            result = AdminDashboardService.get_top_performing_qrs(request)
            return self._paginate(request, result)
        except Exception as e:
            return Response(
                {
                    "data": [],
                    "message": f"Error fetching top performing QR codes: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='os-browser-share')
    def os_browser_share(self, request):
        try:
            result = AdminDashboardService.get_os_browser_distribution(request)
            if isinstance(result.get("data"), dict):
                paginator = CustomPagination()
                data = result["data"]
                for key in ("os", "browser"):
                    page = paginator.paginate_queryset(data.get(key, []), request, view=None)
                    data[key] = list(page)
                result["data"] = data
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {
                    "data": {"os": [], "browser": []},
                    "message": f"Error fetching OS/Browser distribution: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='plan-metrics')
    def plan_metrics(self, request):
        try:
            result = AdminDashboardService.get_plan_metrics(request)
            return self._paginate(request, result)
        except Exception as e:
            return Response(
                {
                    "data": [],
                    "message": f"Error fetching plan metrics: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='user-activities')
    def user_activities(self, request):
        try:
            result = AdminDashboardService.get_user_activities(request)
            return self._paginate(request, result)
        except Exception as e:
            return Response(
                {
                    "data": [],
                    "message": f"Error fetching user activities: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
