from django.db.models import Q
from django.db.models import Count
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser

from Qr.models import CustomDomain
from Qr.serializers import AdminCustomDomainSerializer
from accounts.views import AdminAutoSchema
from Qr.services.domain_verification import DomainVerificationService


class CustomDomainViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AdminCustomDomainSerializer
    permission_classes = [IsAdminUser]
    schema = AdminAutoSchema()
    queryset = CustomDomain.objects.select_related("user").filter(
        is_deleted=False
    ).order_by("-created_at")

    @action(detail=False, methods=["get"], url_path="statistics")
    def statistics(self, request):
        queryset = self.get_queryset()
        counts = {
            row["status"]: row["count"]
            for row in queryset.values("status").annotate(count=Count("id"))
        }
        status_counts = {
            status_value: counts.get(status_value, 0)
            for status_value, _ in CustomDomain.Status.choices
        }
        total = queryset.count()
        active_count = status_counts[CustomDomain.Status.ACTIVE]
        failed_count = status_counts[CustomDomain.Status.FAILED]

        return Response(
            {
                "data": {
                    "total_domains": total,
                    "active_domains": active_count,
                    "failed_domains": failed_count,
                    "other_domains": total - active_count - failed_count,
                    "status_counts": status_counts,
                },
                "message": "Custom domain statistics fetched successfully.",
            },
            status=status.HTTP_200_OK,
        )

    def get_queryset(self):
        queryset = super().get_queryset()
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param.strip().lower())

        user_id = self.request.query_params.get("user_id")
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(domain__icontains=search)
                | Q(user__full_name__icontains=search)
                | Q(user__email__icontains=search)
            )

        is_default = self.request.query_params.get("is_default")
        if is_default in {"true", "false"}:
            queryset = queryset.filter(is_default=is_default == "true")

        ssl_verified = self.request.query_params.get("ssl_verified")
        if ssl_verified in {"true", "false"}:
            queryset = queryset.filter(ssl_verified=ssl_verified == "true")

        return queryset

    def retrieve(self, request, *args, **kwargs):
        domain = self.get_object()
        return Response(
            {
                "data": self.get_serializer(domain).data,
                "message": "Custom domain details fetched successfully.",
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="verify")
    def verify(self, request, pk=None):
        """Run the same DNS, Nginx, ACME and SSL activation flow as the user API."""
        domain = self.get_object()

        if domain.status == CustomDomain.Status.ACTIVE:
            return Response(
                {"data": {}, "message": "Domain is already active"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = DomainVerificationService().verify_and_activate_domain(domain)
        except Exception as exc:
            return Response(
                {
                    "data": {"domain": domain.domain, "status": domain.status},
                    "message": f"Domain verification failed: {exc}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_status = status.HTTP_200_OK if result.get("success") else status.HTTP_400_BAD_REQUEST
        return Response(
            {
                "data": {
                    "domain": self.get_serializer(domain).data,
                    "verification": result,
                },
                "message": result.get(
                    "message",
                    "Domain verified successfully" if result.get("success") else "Verification failed",
                ),
            },
            status=response_status,
        )
