import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone

from accounts.models import User
from system.models import SoftDeletable


# Create your models here.
class Currency(SoftDeletable):
    code = models.CharField(
        max_length=3,
        unique=True,
    )

    name = models.CharField(
        max_length=100,
    )

    symbol = models.CharField(
        max_length=10,
        blank=True,
    )


    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Package(SoftDeletable):
    """
        Main package/plan container
        Admin can create/modify packages freely
    """

    title = models.CharField(max_length=100)
    description = models.TextField()
    # Package type
    is_free = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    # Display
    display_order = models.PositiveIntegerField(default=0)

    # Future flexibility (JSON field for any additional features)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_free"],
                condition=models.Q(is_free=True),
                name="only_one_free_package",
            )
        ]


    def __str__(self):
        return self.title

    @classmethod
    def get_default_free_package(cls):
        return (
            cls.objects.filter(is_free=True, is_active=True)
            .order_by("display_order", "title", "id")
            .first()
        )


class Duration(SoftDeletable):
    name = models.CharField(max_length=100, unique=True)
    days = models.PositiveIntegerField(null=True, blank=True)
    discount = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.name



class PackagePlan(SoftDeletable):
    package = models.ForeignKey(Package, on_delete=models.PROTECT, null=True)
    duration = models.ForeignKey(Duration, on_delete=models.RESTRICT, null=True)
    # price =models.DecimalField(max_digits=10, decimal_places=2)
    # currency = models.ForeignKey(
    #     Currency,
    #     on_delete=models.PROTECT,
    #     related_name="package_plans",
    # )
    # Limits (directly on plan for flexibility)
    max_qrs = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum qr allowed. Null = unlimited"
    )
    max_scans = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum scans allowed. Null = unlimited"
    )

    max_team_members = models.PositiveIntegerField(
        default=0,
        help_text="Maximum team members. 0 = no team members allowed"
    )
    max_bulk_upload = models.PositiveIntegerField(
        default=0,
        help_text="Maximum Bulk upload. 0 = no team members allowed"
    )
    max_domain_add = models.PositiveIntegerField(
        default=0,
        help_text="Maximum domain add. 0 = no team members allowed"
    )

    # Additional features as JSON for flexibility
    features = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional features like: {'analytics': True, 'branding': True}"
    )
    # dodo_product_id = models.CharField(
    #     max_length=255,
    #     unique=True,
    #     null=True,
    #     blank=True,
    # )

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.package.title}"

    @classmethod
    def get_default_free_plan(cls):
        return (
            cls.objects.select_related("package", "duration")
            .filter(is_active=True, package__is_active=True, package__is_free=True)
            .order_by("duration__days", "duration__name", "id")
            .first()
        )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["package", "duration"],
                name="unique_package_duration",
            )
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class PackagePlanPrice(SoftDeletable):
    package_plan = models.ForeignKey(
        PackagePlan,
        on_delete=models.PROTECT,
        related_name="prices",
    )

    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="package_plan_prices",
    )

    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    is_default = models.BooleanField(default=True)

    dodo_product_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["package_plan", "currency"],
                name="unique_package_plan_currency",
            )
        ]

class PaymentMethod(SoftDeletable):
    """
    Payment method used for an invoice; cards may also be saved for Dodo.
    """

    class PaymentType(models.TextChoices):
        CARD = "card", "Credit/Debit Card"
        ESEWA = "esewa", "eSewa"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='payment_methods'
    )

    payment_type = models.CharField(
        max_length=10,
        choices=PaymentType.choices,
        default=PaymentType.CARD
    )

    # Dodo Payment integration
    dodo_customer_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Customer ID from Dodo Payment"
    )
    dodo_payment_method_id = models.CharField(
        max_length=255,
        unique=True,
        blank=True,
        null=True,
        help_text="Payment method ID from Dodo Payment"
    )

    # Card details (minimal for security)
    card_last_four = models.CharField(max_length=4, blank=True)
    card_brand = models.CharField(max_length=50, blank=True)
    card_expiry_month = models.CharField(max_length=2, blank=True)
    card_expiry_year = models.CharField(max_length=4, blank=True)

    # Status
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # Billing address
    billing_address = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', '-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'payment_type'],
                condition=models.Q(payment_type='esewa', is_deleted=False),
                name='unique_esewa_payment_method_per_user',
            ),
        ]

    def __str__(self):
        if self.card_brand and self.card_last_four:
            return f"{self.user.email} - {self.card_brand} ****{self.card_last_four}"
        return f"{self.user.email} - {self.payment_type}"

    def save(self, *args, **kwargs):
        # Ensure only one default payment method per user
        if self.is_default:
            PaymentMethod.objects.filter(
                user=self.user,
                is_default=True
            ).exclude(id=self.id).update(is_default=False)
        super().save(*args, **kwargs)


# class PackageLimit(SoftDeletable):
#     package = models.ForeignKey(Package, on_delete=models.PROTECT, null=True)
#     max_qrs = models.PositiveIntegerField(default=0)
#     max_scans = models.PositiveIntegerField(default=0)
#     max_team_members = models.PositiveIntegerField(default=0)


# class PackageFeature(SoftDeletable):
#     class Feature(models.TextChoices):
#         ADVANCED_ANALYTICS = "advanced_analytics", "Advanced Analytics"
#         CUSTOM_BRANDING = "custom_branding", "Custom Branding"
#         API_ACCESS = "api_access", "API Access"
#         CUSTOM_DOMAIN = "custom_domain", "Custom Domain"
#         BULK_IMPORT = "bulk_import", "Bulk Import"
#
#     package = models.ForeignKey(Package, on_delete=models.RESTRICT)
#     feature = models.CharField(max_length=100, choices=Feature.choices)
#     enabled = models.BooleanField(default=True)
#
#     def __str__(self):
#         return self.package


class Subscription(SoftDeletable):

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"
        PENDING = "pending", "Pending"
        FAILED = "failed", "Failed"
        GRACE_PERIOD = "grace_period", "Grace Period"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )

    package_plan = models.ForeignKey(
        PackagePlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )

    payment_method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="subscriptions",
    )

    # Snapshot of purchased plan
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    billing_duration_days = models.PositiveIntegerField(
        default=0,
    )

    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    qr_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    scan_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    scan_limit_remaining = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    team_member_limit = models.PositiveIntegerField(
        default=0,
    )
    bulk_upload_limit = models.PositiveIntegerField(
        default=0,
    )
    domain_add_limit = models.PositiveIntegerField(
        default=0,
    )

    features = models.JSONField(
        default=dict,
        blank=True,
    )

    started_at = models.DateTimeField()
    expires_at = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices= Status.choices,
        default=Status.PENDING,
    )

    auto_renew = models.BooleanField(default=False)

    dodo_subscription_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )

    last_renewal_date = models.DateTimeField(
        null=True,
        blank=True,
    )

    next_billing_date = models.DateTimeField(
        null=True,
        blank=True,
    )

    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def _invoice_auto_renew_enabled(cls, invoice):
        metadata = getattr(invoice, "metadata", {}) or {}
        raw_value = metadata.get("auto_renew")

        if isinstance(raw_value, bool):
            return raw_value

        if isinstance(raw_value, str):
            return raw_value.strip().lower() in {"1", "true", "yes", "on"}

        return bool(getattr(invoice, "dodo_subscription_id", None))

    @classmethod
    def get_or_create_subscription(cls, invoice):
        """
        Get or create subscription from invoice
        This handles both new subscriptions and renewals
        """
        duration = invoice.package_plan.duration
        duration_days = duration.days or 0
        now = timezone.now()
        auto_renew_enabled = cls._invoice_auto_renew_enabled(invoice)
        subscription = getattr(invoice, "subscription", None)

        # Prefer the invoice-linked subscription when present, otherwise
        # fall back to the user's active subscription for this plan.
        if not subscription:
            subscription = cls.objects.filter(
                user=invoice.user,
                package_plan=invoice.package_plan,
                status=cls.Status.ACTIVE
            ).first()

        if not subscription:
            # Create new subscription
            start_date = now
            end_date = start_date + timezone.timedelta(days=duration_days)

            subscription = cls.objects.create(
                user=invoice.user,
                package_plan=invoice.package_plan,
                payment_method=invoice.payment_method,
                price=invoice.total,
                currency=invoice.currency,
                qr_limit=invoice.package_plan.max_qrs,
                scan_limit=invoice.package_plan.max_scans,
                scan_limit_remaining=invoice.package_plan.max_scans,
                team_member_limit=invoice.package_plan.max_team_members,
                bulk_upload_limit=invoice.package_plan.max_bulk_upload,
                domain_add_limit=invoice.package_plan.max_domain_add,
                features=invoice.package_plan.features or {},
                billing_duration_days=duration_days,
                started_at=start_date,
                expires_at=end_date,
                status=cls.Status.ACTIVE,
                auto_renew=auto_renew_enabled,
                dodo_subscription_id=invoice.dodo_subscription_id or None,
                next_billing_date=end_date if auto_renew_enabled else None,
            )
        else:
            billing_duration_days = subscription.billing_duration_days or duration_days
            billing_delta = timezone.timedelta(days=billing_duration_days)

            # Extend existing subscription
            if subscription.expires_at < now:
                # Subscription expired, restart from now
                subscription.started_at = now
                subscription.expires_at = now + billing_delta
            else:
                # Extend from current end date
                subscription.expires_at += billing_delta

            subscription.status = cls.Status.ACTIVE
            subscription.billing_duration_days = billing_duration_days
            subscription.auto_renew = subscription.auto_renew or auto_renew_enabled
            subscription.last_renewal_date = now
            subscription.next_billing_date = subscription.expires_at
            if invoice.dodo_subscription_id:
                subscription.dodo_subscription_id = invoice.dodo_subscription_id
            if not subscription.payment_method and invoice.payment_method:
                subscription.payment_method = invoice.payment_method
            subscription.save(
                update_fields=[
                    "billing_duration_days",
                    "started_at",
                    "expires_at",
                    "status",
                    "auto_renew",
                    "last_renewal_date",
                    "next_billing_date",
                    "dodo_subscription_id",
                    "payment_method",
                    "updated_at",
                ]
            )

        return subscription

    @classmethod
    def get_active_subscription_for_user(cls, user):
        now = timezone.now()
        return (
            cls.objects.filter(
                user=user,
                status=cls.Status.ACTIVE,
                expires_at__gt=now,
            )
            .select_related("package_plan", "package_plan__package", "package_plan__duration")
            .order_by("-expires_at", "-created_at")
            .first()
        )

    @classmethod
    def get_or_create_default_subscription(cls, user):
        free_plan = (
            PackagePlan.objects
            .filter(
                package__is_free=True,
                package__is_active=True,
                is_active=True,
            )
            .prefetch_related("prices")
            .first()
        )

        if not free_plan:
            return None

        free_price = (
            free_plan.prices
            .filter(
                is_active=True,
                is_default=True,
            )
            .select_related("currency")
            .first()
        )

        if not free_price:
            # Fallback in case the free plan does not have a default price.
            free_price = (
                free_plan.prices
                .filter(is_active=True)
                .select_related("currency")
                .first()
            )

        if not free_price:
            return None

        subscription, created = cls.objects.get_or_create(
            user=user,
            package_plan=free_plan,
            defaults={
                "price": free_price.price,
                "currency": free_price.currency,
                "billing_duration_days": free_plan.duration.days,
                "status": cls.Status.ACTIVE,
                "started_at": timezone.now(),
                "expires_at": timezone.now() + timedelta(days=free_plan.duration.days),
                "auto_renew": False,
            },
        )

        if not created:
            subscription.price = free_price.price
            subscription.currency = free_price.currency
            subscription.billing_duration_days = free_plan.duration.days
            subscription.save(
                update_fields=[
                    "price",
                    "currency",
                    "billing_duration_days",
                    "updated_at",
                ]
            )

        return subscription

    @classmethod
    def get_usage_subscription_for_user(cls, user):
        return cls.get_active_subscription_for_user(user) or cls.get_or_create_default_subscription(user)

    def is_active(self):
        """Check if subscription is currently active"""
        return self.status == self.Status.ACTIVE and self.expires_at > timezone.now()

    def days_remaining(self):
        """Get days remaining in subscription"""
        if not self.is_active():
            return 0
        delta = self.expires_at - timezone.now()
        return delta.days

    def cancel(self):
        """Cancel subscription"""
        self.status = self.Status.CANCELLED
        self.cancelled_at = timezone.now()
        self.auto_renew = False
        self.save()
        return self

    def disable_auto_renew(self):
        """Stop future renewals while preserving current paid access."""
        self.auto_renew = False
        self.save(update_fields=["auto_renew", "updated_at"])
        return self


# ============================================
# INVOICE MODELS
# ============================================

class Invoice(SoftDeletable):
    """
    Invoice generated for subscription payments
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    invoice_number = models.CharField(max_length=50, unique=True)
    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="invoices"
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.PROTECT,
        related_name="invoices",
        null=True,
        blank=True
    )
    package_plan = models.ForeignKey(
        PackagePlan,
        on_delete=models.PROTECT,
        related_name="invoices"
    )
    payment_method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoices"
    )

    # Amounts
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    currency =models.ForeignKey(Currency, on_delete=models.PROTECT)

    # Dodo Payments references - ADD THESE FIELDS
    dodo_checkout_session_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="Checkout session ID from Dodo Payments"
    )
    dodo_payment_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="Payment ID from Dodo Payments"
    )
    dodo_subscription_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="Subscription ID from Dodo Payments"
    )

    # Dates
    due_date = models.DateTimeField()
    issued_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    # Additional data
    invoice_items = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    billing_address = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)  # ADD THIS FIELD


    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['invoice_number']),
            models.Index(fields=['status', 'due_date']),
        ]

    def __str__(self):
        return f"{self.invoice_number} - {self.user.email} ({self.total} {self.currency})"

    @staticmethod
    def generate_invoice_number():
        return f"INV-{uuid.uuid4().hex[:12].upper()}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        super().save(*args, **kwargs)

    def mark_as_paid(self, payment_id=None, subscription_id=None):
        """Mark invoice as paid and update Dodo references"""
        self.status = self.Status.PAID
        self.paid_at = timezone.now()

        if payment_id:
            self.dodo_payment_id = payment_id
        if subscription_id:
            self.dodo_subscription_id = subscription_id

        self.save()

        # Create or extend the user's subscription for this paid invoice.
        if self.package_plan:
            subscription = Subscription.get_or_create_subscription(self)
            self.subscription = subscription
            if subscription:
                self.save(update_fields=["subscription"])

        return self

    def mark_as_failed(self):
        """Mark invoice as failed"""
        self.status = self.Status.FAILED
        self.save()
        return self

    def refund(self, reason=None):
        """Mark invoice as refunded"""
        self.status = self.Status.REFUNDED
        self.metadata['refund_reason'] = reason
        self.save(update_fields=["metadata", "status"])
        return self


# ============================================
# PAYMENT MODELS
# ============================================
class PaymentWebhook(SoftDeletable):
    event_id = models.CharField(
        max_length=255,
        unique=True,
    )

    event_type = models.CharField(
        max_length=100,
    )

    payload = models.JSONField()

    processed = models.BooleanField(
        default=False,
    )

    processed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return f"{self.event_type} - {self.event_id}"




class PaymentProvider(SoftDeletable):
    """
    Payment providers available for customer checkout.

    supported_currencies defines the currencies that this provider
    is configured to accept. Provider services must still validate
    the actual transaction against the provider's API requirements.
    """

    code = models.CharField(
        max_length=30,
        unique=True,
    ) #esewa, dodo

    name = models.CharField(
        max_length=100,
    )
    logo = models.ImageField(upload_to="payment_providers/logo")

    supported_currencies = models.ManyToManyField(
        Currency,
        related_name="payment_providers",
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    display_order = models.PositiveIntegerField(
        default=0,
    )

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class Payment(SoftDeletable):
    """
    Payment transaction record
    """



    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    class PaymentType(models.TextChoices):
        INITIAL = "initial", "Initial Payment"
        RENEWAL = "renewal", "Renewal"
        REFUND = "refund", "Refund"

    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="payments"
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.PROTECT,
        related_name="payments"
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="payments"
    )
    payment_method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payments"
    )

    # Amounts
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="payments",
    )

    # Payment provider
    provider = models.ForeignKey(
        PaymentProvider,
        on_delete=models.PROTECT,

    )

    # Dodo Payment integration
    transaction_id = models.CharField(max_length=255, unique=True)
    dodo_payment_intent_id = models.CharField(max_length=255, blank=True)

    # Type and status
    payment_type = models.CharField(
        max_length=20,
        choices=PaymentType.choices,
        default=PaymentType.INITIAL
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    # Tracking
    paid_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    webhook = models.ForeignKey(
        PaymentWebhook,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payments",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"{self.transaction_id} - {self.amount} {self.currency} ({self.status})"


# ============================================
# AUDIT MODELS
# ============================================

class PackageHistory(SoftDeletable):
    """
    Audit trail for package changes
    """
    package = models.ForeignKey(
        Package,
        on_delete=models.PROTECT,
        related_name='history'
    )
    changed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        related_name='package_changes'
    )

    # Changes tracking
    changes = models.JSONField(
        help_text="Changes made: {'field': {'old': 'value', 'new': 'value'}}"
    )
    package_snapshot = models.JSONField(
        help_text="Complete snapshot of package at change time"
    )

    change_reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['package', 'created_at']),
        ]

    def __str__(self):
        return f"Package {self.package.title} changed by {self.changed_by.email if self.changed_by else 'System'}"


# ============================================
# CUSTOMER/SUPPORT MODELS (Optional)
# ============================================

class SubscriptionChangeLog(SoftDeletable):
    """
    Log changes to subscriptions (upgrades, downgrades, cancellations)
    """
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name='change_logs'
    )
    changed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        related_name='subscription_changes'
    )

    # Change details
    change_type = models.CharField(max_length=50)  # upgrade, downgrade, cancel, renew
    old_package_plan = models.ForeignKey(
        PackagePlan,
        on_delete=models.PROTECT,
        null=True,
        related_name='old_subscription_changes'
    )
    new_package_plan = models.ForeignKey(
        PackagePlan,
        on_delete=models.PROTECT,
        null=True,
        related_name='new_subscription_changes'
    )

    # Details
    changes = models.JSONField(default=dict)
    reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['subscription', 'created_at']),
            models.Index(fields=['change_type']),
        ]

    def __str__(self):
        return f"{self.subscription.user.email} - {self.change_type} ({self.created_at})"
