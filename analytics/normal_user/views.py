from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from DynamicOCR.schemas import PaginatedAutoSchema
from rest_framework.response import Response
from rest_framework import status
from Qr.models import Project, QRCode
from DynamicOCR.pagination import CustomPagination
from django.db.models import Q

from analytics.serializers import DashboardSummarySerializer
from analytics.services.dashboard_summary_service import DashboardSummaryService
from analytics.services.qr_analytics_summary_service import QRAnalyticsSummaryService


class AnalyticsSchema(PaginatedAutoSchema):
    def get_tags(self, path, method):
        if getattr(self.view, "basename", None) == "details":
            return ["QR Analytics"]
        return ["Dashboard Analytics"]

    def get_operation_id(self, path, method):
        if getattr(self.view, "basename", None) == "details":
            return f"qr_analytics_{self.view.action}"
        return f"dashboard_analytics_{self.view.action}"

    def get_operation(self, path, method):
        operation = super().get_operation(path, method)

        if method.upper() != "GET":
            return operation

        parameters = operation.setdefault("parameters", [])
        if isinstance(self.view, QRAnalyticsViewSet):
            parameters.extend(
                [
                    {
                        "name": "qr_id",
                        "required": False,
                        "in": "query",
                        "description": "Filter analytics for a single QR code.",
                        "schema": {"type": "string", "format": "uuid"},
                    },
                    {
                        "name": "qr_type_id",
                        "required": False,
                        "in": "query",
                        "description": "Filter analytics by QR type ID.",
                        "schema": {"type": "string", "format": "uuid"},
                    },
                    {
                        "name": "period",
                        "required": False,
                        "in": "query",
                        "description": "Time window for analytics. Supported values: today, yesterday, 7d, 30d, 90d, 365d, custom.",
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

        if getattr(self.view, "action", None) not in {"summary", "timeline", "qr_types", "top_qrs"}:
            return operation

        parameters.extend(
            [
                {
                    "name": "period",
                    "required": False,
                    "in": "query",
                    "description": "Time window for analytics. Supported values: today, yesterday, 7d, 30d, 90d, 365d, custom.",
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


# class AnalyticsDashboardViewSet(viewsets.ViewSet):
#     schema = AnalyticsSchema()
#     permission_classes_by_action = {
#         'list': [IsAuthenticated],
#     }
#
#     def get_permissions(self):
#         try:
#             return [permission() for permission in self.permission_classes_by_action[self.action]]
#         except KeyError:
#             return [permission() for permission in self.permission_classes]
#
#     def list(self, request):
#         projects = Project.objects.filter(owner=request.user).values(
#             "id",
#             "name",
#             "description",
#             "status_id",
#             "created_at",
#             "updated_at",
#         )
#         search = request.query_params.get("search")
#         if search:
#             projects = projects.filter(Q(name__icontains=search) | Q(description__icontains=search))
#         paginator = CustomPagination()
#         page = paginator.paginate_queryset(projects, request, view=self)
#         return paginator.get_paginated_response(list(page))



class AnalyticsDashboardViewSet(GenericViewSet):

    permission_classes = [IsAuthenticated]
    schema = AnalyticsSchema()
    serializer_class = DashboardSummarySerializer
    queryset = QRCode.objects.none()

    # permission_classes_by_action = {
    #         'list': [IsAuthenticated],
    #     }

    def get_serializer_class(self):
        if self.action == "summary":
            return DashboardSummarySerializer

        elif self.action == "timeline":
            return DashboardSummarySerializer

        elif self.action == "top_qrs":
            return DashboardSummarySerializer

        return DashboardSummarySerializer


    @action(detail=False, methods=["get"])
    def summary(self, request):
        data = DashboardSummaryService.execute(
            user=request.user,
            request=request,
        )

        return Response(
            {
                "data": data,
                "message": "Dashboard summary fetched successfully."
            }
        )

    @action(detail=False, methods=["get"])
    def timeline(self, request):
        data = DashboardSummaryService.timeline(
            user=request.user,
            request=request,
        )

        return Response(
            {
                "data": data,
                "message": "Timeline fetched successfully."
            }
        )

    @action(detail=False, methods=["get"])
    def qr_types(self, request):
        data = DashboardSummaryService.qr_types(
            user=request.user,
            request=request,
        )

        return Response(
            {
                "data": data,
                "message": "QR type analytics fetched successfully."
            }
        )

    @action(detail=False, methods=["get"])
    def top_qrs(self, request):
        data = DashboardSummaryService.top_qrs(
            user=request.user,
            request=request,
        )

        return Response(
            {
                "data": data,
                "message": "Top performing QR codes fetched successfully."
            }
        )




class QRAnalyticsViewSet(viewsets.GenericViewSet):
    """
    QR Analytics

    Supports three scopes:

    1. Overall Dashboard
        /analytics/summary/

    2. Single QR
        /analytics/summary/?qr_id=<uuid>

    3. QR Type Analytics
        /analytics/summary/?qr_type_id=<uuid>
    """

    # serializer_class = EmptySerializer
    schema = AnalyticsSchema()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "summary":
            return DashboardSummarySerializer

        # elif self.action == "timeline":
        #     return DashboardSummarySerializer
        #
        # elif self.action == "top_qrs":
        #     return DashboardSummarySerializer

        return DashboardSummarySerializer

    def get_qr_queryset(self):
        queryset = QRCode.objects.filter(
            created_by=self.request.user,
            is_deleted=False,
        )

        qr_id = self.request.query_params.get("qr_id")
        qr_type_id = self.request.query_params.get("qr_type_id")

        if qr_id and qr_type_id:
            raise ValidationError("Provide either qr_id or qr_type_id, not both.")
        if not qr_id and not qr_type_id:
            raise ValidationError("Provide either qr_id or qr_type_id.")

        if qr_id:
            queryset = queryset.filter(pk=qr_id)

        if qr_type_id:
            queryset = queryset.filter(qr_type_id=qr_type_id)

        return queryset

    @action(detail=False, methods=["get"])
    def detail_summary(self, request):
        qr_queryset = self.get_qr_queryset()
        data = QRAnalyticsSummaryService.execute(qr_queryset=qr_queryset, request=request)

        return Response(
            {
                "data": data,
                "message": "Analytics summary fetched successfully."
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def detail_timeline(self, request):
        qr_queryset = self.get_qr_queryset()
        data = QRAnalyticsSummaryService.timeline(qr_queryset=qr_queryset, request=request)

        return Response(
            {
                "data": data,
                "message": "Timeline fetched successfully."
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def weekdays(self, request):
        qr_queryset = self.get_qr_queryset()

        # TODO: Weekday Analytics Service

        return Response(
            {
                "message": "Weekday analytics fetched successfully."
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def hours(self, request):
        qr_queryset = self.get_qr_queryset()

        # TODO: Hourly Analytics Service

        return Response(
            {
                "message": "Hourly analytics fetched successfully."
            },
            status=status.HTTP_200_OK,
        )
