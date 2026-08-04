from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from DynamicOCR.schemas import PaginatedAutoSchema
from rest_framework.response import Response
from rest_framework import status
from Qr.models import Project
from DynamicOCR.pagination import CustomPagination
from django.db.models import Q

from analytics.serializers import DashboardSummarySerializer
from analytics.services.dashboard_summary_service import DashboardSummaryService


class AnalyticsSchema(PaginatedAutoSchema):
    def get_tags(self, path, method):
        return ["Analytics"]

    def get_operation_id(self, path, method):
        return f"projects_{self.view.action}"

    def get_operation(self, path, method):
        operation = super().get_operation(path, method)

        if getattr(self.view, "action", None) not in {"summary", "timeline"} or method.upper() != "GET":
            return operation

        parameters = operation.setdefault("parameters", [])
        parameters.extend(
            [
                {
                    "name": "project",
                    "required": False,
                    "in": "query",
                    "description": "Filter analytics by project UUID.",
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

    permission_classes_by_action = {
            'list': [IsAuthenticated],
        }

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
        ...

    @action(detail=False, methods=["get"])
    def top_qrs(self, request):
        ...

    # @action(detail=False, methods=["get"])
    # def countries(self, request):
    #     ...

    # @action(detail=False, methods=["get"])
    # def devices(self, request):
    #     ...

    # @action(detail=False, methods=["get"])
    # def browsers(self, request):
    #     ...

    # @action(detail=False, methods=["get"])
    # def operating_systems(self, request):
    #     ...
