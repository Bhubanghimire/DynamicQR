from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.schemas.openapi import AutoSchema
from rest_framework.response import Response
from rest_framework import status
from Qr.models import Project
from Qr.serializers import ProjectSerializer, ProjectDetailSerializer


class ProjectSchema(AutoSchema):
    def get_tags(self, path, method):
        return ["Qr"]

    def get_operation_id(self, path, method):
        return f"projects_{self.view.action}"


class ProjectViewSet(viewsets.ModelViewSet):
    schema = ProjectSchema()
    model = Project
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectSerializer
    queryset = Project.objects.all()

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProjectDetailSerializer
        return super().get_serializer_class()

    def list(self, request, *args, **kwargs):
        projects = self.get_queryset()
        serializer = self.get_serializer(projects, many=True)
        return Response({"data": serializer.data, "message": "Projects fetched successfully."}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        project = self.get_object()
        serializer = self.get_serializer(project)
        return Response({"data": serializer.data, "message": "Project fetched successfully."}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response({"data": serializer.data, "message": "Project created successfully."}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({"data": serializer.data, "message": "Project updated successfully."}, status=status.HTTP_200_OK)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({"data": {}, "message": "Project deleted successfully."}, status=status.HTTP_200_OK)
