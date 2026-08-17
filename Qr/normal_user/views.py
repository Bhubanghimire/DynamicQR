from django.db import transaction
from uuid import UUID
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.filters import SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.exceptions import NotFound
from DynamicOCR.schemas import PaginatedAutoSchema
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError
from accounts.authentication import JWTAuthentication
from django.db.models import Count, Q, Max
from Qr.models import Project, QRCode, TemplateDesign, QrMedia, MediaItem, QRDesign
from Qr.serializers import (
    ProjectSerializer,
    ProjectDetailSerializer,
    ProjectQRActionSerializer,
    QRCodeSerializer,
    QRCodeBundleSerializer,
    QRCodeDuplicateRequestSerializer,
    QRDesignSerializer,
    QRCodeSummarySerializer, TemplateDesignSerializer, VideoDeleteSerializer, VideoUploadSerializer,
    VideoUpdateSerializer,
)
from DynamicOCR.pagination import CustomPagination
from analytics.task import track_scan
from analytics.services.tracker import AnalyticsTracker

class ProjectSchema(PaginatedAutoSchema):
    def get_tags(self, path, method):
        tag_by_basename = {
            "project": "Projects",
            "Qr": "QR Codes",
            "video": "QR Codes",
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
        if action == "qrs":
            return "List QR codes attached to a project. URL path parameter `pk` is the project id."
        if action == "upload":
            return "Create a QR playlist when `qr_code` is provided, or reuse an existing playlist when `playlist_id` is provided, then upload one video to that playlist. The `video_description` field is saved on the media item."
        if action in {"update", "partial_update"} and getattr(self.view, "basename", None) == "video":
            return "Update a video media item. If `video` is included, the old file is replaced and deleted from storage. If `video` is omitted, only the other fields are updated."
        if action == "delete_video":
            return "Delete a video media item by its UUID."
        if action == "duplicate":
            return "Duplicate a QR code using fresh content and design supplied in the request body."
        return super().get_description(path, method)

    def get_request_serializer(self, path, method):
        action = getattr(self.view, "action", None)
        if action in {"add_qr", "remove_qr"}:
            return ProjectQRActionSerializer()
        if action == "upload":
            return VideoUploadSerializer()
        if action in {"update", "partial_update"} and getattr(self.view, "basename", None) == "video":
            return VideoUpdateSerializer()
        if action == "delete_video":
            return VideoDeleteSerializer()
        return super().get_request_serializer(path, method)

    def get_response_serializer(self, path, method):
        action = getattr(self.view, "action", None)
        if action == "scan":
            return QRCodeBundleSerializer()
        return super().get_response_serializer(path, method)

    def get_request_body(self, path, method):
        action = getattr(self.view, "action", None)
        if action == "upload":
            self.request_media_types = ["multipart/form-data"]
            serializer = self.get_request_serializer(path, method)
            item_schema = self.get_reference(serializer) if isinstance(serializer, VideoUploadSerializer) else {}
            return {
                "content": {
                    "multipart/form-data": {"schema": item_schema}
                }
            }
        if action in {"update", "partial_update"} and getattr(self.view, "basename", None) == "video":
            self.request_media_types = ["multipart/form-data", "application/json"]
            serializer = self.get_request_serializer(path, method)
            item_schema = self.get_reference(serializer) if isinstance(serializer, VideoUpdateSerializer) else {}
            return {
                "content": {
                    ct: {"schema": item_schema}
                    for ct in self.request_media_types
                }
            }
        if action == "delete_video":
            return {
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "format": "uuid",
                                    "description": "ID of the media item to delete.",
                                }
                            },
                            "required": ["id"],
                            "example": {
                                "id": "3f5f1a2e-5c1d-4c5b-9dd5-9b4f7f1d2c10"
                            },
                        }
                    }
                }
            }
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
        if action == "duplicate":
            serializer = self.get_request_serializer(path, method)
            item_schema = self.get_reference(serializer) if isinstance(serializer, QRCodeDuplicateRequestSerializer) else {}
            return {
                "content": {
                    "application/json": {"schema": item_schema}
                }
            }
        return super().get_request_body(path, method)


class ProjectViewSet(viewsets.ModelViewSet):
    schema = ProjectSchema()
    authentication_classes = [JWTAuthentication]
    model = Project
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter]
    search_fields = ["name", "description"]
    serializer_class = ProjectSerializer
    queryset = Project.objects.annotate(qr_count=Count("qrcode", filter=Q(qrcode__is_deleted=False))).order_by("-created_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(owner=self.request.user)

    def get_search_fields(self):
        if self.action == "qrs":
            return ["name", "qr_type__name"]
        return ["name", "description"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProjectDetailSerializer
        return super().get_serializer_class()

    def list(self, request, *args, **kwargs):
        projects = self.filter_queryset(self.get_queryset())
        paginator = CustomPagination()
        page = paginator.paginate_queryset(projects, request, view=self)
        serializer = self.get_serializer(page, many=True)
        response = paginator.get_paginated_response(serializer.data)
        response.data["message"] = "Projects fetched successfully."
        return response

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

    @action(detail=True, methods=["get"], url_path="qrs")
    def qrs(self, request, *args, **kwargs):
        project = self.get_object()
        qrcodes = QRCode.objects.filter(project=project, is_deleted=False).order_by("name")
        qrcodes = self.filter_queryset(qrcodes)
        paginator = CustomPagination()
        page = paginator.paginate_queryset(qrcodes, request, view=self)
        serializer = QRCodeSerializer(page, many=True)
        response = paginator.get_paginated_response(serializer.data)
        response.data["message"] = "Project QR codes fetched successfully."
        return response


class QRCodeViewSet(viewsets.ModelViewSet):
    queryset = QRCode.objects.all().order_by("-created_at")
    schema = ProjectSchema()
    serializer_class = QRCodeSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    filter_backends = [SearchFilter]
    search_fields = ["name", "qr_type__name"]

    def get_permissions(self):
        if self.action in {"scan", "analytics"}:
            return [AllowAny()]
        return super().get_permissions()

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "scan":
            return queryset
        return queryset.filter(created_by=self.request.user)

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")

        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()

        return request.META.get("REMOTE_ADDR")

    def _get_qr_by_identifier(self, identifier):
        if identifier in (None, ""):
            raise NotFound()

        qr = QRCode.objects.filter(short_code=identifier).first()
        if qr is not None:
            return qr

        qr = QRCode.objects.filter(link_name=identifier).first()
        if qr is not None:
            return qr

        try:
            UUID(str(identifier))
        except (TypeError, ValueError):
            raise NotFound()

        qr = QRCode.objects.filter(pk=identifier).first()
        if qr is None:
            raise NotFound()
        return qr

    def get_serializer_class(self):
        if self.action == "preview":
            return QRCodeSummarySerializer
        # if self.action == "scan":
        #     return QRCodeBundleSerializer
        if self.action == "save_design":
            return QRDesignSerializer
        if self.action == "duplicate":
            return QRCodeDuplicateRequestSerializer
        if self.action in {"create","scan", "update", "partial_update", "retrieve"}:
            return QRCodeBundleSerializer
        return super().get_serializer_class()

    def list(self, request, *args, **kwargs):
        qrcodes = self.filter_queryset(self.get_queryset())
        paginator = CustomPagination()
        page = paginator.paginate_queryset(qrcodes, request, view=self)
        serializer = self.get_serializer(page, many=True)
        response = paginator.get_paginated_response(serializer.data)
        response.data["message"] = "QR codes fetched successfully."
        return response

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

        qr_code = serializer.validated_data.get("qr_code")
        design = QRDesign.objects.filter(qr_code=qr_code).first()
        is_update = design is not None

        if design is not None:
            serializer = self.get_serializer(design, data=request.data)
        else:
            serializer = self.get_serializer(data=request.data)

        serializer.is_valid(raise_exception=True)
        design = serializer.save()
        return Response(
            {"data": self.get_serializer(design).data, "message": "QR design saved successfully."},
            status=status.HTTP_200_OK if is_update else status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="preview")
    def preview(self, request, *args, **kwargs):
        qr_code = self.get_object()
        serializer = self.get_serializer(qr_code)
        return Response(
            {"data": serializer.data, "message": "QR preview fetched successfully."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], url_path="scan")
    def scan(self, request, *args, **kwargs):
        try:
            qr_code = self._get_qr_by_identifier(kwargs.get("pk"))
        except QRCode.DoesNotExist:
            raise NotFound()
        request_data = {
            "ip": self._get_client_ip(request),
            "user_agent": request.META.get("HTTP_USER_AGENT", ""),
            "referer": request.META.get("HTTP_REFERER", ""),
            "language": request.META.get("HTTP_ACCEPT_LANGUAGE", ""),
            "screen_width": request.query_params.get("sw"),
            "screen_height": request.query_params.get("sh"),
        }

        try:
            AnalyticsTracker(qr=qr_code, request_data=request_data).process(suppress_exceptions=False)
        except ValidationError:
            return Response(
                {
                    "data": ["Scan limit reached for this QR code."],
                    "msg": "Scan limit reached for this QR code.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(qr_code)
        return Response(
            {"data": serializer.data, "message": "QR Scan fetched successfully."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="analytics")
    def analytics(self, request, *args, **kwargs):
        try:
            qr_code = self._get_qr_by_identifier(kwargs.get("pk"))
        except QRCode.DoesNotExist:
            raise NotFound()
        request_data = {
            "ip": self._get_client_ip(request),
            "user_agent": request.META.get("HTTP_USER_AGENT", ""),
            "referer": request.META.get("HTTP_REFERER", ""),
            "language": request.META.get("HTTP_ACCEPT_LANGUAGE", ""),
            "screen_width": request.query_params.get("sw"),
            "screen_height": request.query_params.get("sh"),
        }

        # Queue analytics
        # track_scan.delay(
        #     qr_id=qr_code.id,
        #     request_data=request_data,
        # )
        track_scan(
            qr_id=qr_code.id,
            request_data=request_data,
        )

        serializer = self.get_serializer(qr_code)
        return Response(
            {"data": serializer.data, "message": "QR Scan fetched successfully."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="duplicate")
    def duplicate(self, request, *args, **kwargs):
        source_qr = self.get_object()
        serializer = self.get_serializer(
            data=request.data,
            context={**self.get_serializer_context(), "source_qr": source_qr},
        )
        serializer.is_valid(raise_exception=True)
        duplicate_qr = serializer.save()
        return Response(
            {
                "data": QRCodeBundleSerializer(duplicate_qr, context=self.get_serializer_context()).data,
                "message": "QR code duplicated successfully.",
            },
            status=status.HTTP_201_CREATED,
        )


class TemplateViewSet(viewsets.ModelViewSet):
    queryset = TemplateDesign.objects.all()
    serializer_class = TemplateDesignSerializer
    permission_classes = [IsAuthenticated]
    schema = ProjectSchema()
    authentication_classes = [JWTAuthentication]
    filter_backends = [SearchFilter]
    search_fields = ["created_by__email"]

    def list(self, request, *args, **kwargs):
        templates = self.filter_queryset(self.get_queryset())
        paginator = CustomPagination()
        page = paginator.paginate_queryset(templates, request, view=self)
        serializer = self.get_serializer(page, many=True)
        response = paginator.get_paginated_response(serializer.data)
        response.data["message"] = "Templates fetched successfully."
        return response

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


class VideoViewSet(viewsets.ViewSet):
    schema = ProjectSchema()
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @transaction.atomic
    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request):
        serializer = VideoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        # playlist_id = data.get("playlist_id")

        # ----------------------------------------
        # Existing Playlist
        # ----------------------------------------
        try:
            playlist = QrMedia.objects.get(qr_code__id=data.get("qr_code"))
            created_playlist = False
        except QrMedia.DoesNotExist:
            created_playlist = True


        # ----------------------------------------
        # Create Playlist
        # ----------------------------------------
        if created_playlist:
            qr = QRCode.objects.get(pk=data["qr_code"])

            playlist = QrMedia.objects.create(
                qrcode=qr,
                qr_code=qr,
                title=data.get("playlist_title", ""),
            )

            created_playlist = True

        # ----------------------------------------
        # Sort Order
        # ----------------------------------------

        max_order = playlist.videos.aggregate(max_order=Max("sort_order")).get("max_order") or 0

        # ----------------------------------------
        # Save Video
        # ----------------------------------------

        video = MediaItem.objects.create(
            qr_media=playlist,
            title=data.get("video_title", ""),
            description=data.get("video_description", ""),
            video=data["video"],
            thumbnail=data.get("thumbnail"),
            sort_order=max_order + 1,
        )

        return Response(
            {
                "data": {
                    "playlist_id": playlist.id,
                    "video_id": video.id,
                    "file_path":str(video.video.url),
                    "thumbnail":str(video.thumbnail.url) if video.thumbnail else None,
                    "created_playlist": created_playlist,
                    "video_count": playlist.videos.count(),
                },
                "message": (
                    "Playlist created successfully."
                    if created_playlist
                    else "Video uploaded successfully."
                ),
            },
            status=status.HTTP_201_CREATED,
        )

    @transaction.atomic
    @action(detail=False, methods=["delete"], url_path="delete-video")
    def delete_video(self, request):
        serializer = VideoDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            media_item = MediaItem.objects.get(pk=serializer.validated_data["id"])
        except MediaItem.DoesNotExist:
            return Response(
                {"data": {}, "message": "Video media item not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        media_item.delete()
        return Response(
            {"data": {"id": str(media_item.id)}, "message": "Video media item deleted successfully."},
            status=status.HTTP_200_OK,
        )

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        try:
            media_item = MediaItem.objects.select_related("qr_media").get(pk=kwargs.get("pk"))
        except MediaItem.DoesNotExist:
            return Response(
                {"data": {}, "message": "Video media item not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = VideoUpdateSerializer(data=request.data, partial=kwargs.pop("partial", False))
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        for field in ["title", "description", "sort_order", "is_active"]:
            if field in data:
                setattr(media_item, field, data[field])

        thumbnail_file = request.FILES.get("thumbnail")
        if thumbnail_file is not None:
            old_thumbnail = media_item.thumbnail
            media_item.thumbnail = thumbnail_file
            media_item.save()
            if old_thumbnail and old_thumbnail.name and old_thumbnail.name != media_item.thumbnail.name:
                old_thumbnail.storage.delete(old_thumbnail.name)
        else:
            media_item.save()

        video_file = request.FILES.get("video")
        if video_file is not None:
            old_video = media_item.video
            media_item.video = video_file
            media_item.save()
            if old_video and old_video.name and old_video.name != media_item.video.name:
                old_video.storage.delete(old_video.name)
        else:
            media_item.save()

        return Response(
            {
                "data": {
                    "id": str(media_item.id),
                    "playlist_id": str(media_item.qr_media_id),
                    "video_id": str(media_item.id),
                    "thumbnail": str(media_item.thumbnail.url) if media_item.thumbnail else None,
                    "file_path": str(media_item.video.url) if media_item.video else None,
                },
                "message": "Video media item updated successfully.",
            },
            status=status.HTTP_200_OK,
        )

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)
