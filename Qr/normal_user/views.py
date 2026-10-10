from django.contrib.contenttypes.models import ContentType
from django.core import cache
from django.utils import timezone
from django.db import transaction
from uuid import UUID
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
import secrets
from datetime import timedelta
from django.template.loader import render_to_string
from django.http import JsonResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.filters import SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from DynamicQR.schemas import PaginatedAutoSchema
from Qr.services.domain_verification import DomainVerificationService

from Qr.tasks import (
    process_qr_import,
    get_importer,
    load_import_workbook_rows,
    verify_and_activate_domain_async,
)
from accounts.authentication import JWTAuthentication
from accounts.models import User
from django.db.models import Count, Q, Max
from django.db.models import IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from Qr.models import Project, QRCode, TemplateDesign, QrMedia, MediaItem, QRDesign, Invitations, SharePermissions, \
    QRImportJob, CustomDomain, QRSchedule
from Qr.access import ProjectRolePermission, QRRolePermission, ROLE_NAMES, project_role, qr_role, role_allows
from Qr.serializers import (
    ProjectSerializer,
    ProjectDetailSerializer,
    ProjectQRActionSerializer,
    ProjectMemberRoleSerializer,
    QRCodeSerializer,
    QRCodeBundleSerializer,
    QRCodeDuplicateRequestSerializer,
    QRDesignSerializer,
    QRCodeSummarySerializer, TemplateDesignSerializer, VideoDeleteSerializer, VideoUploadSerializer,
    VideoUpdateSerializer, ProjectInvitationSerializer, ProjectInvitationDetailSerializer, QRImportJobUploadSerializer,
    QRImportJobStatusSerializer, CustomDomainSerializer,
)
from DynamicQR.pagination import CustomPagination
from analytics.task import track_scan
from subscriptions.models import Subscription
from subscriptions.quota_service import (
    QRLimitExceeded,
    TeamMemberLimitExceeded,
    check_qr_capacity,
    check_team_member_capacity,
    get_bulk_upload_limit,
    lock_account_owner,
)
from subscriptions.usage import PackageScanLimitExceeded, get_package_scan_quota
from system.models import ConfigChoice
from Qr.services.account_ownership import account_owner_for_project, account_owner_for_qr


def _build_limit_response(message, limit, used, requested=1):
    remaining = None if limit is None else max(limit - used, 0)
    return Response(
        {
            "data": {
                "limit": limit,
                "used": used,
                "remaining": remaining,
                "requested": requested,
            },
            "message": message,
        },
        status=status.HTTP_403_FORBIDDEN,
    )


def _enforce_qr_limit(user, requested=1):
    try:
        check_qr_capacity(user, requested=requested)
    except QRLimitExceeded as exc:
        return _build_limit_response(
            str(exc),
            exc.limit,
            exc.used,
            exc.requested,
        )
    return None


def _enforce_package_scan_limit(qr_code):
    limit, used = get_package_scan_quota(account_owner_for_qr(qr_code))
    if limit is not None and used >= limit:
        return _build_limit_response("Scan limit reached for your package.", limit, used)
    return None


def _get_domain_add_limit(user):
    subscription = Subscription.get_usage_subscription_for_user(user)
    if not subscription:
        return 0

    if subscription.domain_add_limit is not None:
        return subscription.domain_add_limit

    package_plan = getattr(subscription, "package_plan", None)
    return package_plan.max_domain_add if package_plan else 0


def _enforce_domain_add_limit(user):
    domain_add_limit = _get_domain_add_limit(user)
    if domain_add_limit is None:
        return None

    used = CustomDomain.objects.filter(
        user=user,
        is_deleted=False,
    ).count()
    if used + 1 > domain_add_limit:
        return _build_limit_response(
            "Custom domain limit reached for your package.",
            domain_add_limit,
            used,
        )

    return None


class ProjectSchema(PaginatedAutoSchema):
    def get_tags(self, path, method):
        tag_by_basename = {
            "project": "Projects",
            "Qr": "QR Codes",
            "qr-recycle-bin": "Recycle Bin",
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
        if action == "members":
            return "List accepted project members. Only the project owner and Admin members can use this endpoint."
        if action == "member_detail" and method.upper() == "PATCH":
            return "Change an accepted member's role to an active Admin, Edit, or View role."
        if action == "member_detail" and method.upper() == "DELETE":
            return "Remove an accepted member from the project."
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
        if action == "member_detail" and method.upper() == "PATCH":
            return ProjectMemberRoleSerializer()
        if action == "invitations":
            return ProjectInvitationSerializer()
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
        if getattr(self.view, "basename", None) == "import" and action == "import_status":
            return QRImportJobStatusSerializer()
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
        if action == "invitations":
            self.request_media_types = ["application/json"]
            serializer = self.get_request_serializer(path, method)
            item_schema = self.get_reference(serializer) if isinstance(serializer, ProjectInvitationSerializer) else {}
            return {
                "content": {
                    "application/json": {"schema": item_schema}
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
        if getattr(self.view, "basename", None) == "import" and action == "create":
            self.request_media_types = ["multipart/form-data"]
            serializer = self.get_request_serializer(path, method)
            item_schema = self.get_reference(serializer) if isinstance(serializer, QRImportJobUploadSerializer) else {}
            return {
                "content": {
                    "multipart/form-data": {"schema": item_schema}
                }
            }
        if getattr(self.view, "basename", None) == "import" and action == "import_status":
            serializer = self.get_response_serializer(path, method)
            item_schema = self.get_reference(serializer) if isinstance(serializer, QRImportJobStatusSerializer) else {}
            return {
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "data": item_schema,
                                "message": {
                                    "type": "string",
                                    "example": "Import job status retrieved successfully.",
                                },
                                "status": {
                                    "type": "string",
                                    "example": "success",
                                },
                            },
                            "required": ["data", "message", "status"],
                        }
                    }
                }
            }
        return super().get_request_body(path, method)


class InvitationSchema(PaginatedAutoSchema):
    def get_description(self, path, method):
        action = getattr(self.view, "action", None)
        if action == "sent_invitations":
            return "List invitations sent by the user or for projects they administer. Use the optional `status` query parameter to filter by invitation status name."
        if action == "my_invitations":
            return "List invitations received by the authenticated user."
        return super().get_description(path, method)

    def get_filter_parameters(self, path, method):
        params = super().get_filter_parameters(path, method)
        if getattr(self.view, "action", None) == "sent_invitations":
            params.append(
                {
                    "name": "status",
                    "required": False,
                    "in": "query",
                    "description": "Filter sender invitations by invitation status name.",
                    "schema": {"type": "string"},
                }
            )
        return params


class CustomDomainSchema(PaginatedAutoSchema):
    def get_tags(self, path, method):
        return ["Custom Domain API"]

    def get_operation_id(self, path, method):
        action = getattr(self.view, "action", None) or "unknown"
        return f"custom_domain_{action}"

    def get_description(self, path, method):
        action = getattr(self.view, "action", None)
        if action == "list":
            return "List the authenticated user's custom domains."
        if action == "retrieve":
            return "Retrieve a custom domain owned by the authenticated user."
        if action == "create":
            return "Create a custom domain for the authenticated user."
        if action in {"update", "partial_update"}:
            return "Update a custom domain owned by the authenticated user."
        if action == "destroy":
            return "Delete a custom domain owned by the authenticated user."
        if action == "verify":
            return "Verify the custom domain by checking its CNAME record."
        if action == "verify_by_token":
            return "Verify a custom domain using the verification token passed in the `token` query parameter."
        return super().get_description(path, method)

    def get_request_body(self, path, method):
        if getattr(self.view, "action", None) in {"verify", "verify_by_token"}:
            return None
        return super().get_request_body(path, method)

    def get_filter_parameters(self, path, method):
        params = super().get_filter_parameters(path, method)
        if getattr(self.view, "action", None) == "list":
            params.append(
                {
                    "name": "status",
                    "required": False,
                    "in": "query",
                    "description": "Filter custom domains by status. Use one of the `CustomDomain.Status` values.",
                    "schema": {
                        "type": "string",
                        "enum": [choice[0] for choice in CustomDomain.Status.choices],
                    },
                }
            )
        return params

    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if getattr(self.view, "action", None) == "verify_by_token":
            operation.setdefault("parameters", []).append(
                {
                    "name": "token",
                    "required": True,
                    "in": "query",
                    "description": "Verification token received for the custom domain.",
                    "schema": {"type": "string"},
                }
            )
        return operation

def send_project_invitation_email(invitation):
    invitation_url = (
        f"{settings.FRONTEND_URL.rstrip('/')}"
        f"/project/invitations/{invitation.token}"
    )

    context = {
        "invited_by_name": invitation.invited_by.get_full_name()
        or invitation.invited_by.email,
        "project_name": invitation.content_object.name,
        "role": invitation.role.name,
        "invitation_url": invitation_url,
        "expires_at": invitation.expires_at,
    }

    html_content = render_to_string(
        "email/project_invitation.html",
        context,
    )

    text_content = render_to_string(
        "email/project_invitation.txt",
        context,
    )

    email = EmailMultiAlternatives(
        subject=f"You've been invited to {invitation.content_object.name}",
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[invitation.email],
    )

    email.attach_alternative(
        html_content,
        "text/html",
    )

    email.send()

class ProjectViewSet(viewsets.ModelViewSet):
    schema = ProjectSchema()
    authentication_classes = [JWTAuthentication]
    model = Project
    permission_classes = [IsAuthenticated, ProjectRolePermission]
    lookup_value_regex = r"[0-9a-fA-F-]{36}"
    filter_backends = [SearchFilter]
    search_fields = ["name", "description"]
    serializer_class = ProjectSerializer
    queryset = Project.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        project_content_type = ContentType.objects.get_for_model(Project)
        accepted_people_count = SharePermissions.objects.filter(
            content_type=project_content_type,
            resource_id=OuterRef("pk"),
            is_deleted=False,
        ).values("resource_id").annotate(
            total=Count("id", distinct=True)
        ).values("total")[:1]

        queryset = queryset.annotate(
            qr_count=Count("qrcode", filter=Q(qrcode__is_deleted=False)),
            accepted_people_count=Coalesce(
                Subquery(accepted_people_count, output_field=IntegerField()),
                Value(0),
            ),
        )
        shared_project_ids = SharePermissions.objects.filter(
            user_id=self.request.user,
            content_type=project_content_type,
            is_deleted=False,
            role__category__name__iexact="sharing_permission",
            role__name__in=("Admin", "Edit", "View"),
            role__status=True,
        ).values_list("resource_id", flat=True)

        queryset = queryset.filter(
            Q(owner=self.request.user) | Q(id__in=shared_project_ids)
        )

        if self.action == "list":
            requested_permissions = [
                permission.strip().lower()
                for value in self.request.query_params.getlist("permission")
                for permission in value.split(",")
                if permission.strip()
            ]
            valid_permissions = {"owner", "admin", "edit", "view"}
            invalid_permissions = set(requested_permissions) - valid_permissions
            if invalid_permissions:
                raise ValidationError({
                    "permission": (
                        "Unsupported permission(s): "
                        + ", ".join(sorted(invalid_permissions))
                        + ". Allowed values: owner, admin, edit, view."
                    )
                })

            if requested_permissions:
                permission_filter = Q(pk__in=[])
                if "owner" in requested_permissions:
                    permission_filter |= Q(owner=self.request.user)
                shared_permissions = set(requested_permissions) & {"admin", "edit", "view"}
                if shared_permissions:
                    filtered_project_ids = SharePermissions.objects.filter(
                        user_id=self.request.user,
                        content_type=project_content_type,
                        is_deleted=False,
                        role__category__name__iexact="sharing_permission",
                        role__name__in=shared_permissions,
                        role__status=True,
                    ).values_list("resource_id", flat=True)
                    permission_filter |= Q(id__in=filtered_project_ids)
                queryset = queryset.filter(permission_filter)

        return queryset.order_by("-created_at")

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
            with transaction.atomic():
                qr = (
                    QRCode.objects.select_for_update()
                    .select_related("project__owner", "created_by")
                    .get(id=qr_id)
                )
                if not role_allows(qr_role(request.user, qr), "edit"):
                    raise PermissionDenied("You cannot move this QR code.")

                current_owner = account_owner_for_qr(qr)
                destination_owner = account_owner_for_project(project, request.user)
                if current_owner.pk != destination_owner.pk:
                    destination_owner = lock_account_owner(destination_owner)
                    check_qr_capacity(destination_owner)

                qr.project = project
                qr.save(update_fields=["project"])
        except QRCode.DoesNotExist:
            return Response(
                {"data": {}, "message": "QR code not found."},
                status=400,
            )
        except QRLimitExceeded as exc:
            return _build_limit_response(str(exc), exc.limit, exc.used, exc.requested)
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
            with transaction.atomic():
                qr = (
                    QRCode.objects.select_for_update()
                    .select_related("project__owner", "created_by")
                    .get(id=qr_id, project=project)
                )
                current_owner = account_owner_for_qr(qr)
                destination_owner = qr.created_by
                if current_owner.pk != destination_owner.pk:
                    destination_owner = lock_account_owner(destination_owner)
                    check_qr_capacity(destination_owner)

                qr.project = None
                qr.save(update_fields=["project"])
        except QRCode.DoesNotExist:
            return Response(
                {"data": {}, "message": "QR code not found in this project."},
                status=400,
            )
        except QRLimitExceeded as exc:
            return _build_limit_response(str(exc), exc.limit, exc.used, exc.requested)
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
        qr_content_type = ContentType.objects.get_for_model(QRCode)
        project_content_type = ContentType.objects.get_for_model(Project)

        shared_qr_ids = SharePermissions.objects.filter(
            user_id=request.user,
            content_type=qr_content_type,
            is_deleted=False,
            resource_id__isnull=False,
        ).values_list("resource_id", flat=True)

        shared_project_ids = SharePermissions.objects.filter(
            user_id=request.user,
            content_type=project_content_type,
            resource_id=project.id,
            is_deleted=False,
        ).exists()

        qrcodes = QRCode.objects.filter(
            project=project,
            is_deleted=False,
        ).filter(
            Q(created_by=request.user)
            | Q(project__owner=request.user)
            | Q(id__in=shared_qr_ids)
            | (Q(project=project) if shared_project_ids else Q(pk__in=[]))
        ).order_by("name")
        qrcodes = self.filter_queryset(qrcodes)
        paginator = CustomPagination()
        page = paginator.paginate_queryset(qrcodes, request, view=self)
        serializer = QRCodeSerializer(page, many=True, context={"request": request})
        response = paginator.get_paginated_response(serializer.data)
        response.data["message"] = "Project QR codes fetched successfully."
        return response

    @action(detail=True, methods=["get"], url_path="members")
    def members(self, request, *args, **kwargs):
        project = self.get_object()
        if not role_allows(project_role(request.user, project), "admin"):
            raise PermissionDenied("Only project owners and admins can manage members.")

        project_content_type = ContentType.objects.get_for_model(Project)
        memberships = SharePermissions.objects.filter(
            content_type=project_content_type,
            resource_id=project.id,
            is_deleted=False,
            role__category__name__iexact="sharing_permission",
            role__name__in=("Admin", "Edit", "View"),
        ).select_related("user_id", "role").order_by("user_id__email", "created_at")

        data = [
            {
                "permission_id": str(membership.id),
                "user_id": str(membership.user_id_id),
                "email": membership.user_id.email,
                "full_name": membership.user_id.get_full_name(),
                "role_id": str(membership.role_id),
                "role": membership.role.name,
                "role_active": membership.role.status,
            }
            for membership in memberships
        ]
        return Response(
            {"data": data, "message": "Project members fetched successfully."},
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["patch", "delete"],
        url_path=r"members/(?P<member_id>[0-9a-fA-F-]{36})",
    )
    def member_detail(self, request, member_id=None, *args, **kwargs):
        project = self.get_object()
        if not role_allows(project_role(request.user, project), "admin"):
            raise PermissionDenied("Only project owners and admins can manage members.")

        project_content_type = ContentType.objects.get_for_model(Project)
        memberships = SharePermissions.objects.filter(
            user_id_id=member_id,
            content_type=project_content_type,
            resource_id=project.id,
            is_deleted=False,
        ).select_related("user_id", "role")
        membership = memberships.first()
        if membership is None:
            raise NotFound("Project member not found.")

        if request.method == "PATCH":
            serializer = ProjectMemberRoleSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            role = serializer.validated_data["role"]
            memberships.update(role=role)
            return Response(
                {
                    "data": {
                        "user_id": str(membership.user_id_id),
                        "email": membership.user_id.email,
                        "role_id": str(role.id),
                        "role": role.name,
                    },
                    "message": "Project member role updated successfully.",
                },
                status=status.HTTP_200_OK,
            )

        removed_count = memberships.update(is_deleted=True, deleted_at=timezone.now())
        return Response(
            {
                "data": {"user_id": str(membership.user_id_id), "removed_count": removed_count},
                "message": "Project member removed successfully.",
            },
            status=status.HTTP_200_OK,
        )


class QRCodeViewSet(viewsets.ModelViewSet):
    queryset = QRCode.objects.all().order_by("-created_at")
    schema = ProjectSchema()
    serializer_class = QRCodeSerializer
    permission_classes = [IsAuthenticated, QRRolePermission]
    authentication_classes = [JWTAuthentication]
    filter_backends = [SearchFilter]
    search_fields = ["name", "qr_type__name"]

    def get_permissions(self):
        if self.action in {"scan", "analytics"}:
            return [AllowAny()]
        return super().get_permissions()

    def _get_accessible_qr_queryset(self, include_deleted=False):
        queryset = QRCode.objects.get_deleted() if include_deleted else QRCode.objects.all()
        qr_content_type = ContentType.objects.get_for_model(QRCode)
        project_content_type = ContentType.objects.get_for_model(Project)

        shared_qr_ids = SharePermissions.objects.filter(
            user_id=self.request.user,
            content_type=qr_content_type,
            is_deleted=False,
            role__category__name__iexact="sharing_permission",
            role__name__in=("Admin", "Edit", "View"),
            role__status=True,
        ).values_list("resource_id", flat=True)

        shared_project_ids = SharePermissions.objects.filter(
            user_id=self.request.user,
            content_type=project_content_type,
            is_deleted=False,
            role__category__name__iexact="sharing_permission",
            role__name__in=("Admin", "Edit", "View"),
            role__status=True,
        ).values_list("resource_id", flat=True)

        return queryset.filter(
            Q(created_by=self.request.user, project__isnull=True)
            | Q(project__owner=self.request.user)
            | Q(id__in=shared_qr_ids)
            | Q(project_id__in=shared_project_ids)
        )

    def get_queryset(self):
        queryset = self._get_accessible_qr_queryset(include_deleted=False)
        if self.action == "list":
            return queryset.filter(is_draft=False)
        return queryset

    def _get_client_ip(self, request):
        x_real_ip = request.META.get("HTTP_X_REAL_IP")
        if x_real_ip:
            return x_real_ip.strip()

        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()

        return request.META.get("REMOTE_ADDR")

    def _get_qr_by_identifier(self, identifier):
        if identifier in (None, ""):
            raise NotFound()

        # Draft QR codes are not published and must never be reachable from
        # any public scan-related endpoint.
        qr = QRCode.objects.filter(short_code=identifier, is_draft=False).first()
        if qr is not None:
            return qr

        qr = QRCode.objects.filter(link_name=identifier, is_draft=False).first()
        if qr is not None:
            return qr

        try:
            UUID(str(identifier))
        except (TypeError, ValueError):
            raise NotFound()

        qr = QRCode.objects.filter(pk=identifier, is_draft=False).first()
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
        if not serializer.is_valid():
            return Response(
                {"data": serializer.errors, "message": "Validation error."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        project = serializer.validated_data["QRCode"].get("project")
        account_owner = account_owner_for_project(project, request.user)
        try:
            with transaction.atomic():
                account_owner = lock_account_owner(account_owner)
                check_qr_capacity(account_owner)
                qr_code = serializer.save()
        except QRLimitExceeded as exc:
            return _build_limit_response(str(exc), exc.limit, exc.used, exc.requested)
        return Response(
            {"data": self.get_serializer(qr_code).data, "message": "QR code created successfully."},
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if not serializer.is_valid():
            return Response(
                {"data": serializer.errors, "message": "Validation error."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qr_data = serializer.validated_data.get("QRCode", {})
        target_project = qr_data.get("project", instance.project)
        try:
            with transaction.atomic():
                locked_instance = (
                    QRCode.objects.select_for_update()
                    .select_related("project__owner", "created_by")
                    .get(pk=instance.pk)
                )
                current_owner = account_owner_for_qr(locked_instance)
                target_owner = account_owner_for_project(target_project, locked_instance.created_by)
                if current_owner.pk != target_owner.pk:
                    target_owner = lock_account_owner(target_owner)
                    check_qr_capacity(target_owner)
                serializer.instance = locked_instance
                qr_code = serializer.save()
        except QRLimitExceeded as exc:
            return _build_limit_response(str(exc), exc.limit, exc.used, exc.requested)
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
        if not role_allows(qr_role(request.user, qr_code), "edit"):
            raise PermissionDenied("You cannot edit this QR code.")
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

    @action(detail=True, methods=["post"], url_path="scan")
    def scan(self, request, *args, **kwargs):
        try:
            qr_code = self._get_qr_by_identifier(kwargs.get("pk"))
        except QRCode.DoesNotExist:
            raise NotFound()

        qr_schedule = QRSchedule.objects.filter(qr_code=qr_code, is_deleted=False).first()
        if qr_schedule and (qr_schedule.start_date or qr_schedule.end_date):
            now = timezone.now()
            # Enforce whichever boundary is configured.
            if qr_schedule.start_date and now < qr_schedule.start_date:
                return Response(
                    {"data": {}, "message": "QR code is not active yet."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if qr_schedule.end_date and now > qr_schedule.end_date:
                return Response(
                    {"data": {}, "message": "QR code has expired."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        is_enabled, password_saved = qr_code.is_password_enabled()
        if is_enabled:
            password_ui = request.data.get("password")
            if not password_ui:
                return Response({"data":{"password_enabled":True}, "message": "Password enabled."}, status=status.HTTP_400_BAD_REQUEST)
            if password_ui != password_saved:
                return Response({"data":False, "message": "Wrong password."}, status=status.HTTP_400_BAD_REQUEST)

        limit_response = _enforce_package_scan_limit(qr_code)
        if limit_response is not None:
            return limit_response

        serializer = self.get_serializer(qr_code)
        return Response(
            {"data": serializer.data, "message": "QR Scan fetched successfully."},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="plans/scan")
    def scan_plan(self, request, *args, **kwargs):
        qr_id = request.data.get("qr_id") or request.query_params.get("qr_id")
        if not qr_id:
            return Response(
                {"data": {}, "message": "qr_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            qr_code = self._get_qr_by_identifier(qr_id)
        except QRCode.DoesNotExist:
            raise NotFound()

        qr_schedule = QRSchedule.objects.filter(qr_code=qr_code, is_deleted=False).first()
        if qr_schedule and (qr_schedule.start_date or qr_schedule.end_date):
            now = timezone.now()
            if qr_schedule.start_date and now < qr_schedule.start_date:
                return Response(
                    {"data": {}, "message": "QR code is not active yet."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if qr_schedule.end_date and now > qr_schedule.end_date:
                return Response(
                    {"data": {}, "message": "QR code has expired."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        is_enabled, password_saved = qr_code.is_password_enabled()
        if is_enabled:
            password_ui = request.data.get("password")
            if not password_ui:
                return Response(
                    {"data": {"password_enabled": True}, "message": "Password enabled."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if password_ui != password_saved:
                return Response({"data": False, "message": "Wrong password."}, status=status.HTTP_400_BAD_REQUEST)

        limit_response = _enforce_package_scan_limit(qr_code)
        if limit_response is not None:
            return limit_response

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

        client_ip = self._get_client_ip(request)

        print("====================================")
        print("REMOTE_ADDR:", request.META.get("REMOTE_ADDR"))
        print("X-REAL-IP:", request.META.get("HTTP_X_REAL_IP"))
        print("X-FORWARDED-FOR:", request.META.get("HTTP_X_FORWARDED_FOR"))
        print("FINAL CLIENT IP:", client_ip)
        print("====================================")

        request_data = {
            "ip": client_ip,
            "user_agent": request.META.get("HTTP_USER_AGENT", ""),
            "referer": request.META.get("HTTP_REFERER", ""),
            "language": request.META.get("HTTP_ACCEPT_LANGUAGE", ""),
            "screen_width": request.query_params.get("sw"),
            "screen_height": request.query_params.get("sh"),
        }

        print("REQUEST DATA:", request_data)

        try:
            track_scan(
                qr_id=qr_code.id,
                request_data=request_data,
            )
        except PackageScanLimitExceeded as exc:
            return _build_limit_response(str(exc), exc.limit, exc.used)

        serializer = self.get_serializer(qr_code)

        return Response(
            {
                "data": serializer.data,
                "message": "QR Scan fetched successfully."
            },
            status=status.HTTP_200_OK,
        )
    @action(detail=True, methods=["post"], url_path="duplicate")
    def duplicate(self, request, *args, **kwargs):
        source_qr = self.get_object()
        try:
            with transaction.atomic():
                source_qr = (
                    QRCode.objects.select_for_update()
                    .select_related("project__owner", "created_by")
                    .get(pk=source_qr.pk)
                )
                account_owner = lock_account_owner(account_owner_for_qr(source_qr))
                check_qr_capacity(account_owner)
                serializer = self.get_serializer(
                    data=request.data,
                    context={**self.get_serializer_context(), "source_qr": source_qr},
                )
                serializer.is_valid(raise_exception=True)
                duplicate_qr = serializer.save()
        except QRLimitExceeded as exc:
            return _build_limit_response(str(exc), exc.limit, exc.used, exc.requested)
        return Response(
            {
                "data": QRCodeBundleSerializer(duplicate_qr, context=self.get_serializer_context()).data,
                "message": "QR code duplicated successfully.",
            },
            status=status.HTTP_201_CREATED,
        )


class QRRecycleBinViewSet(viewsets.GenericViewSet):
    schema = ProjectSchema()
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = QRCodeSerializer
    filter_backends = [SearchFilter]
    search_fields = ["name", "qr_type__name"]

    def _get_accessible_deleted_qr_queryset(self, required="view"):
        qr_content_type = ContentType.objects.get_for_model(QRCode)
        project_content_type = ContentType.objects.get_for_model(Project)
        allowed_roles = {
            "view": ("Admin", "Edit", "View"),
            "admin": ("Admin",),
        }[required]

        shared_qr_ids = SharePermissions.objects.filter(
            user_id=self.request.user,
            content_type=qr_content_type,
            is_deleted=False,
            role__category__name__iexact="sharing_permission",
            role__name__in=allowed_roles,
            role__status=True,
        ).values_list("resource_id", flat=True)

        shared_project_ids = SharePermissions.objects.filter(
            user_id=self.request.user,
            content_type=project_content_type,
            is_deleted=False,
            role__category__name__iexact="sharing_permission",
            role__name__in=allowed_roles,
            role__status=True,
        ).values_list("resource_id", flat=True)

        return QRCode.objects.get_deleted().filter(
            Q(created_by=self.request.user, project__isnull=True)
            | Q(project__owner=self.request.user)
            | Q(id__in=shared_qr_ids)
            | Q(project_id__in=shared_project_ids)
        ).annotate(scanned_no=Count("scan_events", distinct=True))

    def list(self, request, *args, **kwargs):
        # The recycle-bin list is limited to the user's own QR codes and
        # resources shared with an Admin role. View/Edit shares must not
        # expose deleted QR codes here.
        qrcodes = self._get_accessible_deleted_qr_queryset(required="admin")

        qr_type_id = request.query_params.get("qr_type") or request.query_params.get("qr_type_id")
        if qr_type_id:
            qrcodes = qrcodes.filter(qr_type_id=qr_type_id)

        qrcodes = qrcodes.order_by("-deleted_at", "-created_at")
        qrcodes = self.filter_queryset(qrcodes)

        paginator = CustomPagination()
        page = paginator.paginate_queryset(qrcodes, request, view=self)
        serialized_qrcodes = QRCodeSerializer(page, many=True, context={"request": request}).data
        for qr_code, serialized_qr_code in zip(page, serialized_qrcodes):
            serialized_qr_code["deleted_at"] = qr_code.deleted_at
            serialized_qr_code["scanned_no"] = qr_code.scanned_no

        response = paginator.get_paginated_response(serialized_qrcodes)
        response.data["message"] = "Deleted QR codes fetched successfully."
        return response

    @action(detail=False, methods=["post"], url_path="hard-delete")
    def hard_delete(self, request, *args, **kwargs):
        qr_ids = request.data.get("ids") or request.data.get("qr_ids") or []
        if not isinstance(qr_ids, list) or not qr_ids:
            return Response(
                {"data": {}, "message": "ids is required and must be a non-empty list."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qr_codes = self._get_accessible_deleted_qr_queryset(required="admin").filter(id__in=qr_ids)
        found_ids = set(str(qr.id) for qr in qr_codes)
        requested_ids = {str(qr_id) for qr_id in qr_ids}

        if found_ids != requested_ids:
            missing_ids = sorted(requested_ids - found_ids)
            return Response(
                {
                    "data": {"missing_ids": missing_ids},
                    "message": "One or more QR codes could not be found in recycle bin.",
                },
                status=400,
            )

        deleted_count = 0
        for qr_code in qr_codes:
            qr_code.hard_delete()
            deleted_count += 1

        return Response(
            {
                "data": {"deleted_count": deleted_count, "ids": sorted(found_ids)},
                "message": "QR codes permanently deleted successfully.",
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="restore")
    def restore(self, request, *args, **kwargs):
        qr_ids = request.data.get("ids") or request.data.get("qr_ids") or []

        if not isinstance(qr_ids, list) or not qr_ids:
            return Response(
                {
                    "data": {},
                    "message": "ids is required and must be a non-empty list.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get only deleted QR codes the current user has access to
        qr_codes = self._get_accessible_deleted_qr_queryset(required="admin").filter(
            id__in=qr_ids
        )

        found_ids = {str(qr.id) for qr in qr_codes}
        requested_ids = {str(qr_id) for qr_id in qr_ids}

        # Make sure all requested IDs are accessible and exist in recycle bin
        if found_ids != requested_ids:
            missing_ids = sorted(requested_ids - found_ids)

            return Response(
                {
                    "data": {
                        "missing_ids": missing_ids,
                    },
                    "message": "One or more QR codes could not be found in recycle bin.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                locked_qr_codes = list(
                    QRCode.objects.get_deleted()
                    .select_for_update()
                    .select_related("project__owner", "created_by")
                    .filter(id__in=qr_ids)
                )

                owner_counts = {}
                for qr_code in locked_qr_codes:
                    owner = account_owner_for_qr(qr_code)
                    owner_entry = owner_counts.setdefault(
                        owner.pk,
                        {"owner": owner, "count": 0},
                    )
                    owner_entry["count"] += 1

                for owner_id in sorted(owner_counts, key=str):
                    owner_entry = owner_counts[owner_id]
                    owner = lock_account_owner(owner_entry["owner"])
                    check_qr_capacity(owner, requested=owner_entry["count"])

                for qr_code in locked_qr_codes:
                    qr_code.restore()
        except QRLimitExceeded as exc:
            return _build_limit_response(str(exc), exc.limit, exc.used, exc.requested)

        restored_count = len(locked_qr_codes)

        return Response(
            {
                "data": {
                    "restored_count": restored_count,
                    "ids": sorted(found_ids),
                },
                "message": "QR codes restored successfully.",
            },
            status=status.HTTP_200_OK,
        )


class TemplateViewSet(viewsets.ModelViewSet):
    queryset = TemplateDesign.objects.all()
    serializer_class = TemplateDesignSerializer
    permission_classes = [IsAuthenticated]
    schema = ProjectSchema()
    authentication_classes = [JWTAuthentication]
    filter_backends = [SearchFilter]
    search_fields = ["created_by__email"]

    def get_queryset(self):
        qr_content_type = ContentType.objects.get_for_model(QRCode)
        project_content_type = ContentType.objects.get_for_model(Project)
        shared_qr_ids = SharePermissions.objects.filter(
            user_id=self.request.user,
            content_type=qr_content_type,
            is_deleted=False,
            role__category__name__iexact="sharing_permission",
            role__name__in=("Admin", "Edit", "View"),
            role__status=True,
        ).values_list("resource_id", flat=True)
        shared_project_ids = SharePermissions.objects.filter(
            user_id=self.request.user,
            content_type=project_content_type,
            is_deleted=False,
            role__category__name__iexact="sharing_permission",
            role__name__in=("Admin", "Edit", "View"),
            role__status=True,
        ).values_list("resource_id", flat=True)

        return super().get_queryset().filter(
            Q(is_public=True)
            | Q(created_by=self.request.user)
            | Q(qr_code__created_by=self.request.user)
            | Q(qr_code__project__owner=self.request.user)
            | Q(qr_code_id__in=shared_qr_ids)
            | Q(qr_code__project_id__in=shared_project_ids)
        ).distinct()

    def _check_template_permission(self, request, template, required):
        if template.qr_code_id:
            allowed = role_allows(qr_role(request.user, template.qr_code), required)
        else:
            allowed = template.created_by_id == request.user.id
        if not allowed:
            action = "delete" if required == "admin" else "edit"
            raise PermissionDenied(f"You cannot {action} this template.")

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
        print(request.data)

        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            {"data": serializer.data, "message": "Template created successfully."},
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        self._check_template_permission(request, instance, "edit")
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
        self._check_template_permission(request, instance, "admin")
        self.perform_destroy(instance)
        return Response(
            {"data": {}, "message": "Template deleted successfully."},
            status=status.HTTP_200_OK,
        )


class VideoViewSet(viewsets.ViewSet):
    schema = ProjectSchema()
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    @transaction.atomic
    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request):
        serializer = VideoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        qr = QRCode.objects.filter(pk=data["qr_code"]).first()
        if qr is None:
            raise NotFound("QR code not found.")
        if not role_allows(qr_role(request.user, qr), "edit"):
            raise PermissionDenied("You cannot edit this QR code.")

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
                status=404,
            )

        if not role_allows(qr_role(request.user, media_item.qr_media.qr_code), "admin"):
            raise PermissionDenied("You cannot delete this QR video.")

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
                status=404,
            )

        if not role_allows(qr_role(request.user, media_item.qr_media.qr_code), "edit"):
            raise PermissionDenied("You cannot edit this QR video.")

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



from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


class ProjectInvitationViewSet(viewsets.GenericViewSet):
    schema = InvitationSchema()
    permission_classes = [AllowAny]
    serializer_class = ProjectInvitationSerializer
    queryset = Project.objects.all()

    @action(detail=False, methods=["POST"], url_path="invitations", permission_classes=[IsAuthenticated])
    def invitations(self, request, *args, **kwargs):
        
        serializer = ProjectInvitationSerializer(
            data=request.data,
            context={
                "request": request,
            },
        )
        serializer.is_valid(raise_exception=True)

        invitations = serializer.save(
            invited_by=request.user,
        )
        if not isinstance(invitations, list):
            invitations = [invitations]

        for invitation in invitations:
            send_project_invitation_email(invitation)

        return Response(
            {
                "data": [
                    {
                        "id": invitation.id,
                        "email": invitation.email,
                        "project_id": invitation.resource_id,
                        "role": invitation.role.name,
                        "status": invitation.status.name,
                    }
                    for invitation in invitations
                ],
                "message": "Project invitation sent successfully.",
            },
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=False,
        methods=["get"],
        url_path="my-invitations",
        permission_classes=[IsAuthenticated],
    )
    def my_invitations(self, request, *args, **kwargs):
        invitations = (
            Invitations.objects.select_related(
                "invited_by",
                "role",
                "status",
                "content_type",
            )
            .filter(
                email__iexact=request.user.email,
                is_deleted=False,
            )
            .order_by("-created_at")
        )

        status_id = request.query_params.get("status")
        if status_id:
            invitations = invitations.filter(status_id=status_id)

        paginator = CustomPagination()
        page = paginator.paginate_queryset(invitations, request, view=self)
        serializer = ProjectInvitationDetailSerializer(page, many=True)
        response = paginator.get_paginated_response(serializer.data)
        response.data["message"] = "User invitations fetched successfully."
        return response

    @action(
        detail=False,
        methods=["get"],
        url_path="sent-invitations",
        permission_classes=[IsAuthenticated],
    )
    def sent_invitations(self, request, *args, **kwargs):
        project_content_type = ContentType.objects.get_for_model(Project)
        manageable_project_ids = Project.objects.filter(owner=request.user).values_list("id", flat=True)
        admin_project_ids = SharePermissions.objects.filter(
            user_id=request.user,
            content_type=project_content_type,
            is_deleted=False,
            role__category__name__iexact="sharing_permission",
            role__name="Admin",
            role__status=True,
        ).values_list("resource_id", flat=True)
        invitations = (
            Invitations.objects.select_related(
                "invited_by",
                "role",
                "status",
                "content_type",
            )
            .filter(
                is_deleted=False,
            )
            .filter(
                Q(invited_by=request.user)
                | Q(content_type=project_content_type, resource_id__in=manageable_project_ids)
                | Q(content_type=project_content_type, resource_id__in=admin_project_ids)
            )
            .order_by("-created_at")
        )

        status_name = request.query_params.get("status")
        if status_name:
            invitations = invitations.filter(status__name__iexact=status_name)

        grouped = []
        group_index = {}

        for invitation in invitations:
            receiver = User.objects.filter(
                email__iexact=invitation.email,
                is_deleted=False,
            ).first()

            # Accepted invitations represent active memberships in this
            # endpoint. Once the owner removes the member, hide the stale
            # accepted invitation from the sender list.
            if invitation.accepted_at and (
                receiver is None
                or not SharePermissions.objects.filter(
                    user_id=receiver,
                    content_type=project_content_type,
                    resource_id=invitation.resource_id,
                    is_deleted=False,
                ).exists()
            ):
                continue

            key = (invitation.email.lower(), str(invitation.role_id))
            if key not in group_index:
                group_index[key] = len(grouped)
                grouped.append(
                    {
                        "email": invitation.email,
                        "user_id": str(receiver.id) if receiver else None,
                        "receiver_name": receiver.get_full_name() if receiver else None,
                        "role_name": invitation.role.name,
                        "project_count": 0,
                        "projects": [],
                        "status": invitation.status.name if invitation.status else None,
                        "status_details": [],
                    }
                )

            current = grouped[group_index[key]]
            current["project_count"] += 1
            current["projects"].append(
                {
                    "project_id": str(invitation.resource_id),
                    "project_name": invitation.content_object.name,
                    "token": invitation.token,
                    "status": invitation.status.name if invitation.status else None,
                }
            )
            current["status_details"].append(
                {
                    "status": invitation.status.name if invitation.status else None,
                    "created_at": invitation.created_at,
                    "expires_at": invitation.expires_at,
                }
            )

        paginator = CustomPagination()
        page = paginator.paginate_queryset(grouped, request, view=self)
        response = paginator.get_paginated_response(page)
        response.data["message"] = "Sender invitations fetched successfully."
        return response

    @action(
        detail=False,
        methods=["get"],
        url_path=r"details/(?P<token>[^/.]+)",
    )
    def invitation_detail(self, request, token):
        try:
            invitation = Invitations.objects.select_related(
                "invited_by",
                "role",
                "status",
            ).get(
                token=token,
                is_deleted=False,
            )
        except Invitations.DoesNotExist:
            return Response(
                {
                    "data": {},
                    "message": "Invitation not found.",
                },
                status=400,
            )

        if invitation.expires_at < timezone.now():
            return Response(
                {
                    "data": {},
                    "message": "This invitation has expired.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ProjectInvitationDetailSerializer(
            invitation
        )

        return Response(
            {
                "data": serializer.data,
                "message": "Invitation fetched successfully.",
            },
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path=r"(?P<token>[^/.]+)/accept",
        permission_classes=[IsAuthenticated],
    )
    def accept(self, request, token):
        with transaction.atomic():
            try:
                invitation = (
                    Invitations.objects
                    .select_for_update()
                    .select_related(
                        "invited_by",
                        "role",
                        "role__category",
                        "status",
                    )
                    .get(
                        token=token,
                        is_deleted=False,
                    )
                )
            except Invitations.DoesNotExist:
                return Response(
                    {
                        "data": {},
                        "message": "Invitation not found.",
                    },
                    status=400,
                )

            # Check expiry
            if invitation.expires_at < timezone.now():
                return Response(
                    {
                        "data": {},
                        "message": "This invitation has expired.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check whether already accepted
            if invitation.accepted_at:
                return Response(
                    {
                        "data": {},
                        "message": "This invitation has already been accepted.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Make sure the invitation belongs to this user's email
            if invitation.email.lower() != request.user.email.lower():
                return Response(
                    {
                        "data": {},
                        "message": (
                            "This invitation was sent to a different "
                            "email address."
                        ),
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            if (
                not invitation.role.status
                or invitation.role.category.name.lower() != "sharing_permission"
                or invitation.role.name.strip().lower() not in ROLE_NAMES
            ):
                return Response(
                    {"data": {}, "message": "This invitation has an invalid project role."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            project = invitation.content_object

            try:
                project_owner = lock_account_owner(project.owner)
                check_team_member_capacity(project_owner, [request.user.email])
            except TeamMemberLimitExceeded as exc:
                return _build_limit_response(
                    str(exc),
                    exc.limit,
                    exc.used,
                    exc.requested,
                )

            content_type = ContentType.objects.get_for_model(
                Project
            )

            # Check existing permission
            existing_permission = SharePermissions.objects.filter(
                user_id=request.user,
                content_type=content_type,
                resource_id=project.id,
                is_deleted=False,
            ).first()

            if existing_permission:
                return Response(
                    {
                        "data": {},
                        "message": "You are already a member of this project.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Create project permission
            permission = SharePermissions.objects.create(
                user_id=request.user,
                content_type=content_type,
                resource_id=project.id,
                role=invitation.role,
            )

            # Mark invitation as accepted
            invitation.accepted_by = request.user
            invitation.accepted_at = timezone.now()

            # Set accepted status here
            accepted_status = ConfigChoice.objects.get(id="12f2f830-ee34-4eba-a067-90ee0d50bccd")
            invitation.status = accepted_status

            invitation.save(
                update_fields=[
                    "accepted_by",
                    "accepted_at",
                    "status",
                ]
            )

        return Response(
            {
                "data": {
                    "project_id": str(project.id),
                    "permission_id": str(permission.id),
                    "role": invitation.role.name,
                },
                "message": "Project invitation accepted successfully.",
            },
            status=status.HTTP_200_OK,
        )


    @action(
        detail=False,
        methods=["post"],
        url_path=r"(?P<token>[^/.]+)/reject",
        permission_classes=[IsAuthenticated],
    )
    def reject(self, request, token):
        with transaction.atomic():
            try:
                invitation = (
                    Invitations.objects
                    .select_for_update()
                    .select_related(
                        "invited_by",
                        "role",
                        "status",
                    )
                    .get(
                        token=token,
                        is_deleted=False,
                    )
                )
            except Invitations.DoesNotExist:
                return Response(
                    {
                        "data": {},
                        "message": "Invitation not found.",
                    },
                    status=400,
                )

            if invitation.expires_at < timezone.now():
                return Response(
                    {
                        "data": {},
                        "message": "This invitation has expired.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if invitation.accepted_at:
                return Response(
                    {
                        "data": {},
                        "message": "This invitation has already been accepted.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if invitation.rejected_at:
                return Response(
                    {
                        "data": {},
                        "message": "This invitation has already been rejected.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if invitation.email.lower() != request.user.email.lower():
                return Response(
                    {
                        "data": {},
                        "message": (
                            "This invitation was sent to a different "
                            "email address."
                        ),
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            invitation.rejected_by = request.user
            invitation.rejected_at = timezone.now()

            # Set your REJECTED ConfigChoice here
            rejected_status = ConfigChoice.objects.get(id="60cfb5b8-93b8-40c5-94e5-1d963d186698")
            invitation.status = rejected_status

            invitation.save(
                update_fields=[
                    "rejected_by",
                    "rejected_at",
                    "status",
                ]
            )

        return Response(
            {
                "data": {},
                "message": "Project invitation rejected successfully.",
            },
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path=r"(?P<token>[^/.]+)/cancel",
        permission_classes=[IsAuthenticated],
    )
    def cancel(self, request, token):
        try:
            invitation = Invitations.objects.select_related(
                "role",
                "status",
            ).get(
                token=token,
                is_deleted=False,
            )
        except Invitations.DoesNotExist:
            return Response(
                {
                    "data": {},
                    "message": "Invitation not found.",
                },
                status=400,
            )

        if not role_allows(project_role(request.user, invitation.content_object), "admin"):
            return Response(
                {
                    "data": {},
                    "message": "You do not have permission to cancel this invitation.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if invitation.accepted_at:
            return Response(
                {
                    "data": {},
                    "message": "Accepted invitations cannot be cancelled.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if invitation.rejected_at:
            return Response(
                {
                    "data": {},
                    "message": "Rejected invitations cannot be cancelled.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if invitation.expires_at < timezone.now():
            return Response(
                {
                    "data": {},
                    "message": "Expired invitations cannot be cancelled.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Set your CANCELLED ConfigChoice here
        cancelled_status = ConfigChoice.objects.get(id="3d18d940-42e2-4f54-9801-8b05a06d0c3a")
        invitation.status = cancelled_status

        invitation.save(
            update_fields=[
                "status",
            ]
        )

        return Response(
            {
                "data": {},
                "message": "Project invitation cancelled successfully.",
            },
            status=status.HTTP_200_OK,
        )

    import secrets
    from datetime import timedelta

    @action(
        detail=False,
        methods=["post"],
        url_path=r"(?P<token>[^/.]+)/resend",
        permission_classes=[IsAuthenticated],
    )
    def resend(self, request, token):
        try:
            invitation = Invitations.objects.select_related(
                "invited_by",
                "role",
            ).get(
                token=token,
                is_deleted=False,
            )
        except Invitations.DoesNotExist:
            return Response(
                {
                    "data": {},
                    "message": "Invitation not found.",
                },
                status=400,
            )

        if not role_allows(project_role(request.user, invitation.content_object), "admin"):
            return Response(
                {
                    "data": {},
                    "message": "You do not have permission to resend this invitation.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if invitation.accepted_at:
            return Response(
                {
                    "data": {},
                    "message": "Accepted invitations cannot be resent.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if invitation.rejected_at:
            return Response(
                {
                    "data": {},
                    "message": "Rejected invitations cannot be resent.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate a new token
        invitation.token = secrets.token_urlsafe(48)

        # Extend expiry
        invitation.expires_at = timezone.now() + timedelta(days=7)

        invitation.save(
            update_fields=[
                "token",
                "expires_at",
            ]
        )

        # Send email again
        send_project_invitation_email(invitation)

        return Response(
            {
                "data": {
                    "email": invitation.email,
                    "expires_at": invitation.expires_at,
                },
                "message": "Project invitation resent successfully.",
            },
            status=status.HTTP_200_OK,
        )






class QRCodeBulkImportViewSet(viewsets.GenericViewSet):
    serializer_class = QRImportJobUploadSerializer
    parser_classes = [MultiPartParser, FormParser]
    schema = ProjectSchema()

    def create(self, request, *args, **kwargs):
        serializer = QRImportJobUploadSerializer(
            data=request.data,
            context={"request": request},
        )


        serializer.is_valid(raise_exception=True)

        qr_type = serializer.validated_data["qr_type"]
        project = serializer.validated_data["project"]
        design_data = serializer.validated_data["design_data"]
        file = serializer.validated_data["file"]

        account_owner = account_owner_for_project(project, request.user)
        bulk_upload_limit = get_bulk_upload_limit(account_owner)
        temp_import_job = QRImportJob(
            user=request.user,
            project=project,
            qr_type=qr_type,
            file=file,
            design_data=design_data,
        )

        try:
            headers, data_rows = load_import_workbook_rows(
                temp_import_job,
                max_rows=bulk_upload_limit,
            )
        except ValueError as exc:
            return Response(
                {
                    "data": {"error": str(exc)},
                    "message": "Import failed.",
                    "status": "error",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        finally:
            if hasattr(file, "seek"):
                file.seek(0)

        limit_response = _enforce_qr_limit(account_owner, requested=len(data_rows))
        if limit_response is not None:
            return limit_response

        # Get PENDING status from ConfigChoice

        pending_status = ConfigChoice.objects.get(
            id="f1f4c191-dadd-43a3-8cba-b021485c418c",
        )

        import_job = QRImportJob.objects.create(
            user=request.user,
            project=project,
            qr_type=qr_type,
            status=pending_status,
            file=file,
            design_data=design_data,
        )

        try:
            # Queue background processing
            process_qr_import(str(import_job.id))
        except ValueError as exc:
            return Response(
                {
                    "data": {
                        "job_id": str(import_job.id),
                        "error": str(exc),
                    },
                    "message": "Import failed.",
                    "status": "error",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {
                    "data": {
                        "job_id": str(import_job.id),
                        "error": str(exc),
                    },
                    "message": "Import failed.",
                    "status": "error",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "data": {
                    "job_id": str(import_job.id),
                    "status": pending_status.name,
                },
                "message": "Import has been queued successfully.",
                "status": "success",
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(
        detail=True,
        methods=["GET"],
        url_path="status",
    )
    def import_status(self, request, pk=None):
        try:
            import_job = QRImportJob.objects.get(
                id=pk,
                user=request.user,
            )
        except QRImportJob.DoesNotExist:
            raise NotFound("Import job not found.")

        serializer = QRImportJobStatusSerializer(import_job)

        return Response(
            {
                "data": serializer.data,
                "message": "Import job status retrieved successfully.",
                "status": "success",
            },
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=["POST"],
        url_path="validate",
    )
    def validate_import(self, request, *args, **kwargs):
        serializer = QRImportJobUploadSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        qr_type = serializer.validated_data["qr_type"]
        project = serializer.validated_data["project"]
        design_data = serializer.validated_data["design_data"]
        file = serializer.validated_data["file"]

        account_owner = account_owner_for_project(project, request.user)
        bulk_upload_limit = get_bulk_upload_limit(account_owner)

        pending_status = ConfigChoice.objects.get(
            id="f1f4c191-dadd-43a3-8cba-b021485c418c",
        )

        import_job = QRImportJob(
            user=request.user,
            project=project,
            qr_type=qr_type,
            status=pending_status,
            file=file,
            design_data=design_data,
        )

        try:
            headers, data_rows = load_import_workbook_rows(
                import_job,
                max_rows=bulk_upload_limit,
            )
            limit_response = _enforce_qr_limit(account_owner, requested=len(data_rows))
            if limit_response is not None:
                return limit_response

            importer = get_importer(import_job.qr_type)
            importer.validate_headers(headers)
        except Exception as exc:
            return Response(
                {
                    "data": {
                        "rows": [],
                        "error": str(exc),
                    },
                    "message": "Import validation failed.",
                    "status": "error",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = []
        from django.db import transaction

        for index, row_values in enumerate(data_rows, start=2):
            row = dict(zip(headers, row_values))
            qrname = row.get("QrName") or row.get("qrname") or ""
            try:
                with transaction.atomic():
                    sid = transaction.savepoint()
                    try:
                        importer.process_row(
                            row=row,
                            job=import_job,
                            row_number=index,
                        )
                        transaction.savepoint_rollback(sid)
                    except Exception:
                        transaction.savepoint_rollback(sid)
                        raise
                results.append(
                    {
                        "row": index,
                        "qrname": qrname,
                        "status": "valid",
                        "error": None,
                    }
                )
            except Exception as exc:
                error_message = str(exc)
                error_list = [
                    part.strip()
                    for part in error_message.split(" | ")
                    if part.strip()
                ]
                results.append(
                    {
                        "row": index,
                        "qrname": qrname,
                        "status": "invalid",
                        "error": error_list if len(error_list) > 1 else error_message,
                    }
                )

        return Response(
            {
                "data": {
                    "rows": results,
                },
                "message": "Import validation completed successfully.",
                "status": "success",
            },
            status=status.HTTP_200_OK,
        )


# views.py - Updated CustomDomainViewSet

class CustomDomainViewSet(viewsets.ModelViewSet):
    schema = CustomDomainSchema()
    serializer_class = CustomDomainSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = CustomDomain.objects.filter(
            user=self.request.user,
            is_deleted=False
        )
        status_param = self.request.query_params.get("status")
        if status_param:
            valid_statuses = {choice[0] for choice in CustomDomain.Status.choices}
            normalized_status = status_param.strip().lower()
            if normalized_status not in valid_statuses:
                raise ValidationError(
                    {
                        "status": (
                            "Invalid status. Use one of: "
                            + ", ".join(sorted(valid_statuses))
                        )
                    }
                )
            queryset = queryset.filter(status=normalized_status)
        return queryset

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Create a new custom domain and start verification"""
        limit_response = _enforce_domain_add_limit(request.user)
        if limit_response is not None:
            return limit_response

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        domain = serializer.save(user=request.user)

        # Start verification process synchronously
        try:
            verification_service = DomainVerificationService()
            result = verification_service.verify_and_activate_domain(domain)

            if result.get('success'):
                return Response({
                    'data': {
                        'domain': serializer.data,
                        'status': domain.status,
                        'verification': result,
                    },
                    'message': 'Domain added, verified, and activated successfully!',
                }, status=status.HTTP_201_CREATED)

            return Response({
                'data': {
                    'domain': serializer.data,
                    'status': domain.status,
                    'verification': result,
                },
                'message': result.get('message', 'Domain added but verification failed.'),
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            # logger.error(f"Failed to start domain verification: {str(e)}")
            return Response({
                'data': {
                    'domain': serializer.data,
                    'warning': str(e)
                },
                'message': 'Domain added but verification must be started manually.',
            }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """Verify a domain and activate it"""
        domain = self.get_object()

        if domain.status == CustomDomain.Status.ACTIVE:
            return Response({
                'data': {},
                'message': 'Domain is already active'
            }, status=status.HTTP_400_BAD_REQUEST)

        verification_service = DomainVerificationService()
        result = verification_service.verify_and_activate_domain(domain)

        if result['success']:
            return Response({
                'data': result,
                'message': result.get('message', 'Domain verified successfully')
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'data': result,
                'message': result.get('message', 'Verification failed')
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a verified domain"""
        domain = self.get_object()

        if domain.status not in [
            CustomDomain.Status.VERIFIED,
            CustomDomain.Status.SSL_PENDING,
            CustomDomain.Status.FAILED,
        ]:
            return Response({
                'data': {},
                'message': f'Domain cannot be activated. Current status: {domain.status}'
            }, status=status.HTTP_400_BAD_REQUEST)

        verification_service = DomainVerificationService()
        result = verification_service.verify_and_activate_domain(domain)

        return Response({
            'data': result,
            'message': result.get('message', 'Domain activated successfully')
        })

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate an active domain"""
        domain = self.get_object()

        if domain.status != CustomDomain.Status.ACTIVE:
            return Response({
                'data': {},
                'message': 'Only active domains can be deactivated'
            }, status=status.HTTP_400_BAD_REQUEST)

        verification_service = DomainVerificationService()
        result = verification_service.deactivate_domain(domain)

        return Response({
            'data': result,
            'message': result.get('message', 'Domain deactivated successfully')
        })

    @action(detail=True, methods=['post'])
    def make_default(self, request, pk=None):
        domain = self.get_object()
        CustomDomain.objects.filter(user=self.request.user).update(is_default=False)
        domain.is_default = True
        domain.save()

        return Response({'data': {},
                'message': 'Default domain was made successfully.',
            }, status=200)


    @action(detail=False, methods=['get'])
    def status(self, request):
        """Get detailed status of a domain"""
        domain = request.query_params.get('domain')

        if not domain:
            return Response({
                'data': {},
                'message': 'Domain parameter required'
            }, status=status.HTTP_400_BAD_REQUEST)

        verification_service = DomainVerificationService()
        result = verification_service.get_domain_status(domain)

        return Response({
            'data': result,
            'message': result.get('message', 'Domain status fetched successfully')
        })

    @action(detail=False, methods=['post'])
    def auto_verify(self, request):
        """Auto-verify pending domains (admin only)"""
        if not request.user.is_staff:
            return Response({
                'data': {},
                'message': 'Only administrators can perform this action'
            }, status=status.HTTP_403_FORBIDDEN)

        verification_service = DomainVerificationService()
        result = verification_service.auto_verify_pending_domains()

        return Response({
            'data': result,
            'message': result.get('message', 'Pending domains processed successfully')
        })

    @action(detail=False, methods=['get'], url_path='verify/(?P<token>[^/.]+)')
    def verify_by_token(self, request, token=None):
        """Verify domain using token from URL"""
        if not token:
            return Response({
                'data': {},
                'message': 'Verification token is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            domain = CustomDomain.objects.get(
                verification_token=token,
                is_deleted=False
            )
        except CustomDomain.DoesNotExist:
            return Response({
                'data': {},
                'message': 'Invalid verification token'
            }, status=400)

        # If domain is already active
        if domain.status == CustomDomain.Status.ACTIVE:
            return Response({
                'data': {
                    'domain': domain.domain,
                    'status': domain.status,
                    'activated_at': domain.activated_at
                },
                'message': 'Domain is already verified and active!',
            })

        # Start verification process
        verification_service = DomainVerificationService()
        result = verification_service.verify_and_activate_domain(domain)

        if result['success']:
            return Response({
                'data': {
                    'domain': domain.domain,
                    'status': domain.status,
                    'ssl_verified': domain.ssl_verified,
                    'ssl_issuer': domain.ssl_issuer,
                    'ssl_expires_at': domain.ssl_expires_at
                },
                'message': 'Domain verified and activated successfully!',
            })
        else:
            return Response({
                'data': {
                    'domain': domain.domain,
                    'status': domain.status,
                    'error': result.get('error'),
                    'fix_instructions': [
                        '1. Check your DNS CNAME record:',
                        f'   - Type: CNAME',
                        f'   - Host: {domain.domain}',
                        f'   - Value: {settings.CUSTOM_DOMAIN_CNAME_TARGET}',
                        '2. Wait for DNS propagation (up to 24 hours)',
                        '3. Try again after propagation',
                        '4. If using Cloudflare, ensure proxy is disabled (grey cloud)'
                    ]
                },
                'message': result.get('message', 'Verification failed'),
            }, status=status.HTTP_400_BAD_REQUEST)


    @action(detail=True, methods=['post'])
    def retry_ssl(self, request, pk=None):
        """Retry SSL provisioning for a domain"""
        domain = self.get_object()

        if domain.status not in [
            CustomDomain.Status.SSL_PENDING,
            CustomDomain.Status.VERIFIED,
            CustomDomain.Status.FAILED,
        ]:
            return Response({
                'data': {},
                'message': f'SSL provisioning cannot be retried. Current status: {domain.status}'
            }, status=status.HTTP_400_BAD_REQUEST)

        verification_service = DomainVerificationService()
        result = verification_service.verify_and_activate_domain(domain)
        if result.get('success'):
            return Response({
                'data': result,
                'message': result.get('message', 'SSL provisioning successful'),
            })

        domain.automation_error = result.get('error', 'SSL provisioning failed')
        domain.save(update_fields=['automation_error', 'updated_at'])
        return Response({
            'data': result,
            'message': result.get('error', 'SSL provisioning failed'),
        }, status=status.HTTP_400_BAD_REQUEST)

    def perform_destroy(self, instance):
        """Delete domain and remove the infrastructure created for it."""
        verification_service = DomainVerificationService()
        cleanup_result = verification_service.cleanup_domain_assets(instance)

        if not cleanup_result.get('success'):
            errors = cleanup_result.get('errors') or ['Domain cleanup failed']
            instance.automation_error = '; '.join(errors)
            instance.save(update_fields=['automation_error', 'updated_at'])
            raise ValidationError(
                {
                    'domain': (
                        'Domain was not deleted because cleanup failed: '
                        + '; '.join(errors)
                    )
                }
            )

        instance.hard_delete()
