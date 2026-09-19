from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from DynamicOCR.pagination import CustomPagination
from analytics.services.admin_dashboard_service import AdminDashboardService
from accounts.views import AdminAutoSchema

class AnalyticsDashboardSchema(AdminAutoSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method.upper() != "GET":
            return operation

        parameters = operation.setdefault("parameters", [])
        parameters.extend(
            [
                {
                    "name": "period",
                    "required": False,
                    "in": "query",
                    "description": "Filter period: today, yesterday, 7d, 30d, 90d, 365d, custom",
                    "schema": {
                        "type": "string",
                        "enum": ["today", "yesterday", "7d", "30d", "90d", "365d", "custom"],
                    },
                },
                {
                    "name": "start_date",
                    "required": False,
                    "in": "query",
                    "description": "Start date for custom period in YYYY-MM-DD format.",
                    "schema": {"type": "string", "format": "date"},
                },
                {
                    "name": "end_date",
                    "required": False,
                    "in": "query",
                    "description": "End date for custom period in YYYY-MM-DD format.",
                    "schema": {"type": "string", "format": "date"},
                },
            ]
        )
        return operation

class AnalyticsDashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAdminUser]
    schema = AnalyticsDashboardSchema()

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
