from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from DynamicOCR.schemas import PaginatedAutoSchema
from rest_framework.response import Response
from rest_framework import status
from Qr.models import Project
from DynamicOCR.pagination import CustomPagination
from django.db.models import Q


class ProjectSchema(PaginatedAutoSchema):
    def get_tags(self, path, method):
        return ["Subscription"]

    def get_operation_id(self, path, method):
        return f"subscription_{self.view.action}"


class SubscriptionViewSet(viewsets.ViewSet):
    schema = ProjectSchema()
    permission_classes_by_action = {
        'list': [IsAuthenticated],
    }

    def get_permissions(self):
        try:
            return [permission() for permission in self.permission_classes_by_action[self.action]]
        except KeyError:
            return [permission() for permission in self.permission_classes]

    def list(self, request):
        projects = Project.objects.filter(owner=request.user).values(
            "id",
            "name",
            "description",
            "status_id",
            "created_at",
            "updated_at",
        )
        search = request.query_params.get("search")
        if search:
            projects = projects.filter(Q(name__icontains=search) | Q(description__icontains=search))
        paginator = CustomPagination()
        page = paginator.paginate_queryset(projects, request, view=self)
        return paginator.get_paginated_response(list(page))
