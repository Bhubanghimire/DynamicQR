from django.db.models import Q, Prefetch
from django.db.models import Sum
from django.db.models.functions import Coalesce
from rest_framework.response import Response
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from DynamicOCR.schemas import PaginatedAutoSchema
from Qr.models import Project, QRCode
from DynamicOCR.pagination import CustomPagination
from subscriptions.models import Duration, Invoice, Package, PackagePlan, Subscription
from subscriptions.serializers import (
    InvoiceSerializer,
    DurationSerializer,
    PackageSerializer,
    SubscriptionUsageSerializer,
)


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


class PackageSchema(PaginatedAutoSchema):
    def get_tags(self, path, method):
        return ["Subscription"]

    def get_operation_id(self, path, method):
        return f"package_{self.view.action}"

    def get_filter_parameters(self, path, method):
        params = super().get_filter_parameters(path, method)
        if method.upper() == "GET":
            params.append(
                {
                    "name": "duration",
                    "required": False,
                    "in": "query",
                    "description": "Filter packages by duration UUID.",
                    "schema": {"type": "string", "format": "uuid"},
                }
            )
        return params


class DurationSchema(PaginatedAutoSchema):
    def get_tags(self, path, method):
        return ["Subscription"]

    def get_operation_id(self, path, method):
        return f"duration_{self.view.action}"


class DurationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    schema = DurationSchema()
    serializer_class = DurationSerializer
    permission_classes_by_action = {
        "list": [AllowAny],
    }
    pagination_class = CustomPagination

    def get_permissions(self):
        try:
            return [permission() for permission in self.permission_classes_by_action[self.action]]
        except KeyError:
            return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        return Duration.objects.all().order_by("days", "name")


class PackageViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    schema = PackageSchema()
    serializer_class = PackageSerializer
    permission_classes_by_action = {
        "list": [AllowAny],
    }
    pagination_class = CustomPagination

    def get_permissions(self):
        try:
            return [permission() for permission in self.permission_classes_by_action[self.action]]
        except KeyError:
            return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        duration = self.request.query_params.get("duration")
        plan_queryset = PackagePlan.objects.filter(is_active=True)
        if duration:
            plan_queryset = plan_queryset.filter(duration_id=duration)

        queryset = Package.objects.filter(is_active=True).prefetch_related(
            Prefetch(
                "packageplan_set",
                queryset=plan_queryset.select_related("duration").order_by(
                    "duration__days",
                    "duration__name",
                ),
            )
        ).order_by("display_order", "title")

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(description__icontains=search))

        if duration:
            queryset = queryset.filter(packageplan__is_active=True, packageplan__duration_id=duration).distinct()
        return queryset


class InvoiceSchema(PaginatedAutoSchema):
    def get_tags(self, path, method):
        return ["Subscription"]

    def get_operation_id(self, path, method):
        return f"invoice_{self.view.action}"


class InvoiceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    schema = InvoiceSchema()
    serializer_class = InvoiceSerializer
    permission_classes_by_action = {
        "list": [IsAuthenticated],
        "retrieve": [IsAuthenticated],
    }
    pagination_class = CustomPagination

    def get_permissions(self):
        try:
            return [permission() for permission in self.permission_classes_by_action[self.action]]
        except KeyError:
            return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        queryset = Invoice.objects.filter(
            user=self.request.user,
            status=Invoice.Status.PAID,
        ).select_related(
            "package_plan",
            "package_plan__package",
            "package_plan__duration",
            "payment_method",
            "subscription",
            "subscription__package_plan",
            "subscription__package_plan__package",
            "subscription__package_plan__duration",
        ).order_by("-paid_at", "-created_at")

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(invoice_number__icontains=search)
                | Q(package_plan__package__title__icontains=search)
                | Q(notes__icontains=search)
            )
        return queryset


class UsageSchema(PaginatedAutoSchema):
    def get_tags(self, path, method):
        return ["Subscription"]

    def get_operation_id(self, path, method):
        return f"usage_{self.view.action}"


class UsageViewSet(viewsets.GenericViewSet):
    schema = UsageSchema()
    serializer_class = SubscriptionUsageSerializer
    permission_classes_by_action = {
        "list": [IsAuthenticated],
    }

    def get_permissions(self):
        try:
            return [permission() for permission in self.permission_classes_by_action[self.action]]
        except KeyError:
            return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        return Subscription.objects.none()

    def list(self, request):
        subscription_qs = (
            Subscription.objects.filter(user=request.user)
            .select_related(
                "package_plan",
                "package_plan__package",
                "package_plan__duration",
            )
            .order_by("-status", "-expires_at", "-created_at")
        )
        subscription = subscription_qs.filter(status=Subscription.Status.ACTIVE).first() or subscription_qs.first()

        qr_queryset = QRCode.objects.filter(created_by=request.user)
        qr_generated_count = qr_queryset.count()

        scan_totals = qr_queryset.aggregate(
            total_scan_count=Coalesce(Sum("analytics__total_scans"), 0),
            unique_scan_count=Coalesce(Sum("analytics__unique_scans"), 0),
        )
        total_scan_count = scan_totals["total_scan_count"] or 0
        unique_scan_count = scan_totals["unique_scan_count"] or 0

        qr_limit = None
        scan_limit = None
        team_member_limit = None
        features = {}

        if subscription:
            qr_limit = subscription.qr_limit if subscription.qr_limit is not None else subscription.package_plan.max_qrs
            scan_limit = subscription.scan_limit if subscription.scan_limit is not None else subscription.package_plan.max_scans
            team_member_limit = subscription.team_member_limit
            features = subscription.features or {}

        def build_quota(used, limit):
            unlimited = limit is None
            remaining = None if unlimited else max(limit - used, 0)
            if unlimited:
                usage_percent = 0.0
            elif limit == 0:
                usage_percent = 100.0 if used else 0.0
            else:
                usage_percent = round(min((used / limit) * 100, 100), 2)
            return {
                "used": used,
                "limit": limit,
                "remaining": remaining,
                "unlimited": unlimited,
                "usage_percent": usage_percent,
            }

        payload = {
            "subscription": subscription,
            "subscription_status": subscription.status if subscription else "none",
            "qr_usage": build_quota(qr_generated_count, qr_limit),
            "scan_usage": build_quota(total_scan_count, scan_limit),
            "total_scan_count": total_scan_count,
            "unique_scan_count": unique_scan_count,
            "team_member_limit": team_member_limit,
            "features": features,
        }

        serializer = self.get_serializer(payload)
        return Response(serializer.data)
