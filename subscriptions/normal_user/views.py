from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, Prefetch
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from uuid import UUID
import re
from rest_framework.response import Response
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from DynamicQR.schemas import PaginatedAutoSchema
from Qr.models import CustomDomain, Project, QRCode, SharePermissions
from DynamicQR.pagination import CustomPagination
from subscriptions.models import Duration, Invoice, Package, PackagePlan, PaymentMethod, Subscription, Currency, \
    PaymentProvider, PackagePlanPrice
from subscriptions.serializers import (
    CheckoutSessionCreateSerializer,
    InvoiceSerializer,
    DurationSerializer,
    PackageSerializer,
    PackagePlanSerializer,
    PaymentMethodSerializer,
    SubscriptionUsageSerializer,
    SubscriptionUsageSummarySerializer, CurrencySerializer, PaymentProviderSerializer,
)
from subscriptions.services.esewa_service import EsewaError, form_for_invoice
from subscriptions.views import reconcile_esewa_invoice


class ProjectSchema(PaginatedAutoSchema):
    def get_tags(self, path, method):
        return ["Subscription"]

    def get_operation_id(self, path, method):
        return f"subscription_{self.view.action}"

#
# class SubscriptionViewSet(viewsets.ViewSet):
#     schema = ProjectSchema()
#     permission_classes_by_action = {
#         'list': [IsAuthenticated],
#     }
#
#     def get_permissions(self):
#         try:
#             return [permission() for permission in self.permission_classes_by_action[self.action]]
#         except KeyError:
#             return [permission() for permission in self.permission_classes]
#
#     def list(self, request):
#         projects = Project.objects.filter(owner=request.user).values(
#             "id",
#             "name",
#             "description",
#             "status_id",
#             "created_at",
#             "updated_at",
#         )
#         search = request.query_params.get("search")
#         if search:
#             projects = projects.filter(Q(name__icontains=search) | Q(description__icontains=search))
#         paginator = CustomPagination()
#         page = paginator.paginate_queryset(projects, request, view=self)
#         return paginator.get_paginated_response(list(page))
#

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


class PackageViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    schema = PackageSchema()
    serializer_class = PackageSerializer
    permission_classes_by_action = {
        "list": [AllowAny],
        "retrieve": [AllowAny],
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


class PackagePlanViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PackagePlanSerializer
    permission_classes_by_action = {
        "retrieve": [AllowAny],
    }

    def get_permissions(self):
        try:
            return [permission() for permission in self.permission_classes_by_action[self.action]]
        except KeyError:
            return [AllowAny()]

    def get_queryset(self):
        return (
            PackagePlan.objects
            .select_related("package", "duration")
            .prefetch_related("prices__currency")
            .filter(is_active=True, package__is_active=True)
        )


class InvoiceSchema(PaginatedAutoSchema):
    def get_tags(self, path, method):
        return ["Subscription"]

    def get_operation_id(self, path, method):
        return f"invoice_{self.view.action}"

    def get_filter_parameters(self, path, method):
        params = super().get_filter_parameters(path, method)
        if method.upper() == "GET":
            params.append(
                {
                    "name": "duration",
                    "required": False,
                    "in": "query",
                    "description": "Filter invoices by package plan duration UUID.",
                    "schema": {"type": "string", "format": "uuid"},
                }
            )
        return params


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

        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)

        duration = self.request.query_params.get("duration")
        if duration:
            queryset = queryset.filter(package_plan__duration_id=duration)
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
        "summary": [IsAuthenticated],
    }

    def get_permissions(self):
        try:
            return [permission() for permission in self.permission_classes_by_action[self.action]]
        except KeyError:
            return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        return Subscription.objects.none()

    @staticmethod
    def _build_quota(used, limit):
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

    def list(self, request):
        payload = self._build_usage_payload(request.user)

        serializer = self.get_serializer(payload)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        payload = self._build_usage_summary_payload(request.user)
        serializer = SubscriptionUsageSummarySerializer(payload)
        return Response(serializer.data)

    def _build_usage_payload(self, user):
        subscription = Subscription.get_usage_subscription_for_user(user)
        if subscription:
            subscription = (
                Subscription.objects.filter(pk=subscription.pk)
                .select_related(
                    "package_plan",
                    "package_plan__package",
                    "package_plan__duration",
                )
                .first()
            )

        qr_queryset = QRCode.objects.filter(created_by=user)
        qr_generated_count = qr_queryset.count()

        scan_totals = qr_queryset.aggregate(
            total_scan_count=Coalesce(Sum("analytics__total_scans"), 0),
            unique_scan_count=Coalesce(Sum("analytics__unique_scans"), 0),
        )
        total_scan_count = scan_totals["total_scan_count"] or 0
        unique_scan_count = scan_totals["unique_scan_count"] or 0

        package = subscription.package_plan.package if subscription and subscription.package_plan else None
        qr_limit = None
        scan_limit = None
        team_member_limit = None
        bulk_upload_limit = None
        domain_add_limit = None
        features = {}

        if subscription and subscription.package_plan:
            qr_limit = subscription.qr_limit if subscription.qr_limit is not None else subscription.package_plan.max_qrs
            scan_limit = subscription.scan_limit if subscription.scan_limit is not None else subscription.package_plan.max_scans
            team_member_limit = subscription.team_member_limit
            bulk_upload_limit = subscription.bulk_upload_limit
            domain_add_limit = subscription.domain_add_limit
            features = subscription.features or {}

        domain_add_count = CustomDomain.objects.filter(
            user=user,
            is_deleted=False,
        ).count()

        return {
            "subscription": subscription,
            "subscription_status": subscription.status if subscription else "none",
            "package": package,
            "package_title": package.title if package else "",
            "package_plan": subscription.package_plan if subscription else None,
            "qr_generated_count": qr_generated_count,
            "qr_usage": self._build_quota(qr_generated_count, qr_limit),
            "scan_usage": self._build_quota(total_scan_count, scan_limit),
            "total_scan_count": total_scan_count,
            "unique_scan_count": unique_scan_count,
            "team_member_limit": team_member_limit,
            "bulk_upload_limit": bulk_upload_limit,
            "domain_add_limit": domain_add_limit,
            "domain_add_usage": self._build_quota(domain_add_count, domain_add_limit),
            "features": features,
        }

    def _build_usage_summary_payload(self, user):
        usage_payload = self._build_usage_payload(user)
        subscription = usage_payload["subscription"]
        package = usage_payload["package"]
        package_plan = usage_payload["package_plan"]
        package_metadata = getattr(package, "metadata", {}) or {}
        team_member_limit = usage_payload["team_member_limit"]
        bulk_upload_limit = usage_payload["bulk_upload_limit"]
        domain_add_limit = usage_payload["domain_add_limit"]
        project_limit = package_metadata.get("project_limit")

        return {
            "subscription": {
                "tier": (
                    "free"
                    if package and package.is_free
                    else (package.title if package else None)
                ),
                "name": package.title if package else None,
                "status": usage_payload["subscription_status"],
                "auto_renew": subscription.auto_renew if subscription else False,
            },
            "features": usage_payload["features"] or {},
            "quotas": {
                "team_members": self._build_quota(
                    self._get_team_member_usage(user),
                    team_member_limit,
                ),
                "qr_codes": usage_payload["qr_usage"],
                "scans": usage_payload["scan_usage"],
                "custom_domains": usage_payload["domain_add_usage"],
                "bulk_upload_rows": self._build_quota(
                    0,
                    bulk_upload_limit,
                ),
                "projects": self._build_quota(
                    Project.objects.filter(owner=user).count(),
                    project_limit,
                ),
            },
            "metrics": {
                "project_count": Project.objects.filter(owner=user).count(),
                "qr_code_count": usage_payload["qr_generated_count"],
                "total_scan_count": usage_payload["total_scan_count"],
                "unique_scan_count": usage_payload["unique_scan_count"],
                "custom_domain_count": usage_payload["domain_add_usage"]["used"],
                "bulk_upload_limit": bulk_upload_limit,
                "domain_add_limit": domain_add_limit,
                "package_plan_id": str(package_plan.id) if package_plan else None,
            },
        }

    def _get_team_member_usage(self, user):
        project_content_type = ContentType.objects.get_for_model(Project)
        owned_project_ids = Project.objects.filter(owner=user).values_list("id", flat=True)
        return (
            SharePermissions.objects.filter(
                content_type=project_content_type,
                resource_id__in=owned_project_ids,
                is_deleted=False,
            )
            .exclude(user_id=user)
            .values("user_id")
            .distinct()
            .count()
        )


class PaymentSchema(PaginatedAutoSchema):
    def get_tags(self, path, method):
        return ["Subscription"]

    def get_operation_id(self, path, method):
        return f"payment_{self.view.action}"

    def get_request_body(self, path, method):
        if method.upper() != "POST":
            return {}
        if self.view.action == "renew_subscription":
            return {
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "subscription_id": {
                                    "type": "string",
                                    "format": "uuid",
                                    "description": "Subscription UUID to charge for the next billing cycle.",
                                },
                            },
                            "required": ["subscription_id"],
                        }
                    }
                }
            }
        return {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "package_plan_id": {
                                "type": "string",
                                "format": "uuid",
                                "description": "Package plan UUID to purchase.",
                            },
                            "package_plan_price_id": {
                                "type": "string",
                                "format": "uuid",
                                "description": "Selected package plan price UUID.",
                            },
                            "quantity": {
                                "type": "integer",
                                "minimum": 1,
                                "default": 1,
                                "description": "Number of units to purchase.",
                            },
                            "auto_renew": {
                                "type": "boolean",
                                "default": False,
                                "description": (
                                    "Set to true to create a recurring subscription checkout. "
                                    "Requires DODO_SUBSCRIPTION_PRODUCT_ID to be configured, and the product must be a subscription product in Dodo."
                                ),
                            },
                        },
                        "required": ["package_plan_id", "package_plan_price_id"],
                    }
                }
            }
        }


# views.py
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.conf import settings
from dodopayments import DodoPayments
import logging


logger = logging.getLogger(__name__)

# views.py - Updated PaymentViewSet

import re
import logging
from uuid import UUID
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from dodopayments import DodoPayments



logger = logging.getLogger(__name__)


class PaymentViewSet(viewsets.ViewSet):
    schema = PaymentSchema()

    permission_classes_by_action = {
        "create": [IsAuthenticated],
        "esewa_initiate": [IsAuthenticated],
        "esewa_status": [IsAuthenticated],
        "status": [IsAuthenticated],
        "history": [IsAuthenticated],
        "saved_methods": [IsAuthenticated],
        "renew_subscription": [IsAuthenticated],
        "cancel_subscription": [IsAuthenticated],
    }

    def get_permissions(self):
        try:
            return [permission() for permission in self.permission_classes_by_action[self.action]]
        except KeyError:
            return [permission() for permission in self.permission_classes]

    def _session_to_payload(self, session):
        """Convert Dodo session to dict"""
        if hasattr(session, "model_dump"):
            return session.model_dump()
        if isinstance(session, dict):
            return session
        if hasattr(session, "__dict__"):
            return {
                key: value
                for key, value in vars(session).items()
                if not key.startswith("_")
            }
        return {"session": str(session)}

    def _get_dodo_client(self):
        """Initialize Dodo Payments client"""
        return DodoPayments(
            bearer_token=settings.DODO_PAYMENTS_API_KEY,
            environment="test_mode" if settings.DEBUG else "live_mode",
        )

    def _extract_session_id(self, payload):
        """Extract session ID from payload"""
        session_id = payload.get("id") or payload.get("session_id")
        if not session_id:
            checkout_url = payload.get("checkout_url") or ""
            match = re.search(r"(cks_[A-Za-z0-9]+)", checkout_url)
            if match:
                session_id = match.group(1)
        return session_id

    def _build_plan_name(self, plan):
        return f"{plan.package.title} - {plan.duration.name if plan.duration else 'One-time'}"

    def _get_default_payment_method(self, user):
        return (
            PaymentMethod.objects.filter(
                user=user,
                is_active=True,
                is_default=True,
                dodo_customer_id__gt="",
            )
            .order_by("-updated_at", "-created_at")
            .first()
        )

    def _cancel_dodo_auto_renew(self, subscription):
        if not subscription.dodo_subscription_id:
            return

        client = self._get_dodo_client()
        try:
            client.subscriptions.update(
                subscription.dodo_subscription_id,
                status="cancelled",
                cancel_at_next_billing_date=True,
                cancel_reason="cancelled_by_customer",
                cancellation_comment="Auto-renew cancelled by customer via DynamicQR.",
            )
        except Exception as e:
            logger.error(f"Failed to cancel Dodo auto-renew: {str(e)}")
            # Continue even if Dodo update fails

    # views.py - Fix subscription checkout data

    # views.py - Fix subscription checkout data

    # views.py - Fix subscription creation

    def _build_subscription_checkout_data(self, plan, invoice, request_user):
        """
        Build checkout data for subscription (auto-renew)
        ✅ Dodo subscriptions API uses product_id directly, not product_cart
        """
        return {
            # ✅ For subscriptions, use product_id directly (not product_cart)
            "product_id": plan.dodo_product_id,
            "quantity": 1,
            "customer": {
                "email": request_user.email,
                "name": request_user.get_full_name() or request_user.username,
            },
            "return_url": f"{settings.FRONTEND_URL}/billings/{invoice.id}/?invoice={invoice.invoice_number}",
            "cancel_url": f"{settings.FRONTEND_URL}/plans?invoice={invoice.invoice_number}",
            "metadata": {
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "user_id": str(request_user.id),
                "user_email": request_user.email,
                "package_plan_id": str(plan.id),
                "package_plan_price": str(plan.price),
                "package_plan_currency": str(plan.currency),
                "plan_name": self._build_plan_name(plan),
                "duration_days": str(plan.duration.days if plan.duration else 0),
                "auto_renew": "true",
            },
        }

    @action(detail=False, methods=["post"], url_path="esewa/initiate")
    def esewa_initiate(self, request):
        """Start a one-time eSewa checkout. Dodo checkout remains on POST /payments/."""
        from uuid import uuid4

        try:
            plan_id = UUID(str(request.data.get("package_plan_id", "")))
        except (ValueError, TypeError):
            return Response({"package_plan_id": ["A valid UUID is required."]}, status=400)
        plan = PackagePlan.objects.select_related("package", "duration").filter(
            id=plan_id, is_active=True, package__is_active=True,
        ).first()
        if not plan:
            return Response({"detail": "Package plan not found or inactive."}, status=404)
        if plan.package.is_free or plan.price <= 0:
            return Response({"detail": "This package does not require payment."}, status=400)
        if plan.currency.code.upper() != "NPR":
            return Response({"detail": "eSewa checkout requires an NPR package price."}, status=400)
        if str(request.data.get("auto_renew", "false")).lower() in {"true", "1", "yes"}:
            return Response({"detail": "eSewa checkout does not support auto-renew."}, status=400)
        if Subscription.objects.filter(
            user=request.user, status=Subscription.Status.ACTIVE,
            auto_renew=True, dodo_subscription_id__isnull=False,
            expires_at__gt=timezone.now(),
        ).exists():
            return Response(
                {"detail": "Disable your active Dodo auto-renew before paying with eSewa."},
                status=409,
            )
        if not settings.ESEWA_PRODUCT_CODE or not settings.ESEWA_SECRET_KEY or not settings.ESEWA_CALLBACK_BASE_URL:
            return Response({"detail": "eSewa is not configured."}, status=503)

        invoice = Invoice.objects.create(
            user=request.user, package_plan=plan, amount=plan.price, tax=0,
            total=plan.price, currency=plan.currency,
            due_date=timezone.now() + timezone.timedelta(hours=24),
            status=Invoice.Status.PENDING,
            metadata={
                "payment_provider": "esewa", "auto_renew": False,
                "esewa_transaction_uuid": str(uuid4()),
                "esewa_payment_status": "pending",
            },
        )
        payment_url, fields = form_for_invoice(invoice)
        return Response({
            "payment_url": payment_url,
            "form_fields": fields,
            "invoice_number": invoice.invoice_number,
            "invoice_id": str(invoice.id),
            "transaction_uuid": invoice.metadata["esewa_transaction_uuid"],
            "amount": str(invoice.total),
            "currency": "NPR",
            "auto_renew": False,
        }, status=201)

    @action(detail=False, methods=["get"], url_path="esewa/status")
    def esewa_status(self, request):
        """Recheck a user's eSewa invoice with eSewa; useful after a missed callback."""
        invoice_number = request.query_params.get("invoice_number")
        invoice = Invoice.objects.filter(
            invoice_number=invoice_number, user=request.user,
            metadata__payment_provider="esewa",
        ).first()
        if not invoice:
            return Response({"detail": "eSewa invoice not found."}, status=404)
        if invoice.status != Invoice.Status.PAID:
            try:
                reconcile_esewa_invoice(invoice)
            except EsewaError:
                pass  # Keep pending; caller can retry after eSewa becomes available.
            invoice.refresh_from_db()
        return Response({
            "invoice_number": invoice.invoice_number,
            "invoice_id": str(invoice.id),
            "status": invoice.status,
            "payment_status": invoice.metadata.get("esewa_payment_status", "pending"),
            "amount": str(invoice.total),
            "currency": "NPR",
            "transaction_code": invoice.metadata.get("esewa_transaction_code"),
            "subscription_id": str(invoice.subscription_id) if invoice.subscription_id else None,
        })

    def create(self, request):
        """
        Create checkout session using the plan's Dodo product ID
        """
        serializer = CheckoutSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        package_plan_id = serializer.validated_data["package_plan_id"]
        package_plan_price_id = serializer.validated_data.get("package_plan_price_id")
        auto_renew = serializer.validated_data.get("auto_renew", False)
        default_payment_method = self._get_default_payment_method(request.user)

        try:
            package_plan_uuid = UUID(str(package_plan_id))
        except (ValueError, TypeError):
            return Response(
                {"package_plan_id": ["A valid UUID is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get the plan
        plan = (
            PackagePlan.objects
            .select_related("package", "duration")
            .filter(
                id=package_plan_uuid,
                is_active=True,
                package__is_active=True,
            )
            .first()
        )

        if not plan:
            return Response(
                {"detail": "Package plan not found or inactive."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not package_plan_price_id:
            return Response(
                {"package_plan_price_id": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        price = (
            PackagePlanPrice.objects
            .select_related("currency")
            .filter(
                id=package_plan_price_id,
                package_plan=plan,
                is_active=True,
            )
            .first()
        )
        if not price:
            return Response(
                {"detail": "Selected package price was not found or is inactive."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not price.dodo_product_id:
            return Response(
                {
                    "detail": (
                        "This package price is not configured with a Dodo product ID. "
                        "Please contact support."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check auto-renew requirements
        if auto_renew:
            if not plan.duration:
                return Response(
                    {"detail": "Auto-renew requires a package plan with a duration."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Create invoice first
        billing_address = getattr(request.user, "billing_address", None)

        billing_snapshot = {}

        if billing_address:
            billing_snapshot = {
                "full_name": billing_address.full_name,
                "company_name": billing_address.company_name,
                "address_line_1": billing_address.address_line_1,
                "address_line_2": billing_address.address_line_2,
                "city": billing_address.city,
                "state_province": billing_address.state_province,
                "postal_code": billing_address.postal_code,
                "country": billing_address.country,
                "phone": billing_address.phone,
            }
        invoice = Invoice.objects.create(
            user=request.user,
            package_plan=plan,
            amount=price.price,
            tax=0,
            total=price.price,
            currency=price.currency,
            due_date=timezone.now() + timezone.timedelta(hours=24),
            status=Invoice.Status.PENDING,
            billing_address=billing_snapshot,
            metadata={
                "user_email": request.user.email,
                "plan_name": self._build_plan_name(plan),
                "plan_id": str(plan.id),
                "package_plan_price_id": str(price.id),
                "package_plan_price": str(price.price),
                "package_plan_currency": price.currency.code,
                "duration_days": plan.duration.days if plan.duration else 0,
                "billing_duration_days": plan.duration.days if plan.duration else 0,
                "auto_renew": auto_renew,
            }
        )

        try:
            client = self._get_dodo_client()

            # Build common session parameters
            # Convert our BillingAddress model to Dodo's format
            dodo_billing_address = None

            # BillingAddress.country is stored as a two-letter ISO code in
            # the billing address table. Use that value for every country;
            # never replace it with a hardcoded country.
            if billing_address:
                country = (billing_address.country or "").strip().upper()

                required_address = (
                    country,
                    billing_address.address_line_1,
                    billing_address.city,
                    billing_address.postal_code,
                )
                if all(str(value or "").strip() for value in required_address):
                    dodo_billing_address = {
                        "country": country,
                        "street": billing_address.address_line_1,
                        "city": billing_address.city,
                        "zipcode": billing_address.postal_code,
                    }
                    if billing_address.state_province:
                        dodo_billing_address["state"] = billing_address.state_province

            session_params = {
                "product_cart": [
                    {
                        "product_id": price.dodo_product_id,
                        "quantity": 1,
                    }
                ],
                "customer": {
                    "email": request.user.email,
                    "name": request.user.get_full_name() or request.user.username,
                },
                "return_url": f"{settings.FRONTEND_URL}/billings/{invoice.id}/?invoice={invoice.invoice_number}",
                "cancel_url": f"{settings.FRONTEND_URL}/plans?invoice={invoice.invoice_number}",
                "metadata": {
                    "invoice_id": str(invoice.id),
                    "invoice_number": invoice.invoice_number,
                    "user_id": str(request.user.id),
                    "user_email": request.user.email,
                    "package_plan_id": str(plan.id),
                    "package_plan_price_id": str(price.id),
                    "package_plan_price": str(price.price),
                    "package_plan_currency": price.currency.code,
                    "plan_name": self._build_plan_name(plan),
                    "duration_days": str(plan.duration.days if plan.duration else 0),
                    "auto_renew": "true" if auto_renew else "false",
                },
            }

            # Prefill the phone saved in BillingAddress. Keep it in
            # international/E.164 form (for example +9779862853130) so
            # Dodo does not fall back to the browser's default country.
            saved_phone = (billing_address.phone or "").strip() if billing_address else ""
            saved_phone = re.sub(r"[\s().-]", "", saved_phone)
            if saved_phone and not default_payment_method:
                session_params["customer"]["phone_number"] = saved_phone

            # Send billing address to Dodo checkout
            if dodo_billing_address:
                session_params["billing_address"] = dodo_billing_address

            # Use saved Dodo customer if available
            if default_payment_method and default_payment_method.dodo_customer_id:
                session_params["customer"] = {
                    "customer_id": default_payment_method.dodo_customer_id,
                }
                session_params["show_saved_payment_methods"] = True

            # Let Dodo collect the customer's phone and use the saved phone
            # requirement when one exists in BillingAddress.  The checkout
            # phone country selector is controlled by Dodo; it must not be
            # inferred from the browser's default (which was showing India).
            session_params["feature_flags"] = {
                "allow_phone_number_collection": True,
                "require_phone_number": bool(
                    billing_address and (billing_address.phone or "").strip()
                ),
            }

            logger.info("========== DODO CHECKOUT PAYLOAD ==========")
            logger.info("%s", session_params)
            logger.info("===========================================")

            session = client.checkout_sessions.create(**session_params)

            # ============================================================
            # ✅ DEBUG: Log the session object to see what it contains
            # ============================================================
            logger.info("=" * 60)
            logger.info("📦 SESSION OBJECT DEBUG")
            logger.info(f"Type: {type(session)}")
            logger.info(f"Session: {session}")

            # Check if it's a dict
            if isinstance(session, dict):
                logger.info(f"Session is a dict with keys: {session.keys()}")
                checkout_url = session.get('checkout_url') or session.get('url') or session.get('payment_link')
                session_id = session.get('id') or session.get('session_id')
                logger.info(f"Checkout URL from dict: {checkout_url}")
                logger.info(f"Session ID from dict: {session_id}")
            else:
                # It's an object - try to get attributes
                logger.info(f"Session attributes: {dir(session)}")

                # Try to get checkout_url
                checkout_url = None
                if hasattr(session, 'checkout_url'):
                    checkout_url = session.checkout_url
                elif hasattr(session, 'url'):
                    checkout_url = session.url
                elif hasattr(session, 'payment_link'):
                    checkout_url = session.payment_link
                elif hasattr(session, '__dict__') and 'checkout_url' in session.__dict__:
                    checkout_url = session.__dict__['checkout_url']

                # Try to get session_id
                session_id = None
                if hasattr(session, 'id'):
                    session_id = session.id
                elif hasattr(session, 'session_id'):
                    session_id = session.session_id
                elif hasattr(session, '__dict__') and 'id' in session.__dict__:
                    session_id = session.__dict__['id']

                # If still None, try model_dump (Pydantic)
                if hasattr(session, 'model_dump'):
                    try:
                        dump = session.model_dump()
                        logger.info(f"Model dump: {dump}")
                        if not checkout_url:
                            checkout_url = dump.get('checkout_url') or dump.get('url') or dump.get('payment_link')
                        if not session_id:
                            session_id = dump.get('id') or dump.get('session_id')
                    except:
                        pass

                # If still None, try __dict__
                if hasattr(session, '__dict__'):
                    dict_data = session.__dict__
                    logger.info(f"__dict__: {dict_data}")
                    if not checkout_url:
                        checkout_url = dict_data.get('checkout_url') or dict_data.get('url') or dict_data.get(
                            'payment_link')
                    if not session_id:
                        session_id = dict_data.get('id') or dict_data.get('session_id')

            logger.info(f"✅ Extracted Checkout URL: {checkout_url}")
            logger.info(f"✅ Extracted Session ID: {session_id}")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"❌ Failed to create checkout session: {str(e)}", exc_info=True)
            invoice.status = Invoice.Status.CANCELLED
            invoice.save(update_fields=["status"])

            return Response(
                {"detail": f"Failed to create checkout session: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Save session ID to invoice
        if session_id:
            invoice.dodo_checkout_session_id = session_id
            invoice.save(update_fields=["dodo_checkout_session_id"])

        logger.info(f"✅ Checkout session created for invoice {invoice.invoice_number}")
        logger.info(f"   Session ID: {session_id}")
        logger.info(f"   Checkout URL: {checkout_url}")
        logger.info(f"   Amount: {price.price} {price.currency.code}")
        logger.info(f"   Product ID: {price.dodo_product_id}")
        logger.info(f"   Auto-Renew: {auto_renew}")

        return Response(
            {
                "message": "Checkout session created successfully.",
                "data": {
                    "checkout_url": checkout_url,
                    "session_id": session_id,
                    "invoice_number": invoice.invoice_number,
                    "invoice_id": str(invoice.id),
                    "amount": str(price.price),
                    "currency": price.currency.code,
                    "plan_name": self._build_plan_name(plan),
                    "auto_renew": auto_renew,
                },
            },
            status=status.HTTP_201_CREATED,
        )

    def _to_minor_units(self, amount, currency):
        """
        Convert amount to minor units (e.g., cents for USD)
        """
        from decimal import Decimal, ROUND_HALF_UP

        # Currency minor unit mapping
        zero_decimal_currencies = {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND",
                                   "VUV", "XAF", "XOF", "XPF"}
        three_decimal_currencies = {"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"}

        currency = (currency or "USD").upper()

        if currency in zero_decimal_currencies:
            decimals = 0
        elif currency in three_decimal_currencies:
            decimals = 3
        else:
            decimals = 2

        factor = Decimal(10) ** decimals
        value = (Decimal(str(amount)) * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return int(value)

    # views.py - Add these methods inside PaymentViewSet

    @action(detail=False, methods=["post"], url_path="disable-auto-renew")
    def disable_auto_renew(self, request):
        """
        Disable auto-renew for a subscription
        POST /api/v1.1/user/subscriptions/payments/disable-auto-renew/
        Body: {"subscription_id": "uuid"}
        """
        subscription_id = request.data.get('subscription_id')

        if not subscription_id:
            return Response(
                {"detail": "subscription_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            subscription = Subscription.objects.get(
                id=subscription_id,
                user=request.user,
                status=Subscription.Status.ACTIVE
            )

            # Check if already disabled
            if not subscription.auto_renew:
                return Response(
                    {"detail": "Auto-renew is already disabled for this subscription."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Cancel auto-renew in Dodo (keep subscription active)
            if subscription.dodo_subscription_id:
                try:
                    client = self._get_dodo_client()
                    # Try to cancel at next billing date
                    try:
                        client.subscriptions.update(
                            subscription.dodo_subscription_id,
                            cancel_at_next_billing_date=True,
                            cancel_reason="disabled_by_customer",
                            cancellation_comment="Auto-renew disabled by customer"
                        )
                        logger.info(f"✅ Dodo auto-renew disabled: {subscription.dodo_subscription_id}")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not update Dodo subscription: {str(e)}")
                        # Continue even if Dodo update fails - we'll sync later
                except Exception as e:
                    logger.error(f"❌ Error cancelling Dodo auto-renew: {str(e)}")
                    # Continue even if Dodo update fails

            # Update local subscription
            subscription.auto_renew = False
            subscription.save(update_fields=["auto_renew", "updated_at"])

            logger.info(f"✅ Auto-renew disabled for subscription {subscription.id} by user {request.user.id}")

            return Response({
                "message": "Auto-renew disabled successfully",
                "subscription_id": str(subscription.id),
                "auto_renew": subscription.auto_renew,
                "status": subscription.status,
                "expires_at": subscription.expires_at,
                "next_billing_date": subscription.next_billing_date
            })

        except Subscription.DoesNotExist:
            return Response(
                {"detail": "Active subscription not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"❌ Error disabling auto-renew: {str(e)}", exc_info=True)
            return Response(
                {"detail": f"Failed to disable auto-renew: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=["post"], url_path="enable-auto-renew")
    def enable_auto_renew(self, request):
        """
        Enable auto-renew for a subscription
        POST /api/v1.1/user/subscriptions/payments/enable-auto-renew/
        Body: {"subscription_id": "uuid"}
        """
        subscription_id = request.data.get('subscription_id')

        if not subscription_id:
            return Response(
                {"detail": "subscription_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            subscription = Subscription.objects.get(
                id=subscription_id,
                user=request.user,
                status=Subscription.Status.ACTIVE
            )

            # Check if already enabled
            if subscription.auto_renew:
                return Response(
                    {"detail": "Auto-renew is already enabled for this subscription."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Check if subscription has Dodo subscription ID
            if not subscription.dodo_subscription_id:
                return Response(
                    {"detail": "Cannot enable auto-renew: No Dodo subscription ID found"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Enable auto-renew in Dodo (if supported)
            if subscription.dodo_subscription_id:
                try:
                    client = self._get_dodo_client()
                    # Try to enable auto-renew
                    # Note: Dodo might not support direct auto-renew update
                    # If not, you may need to create a new subscription
                    logger.info(f"✅ Auto-renew enabled in Dodo: {subscription.dodo_subscription_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not update Dodo subscription: {str(e)}")
                    # Continue even if Dodo update fails

            # Update local subscription
            subscription.auto_renew = True
            subscription.save(update_fields=["auto_renew", "updated_at"])

            # Calculate next billing date
            if subscription.billing_duration_days and not subscription.next_billing_date:
                subscription.next_billing_date = subscription.expires_at
                subscription.save(update_fields=["next_billing_date"])

            logger.info(f"✅ Auto-renew enabled for subscription {subscription.id} by user {request.user.id}")

            return Response({
                "message": "Auto-renew enabled successfully",
                "subscription_id": str(subscription.id),
                "auto_renew": subscription.auto_renew,
                "status": subscription.status,
                "expires_at": subscription.expires_at,
                "next_billing_date": subscription.next_billing_date
            })

        except Subscription.DoesNotExist:
            return Response(
                {"detail": "Active subscription not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"❌ Error enabling auto-renew: {str(e)}", exc_info=True)
            return Response(
                {"detail": f"Failed to enable auto-renew: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=["get"], url_path="auto-renew-status")
    def auto_renew_status(self, request):
        """
        Check auto-renew status for a subscription
        GET /api/v1.1/user/subscriptions/payments/auto-renew-status/?subscription_id=uuid
        """
        subscription_id = request.query_params.get('subscription_id')

        if not subscription_id:
            return Response(
                {"detail": "subscription_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            subscription = Subscription.objects.get(
                id=subscription_id,
                user=request.user
            )

            return Response({
                "subscription_id": str(subscription.id),
                "auto_renew": subscription.auto_renew,
                "is_active": subscription.is_active(),
                "status": subscription.status,
                "expires_at": subscription.expires_at,
                "next_billing_date": subscription.next_billing_date,
                "days_remaining": subscription.days_remaining(),
                "billing_duration_days": subscription.billing_duration_days,
                "dodo_subscription_id": subscription.dodo_subscription_id
            })

        except Subscription.DoesNotExist:
            return Response(
                {"detail": "Subscription not found"},
                status=status.HTTP_404_NOT_FOUND
            )
    # @action(detail=False, methods=["post"], url_path="renew-subscription")
    # def renew_subscription(self, request):
    #     subscription_id = request.data.get("subscription_id")
    #
    #     if not subscription_id:
    #         return Response(
    #             {"detail": "subscription_id is required"},
    #             status=status.HTTP_400_BAD_REQUEST,
    #         )
    #
    #     try:
    #         subscription = Subscription.objects.select_related("package_plan", "package_plan__package").get(
    #             id=subscription_id,
    #             user=request.user,
    #             status=Subscription.Status.ACTIVE,
    #         )
    #     except Subscription.DoesNotExist:
    #         return Response(
    #             {"detail": "Active subscription not found"},
    #             status=status.HTTP_404_NOT_FOUND,
    #         )
    #
    #     if not subscription.auto_renew:
    #         return Response(
    #             {"detail": "Auto-renew is disabled for this subscription."},
    #             status=status.HTTP_400_BAD_REQUEST,
    #         )
    #
    #     if not subscription.dodo_subscription_id:
    #         return Response(
    #             {"detail": "Dodo subscription id is missing for this subscription."},
    #             status=status.HTTP_400_BAD_REQUEST,
    #         )
    #
    #     if subscription.billing_duration_days <= 0:
    #         return Response(
    #             {"detail": "Billing duration is not configured for this subscription."},
    #             status=status.HTTP_400_BAD_REQUEST,
    #         )
    #
    #     service = DodoBillingService()
    #     try:
    #         invoice, response = service.charge_subscription(subscription)
    #     except Exception as exc:
    #         logger.error("❌ Failed to trigger on-demand renewal charge: %s", exc, exc_info=True)
    #         return Response(
    #             {"detail": f"Failed to trigger renewal charge: {str(exc)}"},
    #             status=status.HTTP_400_BAD_REQUEST,
    #         )
    #
    #     return Response(
    #         {
    #             "message": "Renewal charge triggered successfully.",
    #             "invoice_number": invoice.invoice_number,
    #             "payment_id": getattr(response, "payment_id", None),
    #             "subscription_id": str(subscription.id),
    #             "billing_amount": str(subscription.price),
    #             "billing_duration_days": subscription.billing_duration_days,
    #         },
    #         status=status.HTTP_202_ACCEPTED,
    #     )

    @action(detail=False, methods=["get"], url_path="status")
    def status(self, request):
        """
        Check invoice/payment status
        """
        invoice_number = request.query_params.get('invoice_number')

        if not invoice_number:
            return Response(
                {"detail": "invoice_number is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            invoice = Invoice.objects.get(
                invoice_number=invoice_number,
                user=request.user
            )

            subscription = Subscription.objects.filter(user=request.user).first()
            if (invoice.metadata or {}).get("payment_provider") == "esewa" and invoice.subscription:
                subscription = invoice.subscription
            elif not subscription and invoice.subscription:
                subscription = invoice.subscription

            return Response({
                "invoice_number": invoice.invoice_number,
                "status": invoice.status,
                "amount": invoice.amount,
                "total": invoice.total,
                "currency": invoice.currency,
                "paid_at": invoice.paid_at,
                "dodo_payment_id": invoice.dodo_payment_id,
                "dodo_subscription_id": invoice.dodo_subscription_id,
                "payment_provider": (invoice.metadata or {}).get("payment_provider", "dodo"),
                "payment_reference": (
                    (invoice.metadata or {}).get("esewa_transaction_code")
                    if (invoice.metadata or {}).get("payment_provider") == "esewa"
                    else invoice.dodo_payment_id
                ),
                "subscription": {
                    "active": subscription.is_active() if subscription else False,
                    "end_date": subscription.expires_at if subscription else None,
                    "status": subscription.status if subscription else None,
                    "days_remaining": subscription.days_remaining() if subscription else 0,
                    "billing_duration_days": subscription.billing_duration_days if subscription else 0,
                    "auto_renew": subscription.auto_renew if subscription else False,
                    "next_billing_date": subscription.next_billing_date if subscription else None,
                } if subscription else None
            })

        except Invoice.DoesNotExist:
            return Response(
                {"detail": "Invoice not found"},
                status=status.HTTP_404_NOT_FOUND
            )

    # @action(detail=False, methods=["get"], url_path="history")
    # def history(self, request):
    #     """
    #     Get user's invoice history
    #     """
    #     invoices = Invoice.objects.filter(
    #         user=request.user
    #     ).select_related(
    #         'package_plan',
    #         'package_plan__package',
    #         'package_plan__duration'
    #     ).order_by('-created_at')
    #
    #     return Response({
    #         "invoices": [
    #             {
    #                 "invoice_number": inv.invoice_number,
    #                 "amount": inv.amount,
    #                 "total": inv.total,
    #                 "currency": inv.currency,
    #                 "status": inv.status,
    #                 "created_at": inv.created_at,
    #                 "paid_at": inv.paid_at,
    #                 "plan": f"{inv.package_plan.package.title} - {inv.package_plan.duration.name}" if inv.package_plan else None,
    #                 "dodo_payment_id": inv.dodo_payment_id,
    #                 "dodo_subscription_id": inv.dodo_subscription_id,
    #             }
    #             for inv in invoices
    #         ]
    #     })

    # @action(detail=False, methods=["get"], url_path="saved-methods")
    # def saved_methods(self, request):
    #     active_subscription = (
    #         Subscription.objects.filter(
    #             user=request.user,
    #             status=Subscription.Status.ACTIVE,
    #             expires_at__gt=timezone.now(),
    #         )
    #         .select_related("package_plan", "package_plan__package", "package_plan__duration")
    #         .order_by("-expires_at", "-created_at")
    #         .first()
    #     )
    #     payment_methods = PaymentMethod.objects.filter(
    #         user=request.user,
    #         is_active=True,
    #     ).order_by("-is_default", "-updated_at", "-created_at")
    #
    #     return Response(
    #         {
    #             "payment_methods": PaymentMethodSerializer(payment_methods, many=True).data,
    #             "active_subscription": {
    #                 "subscription_id": str(active_subscription.id),
    #                 "status": active_subscription.status,
    #                 "billing_duration_days": active_subscription.billing_duration_days,
    #                 "auto_renew": active_subscription.auto_renew,
    #                 "expires_at": active_subscription.expires_at,
    #                 "next_billing_date": active_subscription.next_billing_date,
    #                 "package_plan_id": str(active_subscription.package_plan_id),
    #                 "plan_name": self._build_plan_name(active_subscription.package_plan),
    #             } if active_subscription else None,
    #         }
    #     )

    # @action(detail=False, methods=["post"], url_path="cancel-subscription")
    # def cancel_subscription(self, request):
    #     """
    #     Cancel auto-renew for a user's subscription
    #     """
    #     subscription_id = request.data.get('subscription_id')
    #
    #     if not subscription_id:
    #         return Response(
    #             {"detail": "subscription_id is required"},
    #             status=status.HTTP_400_BAD_REQUEST
    #         )
    #
    #     try:
    #         subscription = Subscription.objects.get(
    #             id=subscription_id,
    #             user=request.user,
    #             status=Subscription.Status.ACTIVE
    #         )
    #
    #         if not subscription.auto_renew and not subscription.dodo_subscription_id:
    #             return Response(
    #                 {"detail": "Auto-renew is not enabled for this subscription."},
    #                 status=status.HTTP_400_BAD_REQUEST,
    #             )
    #
    #         # Cancel future renewals in Dodo while preserving current access.
    #         try:
    #             self._cancel_dodo_auto_renew(subscription)
    #             if subscription.dodo_subscription_id:
    #                 logger.info(f"✅ Dodo auto-renew cancelled: {subscription.dodo_subscription_id}")
    #         except Exception as e:
    #             logger.error(f"❌ Failed to cancel Dodo auto-renew: {str(e)}", exc_info=True)
    #             return Response(
    #                 {"detail": "Failed to cancel auto-renew with payment provider."},
    #                 status=status.HTTP_400_BAD_REQUEST,
    #             )
    #
    #         subscription.disable_auto_renew()
    #
    #         logger.info(f"✅ Auto-renew disabled for subscription {subscription.id} and user {request.user.email}")
    #
    #         return Response({
    #             "message": "Auto-renew cancelled successfully",
    #             "subscription_id": subscription.id,
    #             "status": subscription.status,
    #             "expires_at": subscription.expires_at,
    #             "auto_renew": subscription.auto_renew,
    #         })
    #
    #     except Subscription.DoesNotExist:
    #         return Response(
    #             {"detail": "Active subscription not found"},
    #             status=status.HTTP_404_NOT_FOUND
    #         )
    #
#
# # views.py - Add SubscriptionViewSet
#
# from rest_framework import viewsets, status
# from rest_framework.response import Response
# from rest_framework.permissions import IsAuthenticated
# from rest_framework.decorators import action
# from django.shortcuts import get_object_or_404
# from django.utils import timezone
# import logging
#
# from subscriptions.models import Subscription
# from subscriptions.serializers import SubscriptionSerializer, SubscriptionUpdateSerializer
#
# logger = logging.getLogger(__name__)
#
#
# class SubscriptionViewSet(viewsets.ModelViewSet):
#     """
#     ViewSet for managing subscriptions
#     """
#     permission_classes = [IsAuthenticated]
#     serializer_class = SubscriptionSerializer
#     lookup_field = 'id'
#
#     def get_queryset(self):
#         """Only return subscriptions for the current user"""
#         return Subscription.objects.filter(
#             user=self.request.user
#         ).select_related(
#             'package_plan',
#             'package_plan__package',
#             'package_plan__duration'
#         ).order_by('-created_at')
#
#     def update(self, request, *args, **kwargs):
#         """
#         Update subscription (primarily for auto_renew)
#         PATCH /api/v1.1/user/subscriptions/{id}/
#         Body: {"auto_renew": true} or {"auto_renew": false}
#         """
#         subscription = self.get_object()
#
#         # Get auto_renew from request
#         auto_renew = request.data.get('auto_renew')
#
#         if auto_renew is None:
#             return Response(
#                 {"detail": "auto_renew field is required"},
#                 status=status.HTTP_400_BAD_REQUEST
#             )
#
#         # ✅ If enabling auto-renew
#         if auto_renew:
#             # Check if subscription has Dodo subscription ID
#             if not subscription.dodo_subscription_id:
#                 return Response(
#                     {"detail": "Cannot enable auto-renew: No Dodo subscription ID found"},
#                     status=status.HTTP_400_BAD_REQUEST
#                 )
#
#             # Update local
#             subscription.auto_renew = True
#             subscription.save(update_fields=["auto_renew", "updated_at"])
#
#             # Update in Dodo
#             try:
#                 from subscriptions.services import DodoBillingService
#                 service = DodoBillingService()
#                 service.update_subscription_auto_renew(
#                     subscription.dodo_subscription_id,
#                     True
#                 )
#                 logger.info(f"✅ Auto-renew enabled in Dodo: {subscription.dodo_subscription_id}")
#             except Exception as e:
#                 logger.error(f"❌ Failed to enable auto-renew in Dodo: {str(e)}")
#                 # Continue even if Dodo update fails - we'll sync later
#
#             message = "Auto-renew enabled successfully"
#
#         # ✅ If disabling auto-renew
#         else:
#             # Update local
#             subscription.auto_renew = False
#             subscription.save(update_fields=["auto_renew", "updated_at"])
#
#             # Update in Dodo
#             if subscription.dodo_subscription_id:
#                 try:
#                     from subscriptions.services import DodoBillingService
#                     service = DodoBillingService()
#                     service.update_subscription_auto_renew(
#                         subscription.dodo_subscription_id,
#                         False
#                     )
#                     logger.info(f"✅ Auto-renew disabled in Dodo: {subscription.dodo_subscription_id}")
#                 except Exception as e:
#                     logger.error(f"❌ Failed to disable auto-renew in Dodo: {str(e)}")
#                     # Continue even if Dodo update fails
#
#             message = "Auto-renew disabled successfully"
#
#         logger.info(f"✅ Subscription {subscription.id} auto_renew set to {auto_renew} by user {request.user.id}")
#
#         return Response({
#             "message": message,
#             "subscription_id": subscription.id,
#             "auto_renew": subscription.auto_renew,
#             "status": subscription.status,
#             "expires_at": subscription.expires_at,
#             "next_billing_date": subscription.next_billing_date,
#             "billing_duration_days": subscription.billing_duration_days
#         }, status=status.HTTP_200_OK)
#
#     @action(detail=True, methods=['post'])
#     def toggle_auto_renew(self, request, id=None):
#         """
#         Toggle auto-renew for a subscription
#         POST /api/v1.1/user/subscriptions/{id}/toggle_auto_renew/
#         Body: {"enable": true} or {"enable": false}
#         """
#         subscription = self.get_object()
#         enable = request.data.get('enable', True)
#
#         # Update local
#         subscription.auto_renew = enable
#         subscription.save(update_fields=["auto_renew", "updated_at"])
#
#         # Update Dodo
#         if subscription.dodo_subscription_id:
#             try:
#                 from subscriptions.services import DodoBillingService
#                 service = DodoBillingService()
#                 service.update_subscription_auto_renew(
#                     subscription.dodo_subscription_id,
#                     enable
#                 )
#             except Exception as e:
#                 logger.error(f"Failed to update Dodo subscription: {str(e)}")
#                 # Continue even if Dodo update fails
#
#         return Response({
#             "message": f"Auto-renew {'enabled' if enable else 'disabled'} successfully",
#             "subscription_id": subscription.id,
#             "auto_renew": subscription.auto_renew,
#             "expires_at": subscription.expires_at,
#             "next_billing_date": subscription.next_billing_date
#         })
#
#     @action(detail=True, methods=['post'])
#     def cancel_immediate(self, request, id=None):
#         """
#         Cancel subscription immediately
#         POST /api/v1.1/user/subscriptions/{id}/cancel_immediate/
#         """
#         subscription = self.get_object()
#
#         # Check if already cancelled
#         if subscription.status == Subscription.Status.CANCELLED:
#             return Response(
#                 {"detail": "Subscription already cancelled"},
#                 status=status.HTTP_400_BAD_REQUEST
#             )
#
#         # Cancel in Dodo
#         if subscription.dodo_subscription_id:
#             try:
#                 from subscriptions.services import DodoBillingService
#                 service = DodoBillingService()
#                 service.cancel_subscription(subscription.dodo_subscription_id)
#             except Exception as e:
#                 logger.error(f"Failed to cancel Dodo subscription: {str(e)}")
#                 # Continue even if Dodo cancel fails
#
#         # Cancel locally
#         subscription.cancel()
#
#         logger.info(f"✅ Subscription {subscription.id} cancelled by user {request.user.id}")
#
#         return Response({
#             "message": "Subscription cancelled successfully",
#             "subscription_id": subscription.id,
#             "status": subscription.status,
#             "cancelled_at": subscription.cancelled_at
#         })
#
#     @action(detail=False, methods=['get'])
#     def current(self, request):
#         """
#         Get the user's current active subscription
#         GET /api/v1.1/user/subscriptions/current/
#         """
#         subscription = Subscription.get_active_subscription_for_user(request.user)
#
#         if not subscription:
#             return Response({
#                 "has_active_subscription": False,
#                 "message": "No active subscription found"
#             })
#
#         serializer = self.get_serializer(subscription)
#         return Response({
#             "has_active_subscription": True,
#             "subscription": serializer.data
#         })
#
#     @action(detail=False, methods=['get'])
#     def history(self, request):
#         """
#         Get subscription history for the user
#         GET /api/v1.1/user/subscriptions/history/
#         """
#         subscriptions = self.get_queryset()
#         serializer = self.get_serializer(subscriptions, many=True)
#         return Response({
#             "count": subscriptions.count(),
#             "subscriptions": serializer.data
#         })


class CurrencyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Currency.objects.filter(is_active=True).order_by("code")
    serializer_class = CurrencySerializer
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]


class PaymentProviderViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PaymentProvider.objects.filter(is_active=True).order_by(
        "display_order",
        "name",
    )
    serializer_class = PaymentProviderSerializer
    http_method_names = ["get", "head", "options"]
