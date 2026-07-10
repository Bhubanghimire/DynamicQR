from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.schemas.openapi import AutoSchema
from rest_framework.response import Response
from rest_framework import status
from accounts.authentication import JWTAuthentication
from Qr.models import Project, QRCode, TemplateDesign
from Qr.serializers import (
    ProjectSerializer,
    ProjectDetailSerializer,
    ProjectQRActionSerializer,
    QRCodeSerializer,
    QRCodeBundleSerializer,
    QRDesignSerializer,
    QRCodeSummarySerializer, TemplateDesignSerializer,
)


class ProjectSchema(AutoSchema):
    def get_tags(self, path, method):
        tag_by_basename = {
            "project": "Projects",
            "Qr": "QR Codes",
            "template_design": "Templates",
        }
        return [tag_by_basename.get(getattr(self.view, "basename", None), "Qr")]

    def get_operation_id(self, path, method):
        prefix = getattr(self.view, "basename", self.view.__class__.__name__)
        return f"{prefix.lower()}_{self.view.action}"

    def get_description(self, path, method):
        action = getattr(self.view, "action", None)
        if action == "add_qr":
            return "Attach a QR code to the project. URL path parameter `pk` is the project id and request body field `qr_id` is the QR code id."
        if action == "remove_qr":
            return "Detach a QR code from the project. URL path parameter `pk` is the project id and request body field `qr_id` is the QR code id."
        return super().get_description(path, method)

    def get_request_serializer(self, path, method):
        action = getattr(self.view, "action", None)
        if action in {"add_qr", "remove_qr"}:
            return ProjectQRActionSerializer()
        return super().get_request_serializer(path, method)

    def get_request_body(self, path, method):
        action = getattr(self.view, "action", None)
        if action == "remove_qr":
            self.request_media_types = self.map_parsers(path, "POST")
            serializer = self.get_request_serializer(path, method)
            item_schema = self.get_reference(serializer) if isinstance(serializer, ProjectQRActionSerializer) else {}
            return {
                "content": {
                    ct: {"schema": item_schema}
                    for ct in self.request_media_types
                }
            }
        return super().get_request_body(path, method)


class ProjectViewSet(viewsets.ModelViewSet):
    schema = ProjectSchema()
    authentication_classes = [JWTAuthentication]
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

    @action(detail=True, methods=["post"], url_path="add-qr")
    def add_qr(self, request, *args, **kwargs):
        project = self.get_object()
        qr_id = request.data.get("qr_id") or request.query_params.get("qr_id")

        if not qr_id:
            return Response(
                {"data": {}, "message": "qr_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            qr = QRCode.objects.get(id=qr_id)
        except QRCode.DoesNotExist:
            return Response(
                {"data": {}, "message": "QR code not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        qr.project = project
        qr.save(update_fields=["project"])
        return Response(
            {
                "data": {"project_id": project.id, "qr_id": qr.id},
                "message": "QR code added to project successfully.",
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["delete"], url_path="remove-qr")
    def remove_qr(self, request, *args, **kwargs):
        project = self.get_object()
        qr_id = request.data.get("qr_id") or request.query_params.get("qr_id")

        if not qr_id:
            return Response(
                {"data": {}, "message": "qr_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            qr = QRCode.objects.get(id=qr_id, project=project)
        except QRCode.DoesNotExist:
            return Response(
                {"data": {}, "message": "QR code not found in this project."},
                status=status.HTTP_404_NOT_FOUND,
            )

        qr.project = None
        qr.save(update_fields=["project"])
        return Response(
            {
                "data": {"project_id": project.id, "qr_id": qr.id},
                "message": "QR code removed from project successfully.",
            },
            status=status.HTTP_200_OK,
        )


class QRCodeViewSet(viewsets.ModelViewSet):
    queryset = QRCode.objects.all()
    schema = ProjectSchema()
    serializer_class = QRCodeSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get_serializer_class(self):
        if self.action == "preview":
            return QRCodeSummarySerializer
        if self.action == "save_design":
            return QRDesignSerializer
        if self.action in {"create", "update", "partial_update", "retrieve"}:
            return QRCodeBundleSerializer
        return super().get_serializer_class()

    def list(self, request, *args, **kwargs):
        qrcodes = self.get_queryset()
        serializer = self.get_serializer(qrcodes, many=True)
        return Response({"data": serializer.data, "message": "QR codes fetched successfully."}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        qr_code = self.get_object()
        serializer = self.get_serializer(qr_code)
        return Response({"data": serializer.data, "message": "QR code fetched successfully."}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        qr_code = serializer.save()
        return Response(
            {"data": self.get_serializer(qr_code).data, "message": "QR code created successfully."},
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        qr_code = serializer.save()
        return Response(
            {"data": self.get_serializer(qr_code).data, "message": "QR code updated successfully."},
            status=status.HTTP_200_OK,
        )

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({"data": {}, "message": "QR code deleted successfully."}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="design")
    def save_design(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        design = serializer.save()
        return Response(
            {"data": self.get_serializer(design).data, "message": "QR design saved successfully."},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="preview")
    def preview(self, request, *args, **kwargs):
        qr_code = self.get_object()
        serializer = self.get_serializer(qr_code)
        return Response(
            {"data": serializer.data, "message": "QR preview fetched successfully."},
            status=status.HTTP_200_OK,
        )


class TemplateViewSet(viewsets.ModelViewSet):
    queryset = TemplateDesign.objects.all()
    serializer_class = TemplateDesignSerializer
    permission_classes = [IsAuthenticated]
    schema = ProjectSchema()
    authentication_classes = [JWTAuthentication]

    def list(self, request, *args, **kwargs):
        templates = self.get_queryset()
        serializer = self.get_serializer(templates, many=True)
        return Response(
            {"data": serializer.data, "message": "Templates fetched successfully."},
            status=status.HTTP_200_OK,
        )

    def retrieve(self, request, *args, **kwargs):
        template = self.get_object()
        serializer = self.get_serializer(template)
        return Response(
            {"data": serializer.data, "message": "Template fetched successfully."},
            status=status.HTTP_200_OK,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            {"data": serializer.data, "message": "Template created successfully."},
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(
            {"data": serializer.data, "message": "Template updated successfully."},
            status=status.HTTP_200_OK,
        )

    # def partial_update(self, request, *args, **kwargs):
    #     kwargs["partial"] = True
    #     return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {"data": {}, "message": "Template deleted successfully."},
            status=status.HTTP_200_OK,
        )
