"""Project and QR access granted by accepted invitations."""

from django.contrib.contenttypes.models import ContentType
from rest_framework.permissions import BasePermission, SAFE_METHODS

from Qr.models import Project, QRCode, SharePermissions


ROLE_NAMES = {"admin", "edit", "view"}
WRITE_ROLES = {"admin", "edit"}
ADMIN_ROLES = {"admin"}
ROLE_PRIORITY = {"view": 1, "edit": 2, "admin": 3, "owner": 4}


def _shared_role(user, model, resource_id):
    if not user or not user.is_authenticated:
        return None
    roles = SharePermissions.objects.filter(
        user_id=user,
        content_type=ContentType.objects.get_for_model(model),
        resource_id=resource_id,
        is_deleted=False,
        role__category__name__iexact="sharing_permission",
        role__status=True,
    ).values_list("role__name", flat=True)
    valid_roles = (role.strip().lower() for role in roles if role and role.strip().lower() in ROLE_NAMES)
    return max(valid_roles, key=lambda role: ROLE_PRIORITY[role], default=None)


def project_role(user, project):
    if project is None or not user or not user.is_authenticated:
        return None
    if project.owner_id == user.id:
        return "owner"
    return _shared_role(user, Project, project.id)


def qr_role(user, qr):
    if qr is None or not user or not user.is_authenticated:
        return None
    if not qr.project_id and qr.created_by_id == user.id:
        return "owner"
    direct_role = _shared_role(user, QRCode, qr.id)
    inherited_role = project_role(user, qr.project) if qr.project_id else None
    return max((direct_role, inherited_role), key=lambda role: ROLE_PRIORITY.get(role, 0))


def role_allows(role, required):
    allowed = {
        "view": ROLE_NAMES | {"owner"},
        "edit": WRITE_ROLES | {"owner"},
        "admin": ADMIN_ROLES | {"owner"},
    }
    return role in allowed[required]


class ProjectRolePermission(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            required = "view"
        elif view.action == "destroy":
            required = "admin"
        else:
            required = "edit"
        return role_allows(project_role(request.user, obj), required)


class QRRolePermission(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            required = "view"
        elif view.action == "destroy":
            required = "admin"
        else:
            required = "edit"
        return role_allows(qr_role(request.user, obj), required)
