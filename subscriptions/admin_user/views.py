from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from django.db.models import Count, Q
from django.db import transaction
from subscriptions.models import Duration, Package, PackagePlan, Invoice, SubscriptionChangeLog
from subscriptions.serializers import AdminDurationSerializer, AdminPackageSerializer, AdminInvoiceSerializer
from accounts.views import AdminAutoSchema, admin_query_parameter


class DurationViewSet(viewsets.ModelViewSet):
    queryset = Duration.objects.all().order_by("days", "name")
    serializer_class = AdminDurationSerializer
    permission_classes = [IsAdminUser]
    schema = AdminAutoSchema()


class PackageViewSet(viewsets.ModelViewSet):
    queryset = Package.objects.prefetch_related("packageplan_set", "packageplan_set__duration").all()
    serializer_class = AdminPackageSerializer
    permission_classes = [IsAdminUser]
    schema = AdminAutoSchema()

    def perform_create(self, serializer):
        with transaction.atomic():
            serializer.save()

    def perform_update(self, serializer):
        with transaction.atomic():
            serializer.save()

    def perform_destroy(self, instance):
        plan_ids = list(instance.packageplan_set.values_list("id", flat=True))
        if plan_ids:
            has_usage = (
                PackagePlan.objects.filter(id__in=plan_ids, subscriptions__isnull=False).exists()
                or PackagePlan.objects.filter(id__in=plan_ids, invoices__isnull=False).exists()
                or SubscriptionChangeLog.objects.filter(
                    Q(old_package_plan_id__in=plan_ids) | Q(new_package_plan_id__in=plan_ids)
                ).exists()
            )
            if has_usage:
                raise ValidationError({
                    "detail": "This package is already used and cannot be deleted."
                })

        with transaction.atomic():
            for plan in instance.packageplan_set.all():
                plan.delete()
            instance.delete()

class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Invoice.objects.select_related(
        "user", "package_plan", "package_plan__package", "package_plan__duration",
        "payment_method", "subscription",
    ).all().order_by("-created_at")
    serializer_class = AdminInvoiceSerializer
    permission_classes = [IsAdminUser]
    schema = AdminAutoSchema()
    swagger_query_parameters = {
        "list": [
            admin_query_parameter(
                "status",
                "Filter by exact invoice status.",
                enum=[value for value, _label in Invoice.Status.choices],
                example=Invoice.Status.PAID,
            ),
            admin_query_parameter(
                "user_id",
                "Filter invoices by user UUID.",
                value_format="uuid",
            ),
        ],
        "status_counts": [
            admin_query_parameter(
                "user_id",
                "Filter invoice counts by user UUID.",
                value_format="uuid",
            ),
        ],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        return queryset

    @action(detail=False, methods=["get"], url_path="status-counts")
    def status_counts(self, request):
        queryset = self.get_queryset()
        counts = queryset.values("status").annotate(count=Count("id"))
        counts_by_status = {status_value: 0 for status_value, _label in Invoice.Status.choices}
        counts_by_status.update({item["status"]: item["count"] for item in counts})
        return Response(
            {
                "data": counts_by_status,
                "message": "Invoice status counts fetched successfully.",
            },
            status=status.HTTP_200_OK,
        )
