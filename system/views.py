from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.schemas.openapi import AutoSchema

from system.models import ConfigCategory, ConfigChoice
from system.serializers import (
    ConfigCategorySerializer,
    ConfigChoiceSerializer,
    ConfigCategoryListResponseSerializer,
    ConfigChoiceListResponseSerializer,
)
class CategorySchema(AutoSchema):
    def get_tags(self, path, method):
        return ["Category"]


class ConfigCategoryViewSet(viewsets.ModelViewSet):
    schema = CategorySchema()
    queryset = ConfigCategory.objects.all().order_by("id")
    serializer_class = ConfigCategorySerializer
    permission_classes = [AllowAny]
    http_method_names = ["get"]

    def get_serializer_class(self):
        if self.action == "choices":
            return ConfigChoiceSerializer
        return super().get_serializer_class()

    def get_response_serializer(self, path, method):
        if method.upper() != "GET":
            return super().get_response_serializer(path, method)

        if self.action == "list":
            return ConfigCategoryListResponseSerializer()
        if self.action == "choices":
            return ConfigChoiceListResponseSerializer()
        return super().get_response_serializer(path, method)

    @action(detail=True, methods=["get"], url_path="choices")
    def choices(self, request, pk=None):
        choices = ConfigChoice.objects.filter(category_id=pk).order_by("id")
        serializer = ConfigChoiceSerializer(choices, many=True)
        return Response({"data": serializer.data, "msg": "Choices fetched successfully."})

    def list(self, request, *args, **kwargs):
        categories = self.get_queryset()
        serializer = self.get_serializer(categories, many=True)
        return Response({"data": serializer.data, "msg": "Config categories fetched successfully."})
