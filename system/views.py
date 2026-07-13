from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from DynamicOCR.schemas import PaginatedAutoSchema

from system.models import ConfigCategory, ConfigChoice
from system.serializers import (
    ConfigCategorySerializer,
    ConfigChoiceSerializer,
    ConfigCategoryPaginatedResponseSerializer,
    ConfigChoicePaginatedResponseSerializer,
)
from DynamicOCR.pagination import CustomPagination


class CategorySchema(PaginatedAutoSchema):
    def get_tags(self, path, method):
        return ["Category"]


class ConfigCategoryViewSet(viewsets.ModelViewSet):
    schema = CategorySchema()
    queryset = ConfigCategory.objects.all().order_by("id")
    serializer_class = ConfigCategorySerializer
    permission_classes = [AllowAny]
    http_method_names = ["get"]
    filter_backends = [SearchFilter]
    search_fields = ["name", "description"]

    def get_serializer_class(self):
        if self.action == "choices":
            return ConfigChoiceSerializer
        return super().get_serializer_class()

    def get_response_serializer(self, path, method):
        if method.upper() != "GET":
            return super().get_response_serializer(path, method)

        if self.action == "list":
            return ConfigCategoryPaginatedResponseSerializer()
        if self.action == "choices":
            return ConfigChoicePaginatedResponseSerializer()
        return super().get_response_serializer(path, method)

    @action(detail=True, methods=["get"], url_path="choices")
    def choices(self, request, pk=None):
        choices = ConfigChoice.objects.filter(category_id=pk).order_by("id")
        choices = self.filter_queryset(choices)
        paginator = CustomPagination()
        page = paginator.paginate_queryset(choices, request, view=self)
        serializer = self.get_serializer(page, many=True)
        response = paginator.get_paginated_response(serializer.data)
        response.data["msg"] = "Choices fetched successfully."
        return response

    def list(self, request, *args, **kwargs):
        categories = self.filter_queryset(self.get_queryset())
        paginator = CustomPagination()
        page = paginator.paginate_queryset(categories, request, view=self)
        serializer = self.get_serializer(page, many=True)
        response = paginator.get_paginated_response(serializer.data)
        response.data["msg"] = "Config categories fetched successfully."
        return response
