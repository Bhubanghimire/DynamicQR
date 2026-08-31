from django.conf import settings
from django.db.models import Q, Prefetch
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from uuid import UUID
import re
from rest_framework.response import Response
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from DynamicOCR.schemas import PaginatedAutoSchema
from Qr.models import Project, QRCode
from DynamicOCR.pagination import CustomPagination
from subscriptions.models import Duration, Invoice, Package, PackagePlan, Subscription
from subscriptions.serializers import (
    CheckoutSessionCreateSerializer,
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


class PaymentSchema(PaginatedAutoSchema):
    def get_tags(self, path, method):
        return ["Subscription"]

    def get_operation_id(self, path, method):
        return f"payment_{self.view.action}"

    def get_request_body(self, path, method):
        if method.upper() != "POST":
            return {}
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
                            "quantity": {
                                "type": "integer",
                                "minimum": 1,
                                "default": 1,
                                "description": "Number of units to purchase.",
                            },
                        },
                        "required": ["package_plan_id"],
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
#
# from .models import PackagePlan, Invoice, Subscription
# from .serializers import CheckoutSessionCreateSerializer
# from .schemas import PaymentSchema

logger = logging.getLogger(__name__)


class PaymentViewSet(viewsets.ViewSet):
    schema = PaymentSchema()
    STATIC_DODO_PRODUCT_ID = "pdt_0NmWwpmViOK71N77YS7MR"
    permission_classes_by_action = {
        "create": [IsAuthenticated],
        "status": [IsAuthenticated],
        "history": [IsAuthenticated],
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

    def create(self, request):
        """
        Create checkout session
        """
        serializer = CheckoutSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        package_plan_id = serializer.validated_data["package_plan_id"]
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

        # Create invoice first
        invoice = Invoice.objects.create(
            user=request.user,
            package_plan=plan,
            amount=plan.price,
            tax=0,
            total=plan.price,
            currency=plan.currency,
            due_date=timezone.now() + timezone.timedelta(hours=24),
            status=Invoice.Status.PENDING,
            # metadata={
            #     "user_email": request.user.email,
            #     # "username": request.user.username,
            #     "plan_name": f"{plan.package} - {plan.duration.name}"
            # }
        )

        try:
            client = self._get_dodo_client()

            # Create checkout session
            session_params = {
                "product_cart": [
                    {
                        "product_id": self.STATIC_DODO_PRODUCT_ID,
                        "quantity": 1,
                    }
                ],
                "customer": {
                    "email": request.user.email,
                    "name": request.user.get_full_name() or request.user.username,
                },
                "return_url": f"{settings.FRONTEND_URL}/payment/success?invoice={invoice.invoice_number}",
                "cancel_url": f"{settings.FRONTEND_URL}/payment/cancel?invoice={invoice.invoice_number}",
                "metadata": {
                    "invoice_id": str(invoice.id),
                    "invoice_number": invoice.invoice_number,
                    "user_id": str(request.user.id),
                    "user_email": request.user.email,
                    "package_plan_id": str(plan.id),
                }
            }

            session = client.checkout_sessions.create(**session_params)

        except Exception as e:
            logger.error(f"Failed to create checkout session: {str(e)}")
            invoice.status = Invoice.Status.CANCELLED
            invoice.save(update_fields=["status"])

            return Response(
                {"detail": f"Failed to create checkout session: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = self._session_to_payload(session)
        checkout_session_id = payload.get("id") or payload.get("session_id")
        if not checkout_session_id:
            checkout_url = payload.get("checkout_url") or ""
            match = re.search(r"(cks_[A-Za-z0-9]+)", checkout_url)
            if match:
                checkout_session_id = match.group(1)

        return Response(
            {
                "message": "Checkout session created successfully.",
                "data": {
                    "checkout_url": payload.get("checkout_url"),
                    "session_id": checkout_session_id,
                    "invoice_number": invoice.invoice_number,
                    "invoice_id": invoice.id,
                },
            },
            status=status.HTTP_201_CREATED,
        )

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

            subscription = Subscription.objects.filter(
                user=request.user,
                current_invoice=invoice
            ).first()

            return Response({
                "invoice_number": invoice.invoice_number,
                "status": invoice.status,
                "amount": invoice.amount,
                "total": invoice.total,
                "paid_at": invoice.paid_at,
                "dodo_payment_id": invoice.dodo_payment_id,
                "subscription": {
                    "active": subscription.is_active() if subscription else False,
                    "end_date": subscription.end_date if subscription else None,
                    "status": subscription.status if subscription else None,
                } if subscription else None
            })

        except Invoice.DoesNotExist:
            return Response(
                {"detail": "Invoice not found"},
                status=status.HTTP_404_NOT_FOUND
            )

    def history(self, request):
        """
        Get user's invoice history
        """
        invoices = Invoice.objects.filter(
            user=request.user
        ).select_related('package_plan', 'package_plan__package', 'package_plan__duration').order_by('-created_at')

        return Response({
            "invoices": [
                {
                    "invoice_number": inv.invoice_number,
                    "amount": inv.amount,
                    "total": inv.total,
                    "status": inv.status,
                    "created_at": inv.created_at,
                    "paid_at": inv.paid_at,
                    "plan": f"{inv.package_plan.package.name} - {inv.package_plan.duration.name}" if inv.package_plan else None,
                }
                for inv in invoices
            ]
        })

    def cancel_subscription(self, request):
        """
        Cancel a user's subscription
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

            # Cancel in Dodo
            try:
                client = self._get_dodo_client()
                if subscription.dodo_subscription_id:
                    client.subscriptions.cancel(subscription.dodo_subscription_id)
            except Exception as e:
                logger.error(f"Failed to cancel Dodo subscription: {str(e)}")
                # Still cancel locally even if Dodo fails

            # Cancel locally
            subscription.cancel()

            return Response({
                "message": "Subscription cancelled successfully",
                "subscription_id": subscription.id,
                "status": subscription.status
            })

        except Subscription.DoesNotExist:
            return Response(
                {"detail": "Active subscription not found"},
                status=status.HTTP_404_NOT_FOUND
            )
