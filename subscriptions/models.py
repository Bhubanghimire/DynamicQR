from django.db import models
from accounts.models import User
from system.models import SoftDeletable


# Create your models here.
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


class Duration(SoftDeletable):
    name = models.CharField(max_length=100, unique=True)
    days = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return self.name



class PackagePlan(SoftDeletable):
    package = models.ForeignKey(Package, on_delete=models.PROTECT, null=True)
    duration = models.ForeignKey(Duration, on_delete=models.RESTRICT, null=True)
    price =models.DecimalField(max_digits=10, decimal_places=2)
    currency =models.CharField(max_length=10)
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

    # Additional features as JSON for flexibility
    features = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional features like: {'analytics': True, 'branding': True}"
    )

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.package.title}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["package", "duration"],
                name="unique_package_duration",
            )
        ]

    def save(self, *args, **kwargs):
        # If package is free, ensure price is 0
        if self.package and self.package.is_free:
            self.price = 0
        super().save(*args, **kwargs)


class PaymentMethod(SoftDeletable):
    """
    Saved payment methods for users (Dodo Payment)
    """

    class PaymentType(models.TextChoices):
        CARD = "card", "Credit/Debit Card"

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

    currency = models.CharField(
        max_length=3,
    )
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
    currency = models.CharField(max_length=3, default="NPR")

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


class Payment(SoftDeletable):
    """
    Payment transaction record
    """

    class Provider(models.TextChoices):
        DODO = "dodo", "Dodo"

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
    currency = models.CharField(max_length=3, default="NPR")

    # Payment provider
    provider = models.CharField(
        max_length=20,
        choices=Provider.choices,
        default=Provider.DODO,
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
