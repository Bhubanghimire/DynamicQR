from django.contrib import admin

from .models import (
    Package,
    Duration,
    PackagePlan,
    PaymentMethod,
    Subscription,
    Invoice,
    PaymentWebhook,
    Payment,
    PackageHistory,
    SubscriptionChangeLog,
)


# ============================================================
# PACKAGE
# ============================================================

@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "is_free",
        "is_active",
        "is_featured",
        "display_order",
    )

    list_filter = (
        "is_free",
        "is_active",
        "is_featured",
    )

    search_fields = (
        "title",
        "description",
    )

    ordering = (
        "display_order",
        "title",
    )

    readonly_fields = ()

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "title",
                    "description",
                )
            },
        ),
        (
            "Package Settings",
            {
                "fields": (
                    "is_free",
                    "is_active",
                    "is_featured",
                    "display_order",
                )
            },
        ),
        (
            "Additional Data",
            {
                "fields": (
                    "metadata",
                )
            },
        ),
    )


# ============================================================
# DURATION
# ============================================================

@admin.register(Duration)
class DurationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "days",
        "discount"
    )

    search_fields = (
        "name",
    )

    ordering = (
        "days",
        "name",
    )

    fieldsets = (
        (
            "Duration",
            {
                "fields": (
                    "name",
                    "discount",
                    "days",
                )
            },
        ),
    )


# ============================================================
# PACKAGE PLAN
# ============================================================

@admin.register(PackagePlan)
class PackagePlanAdmin(admin.ModelAdmin):
    list_display = (
        "package",
        "duration",
        "price",
        "currency",
        "max_qrs",
        "max_scans",
        "max_team_members",
        "max_bulk_upload",
        "max_domain_add",
        "is_active",
    )

    list_filter = (
        "is_active",
        "currency",
        "duration",
        "package",
    )

    search_fields = (
        "package__title",
    )

    ordering = (
        "package",
        "duration__days",
    )

    fieldsets = (
        (
            "Plan",
            {
                "fields": (
                    "package",
                    "duration",
                    "dodo_product_id",
                    "is_active",
                )
            },
        ),
        (
            "Pricing",
            {
                "fields": (
                    "price",
                    "currency",
                )
            },
        ),
        (
            "Limits",
            {
                "fields": (
                    "max_qrs",
                    "max_scans",
                    "max_team_members",
                    "max_bulk_upload",
                    "max_domain_add",
                )
            },
        ),
        (
            "Features",
            {
                "fields": (
                    "features",
                )
            },
        ),
    )


# ============================================================
# PAYMENT METHOD
# ============================================================

@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "payment_type",
        "card_display",
        "is_default",
        "is_active",
        "created_at",
    )

    list_filter = (
        "payment_type",
        "is_default",
        "is_active",
        "card_brand",
    )

    search_fields = (
        "user__email",
        "dodo_customer_id",
        "dodo_payment_method_id",
        "card_last_four",
    )

    ordering = (
        "-is_default",
        "-created_at",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "User",
            {
                "fields": (
                    "user",
                )
            },
        ),
        (
            "Payment Method",
            {
                "fields": (
                    "payment_type",
                    "is_default",
                    "is_active",
                )
            },
        ),
        (
            "Dodo Payment Information",
            {
                "fields": (
                    "dodo_customer_id",
                    "dodo_payment_method_id",
                )
            },
        ),
        (
            "Card Information",
            {
                "fields": (
                    "card_brand",
                    "card_last_four",
                    "card_expiry_month",
                    "card_expiry_year",
                )
            },
        ),
        (
            "Billing",
            {
                "fields": (
                    "billing_address",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(description="Card")
    def card_display(self, obj):
        if obj.card_brand and obj.card_last_four:
            return f"{obj.card_brand} ****{obj.card_last_four}"

        return "-"


# ============================================================
# SUBSCRIPTION
# ============================================================

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "package_name",
        "status",
        "price",
        "currency",
        "started_at",
        "expires_at",
        "auto_renew",
    )

    list_filter = (
        "status",
        "auto_renew",
        "package_plan__package",
        "package_plan__duration",
        "currency",
    )

    search_fields = (
        "user__email",
        "dodo_subscription_id",
        "package_plan__package__title",
    )

    ordering = (
        "-created_at",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Subscription",
            {
                "fields": (
                    "user",
                    "package_plan",
                    "payment_method",
                    "status",
                )
            },
        ),
        (
            "Purchased Plan Snapshot",
            {
                "description": (
                    "These values represent the plan purchased by the "
                    "customer and should not normally be changed manually."
                ),
                "fields": (
                    "price",
                    "currency",
                    "qr_limit",
                    "scan_limit",
                    "scan_limit_remaining",
                    "team_member_limit",
                    "bulk_upload_limit",
                    "domain_add_limit",
                    "features",
                )
            },
        ),
        (
            "Subscription Period",
            {
                "fields": (
                    "started_at",
                    "expires_at",
                    "auto_renew",
                    "last_renewal_date",
                    "next_billing_date",
                    "cancelled_at",
                )
            },
        ),
        (
            "Dodo",
            {
                "fields": (
                    "dodo_subscription_id",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(description="Package")
    def package_name(self, obj):
        return obj.package_plan.package.title


# ============================================================
# INVOICE
# ============================================================

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "user",
        "package_plan",
        "total",
        "currency",
        "status",
        "due_date",
        "paid_at",
    )

    list_filter = (
        "status",
        "currency",
        "package_plan__package",
    )

    search_fields = (
        "invoice_number",
        "user__email",
        "package_plan__package__title",
    )

    ordering = (
        "-created_at",
    )

    readonly_fields = (
        "invoice_number",
        "issued_at",
        "created_at",
        "updated_at",
        "billing_address",
    )

    fieldsets = (
        (
            "Invoice",
            {
                "fields": (
                    "invoice_number",
                    "user",
                    "subscription",
                    "package_plan",
                    "status",
                )
            },
        ),
        (
            "Payment Information",
            {
                "fields": (
                    "payment_method",
                    "amount",
                    "tax",
                    "total",
                    "currency",
                )
            },
        ),
        (
            "Dates",
            {
                "fields": (
                    "due_date",
                    "issued_at",
                    "paid_at",
                )
            },
        ),
        (
            "Additional Information",
            {
                "fields": (
                    "invoice_items",
                    "notes",
                    "billing_address",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


# ============================================================
# PAYMENT WEBHOOK
# ============================================================

@admin.register(PaymentWebhook)
class PaymentWebhookAdmin(admin.ModelAdmin):
    list_display = (
        "event_id",
        "event_type",
        "processed",
        "processed_at",
        "created_at",
    )

    list_filter = (
        "event_type",
        "processed",
    )

    search_fields = (
        "event_id",
        "event_type",
    )

    ordering = (
        "-created_at",
    )

    readonly_fields = (
        "event_id",
        "event_type",
        "payload",
        "processed",
        "processed_at",
        "created_at",
    )

    fieldsets = (
        (
            "Webhook",
            {
                "fields": (
                    "event_id",
                    "event_type",
                    "payload",
                )
            },
        ),
        (
            "Processing",
            {
                "fields": (
                    "processed",
                    "processed_at",
                )
            },
        ),
        (
            "Timestamp",
            {
                "fields": (
                    "created_at",
                )
            },
        ),
    )


# ============================================================
# PAYMENT
# ============================================================

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "transaction_id",
        "user",
        "amount",
        "currency",
        "payment_type",
        "status",
        "provider",
        "paid_at",
        "created_at",
    )

    list_filter = (
        "status",
        "payment_type",
        "provider",
        "currency",
    )

    search_fields = (
        "transaction_id",
        "dodo_payment_intent_id",
        "user__email",
        "subscription__dodo_subscription_id",
        "invoice__invoice_number",
    )

    ordering = (
        "-created_at",
    )

    readonly_fields = (
        "transaction_id",
        "created_at",
        "updated_at",
        "paid_at",
    )

    fieldsets = (
        (
            "Payment",
            {
                "fields": (
                    "user",
                    "subscription",
                    "invoice",
                    "payment_method",
                )
            },
        ),
        (
            "Amount",
            {
                "fields": (
                    "amount",
                    "currency",
                )
            },
        ),
        (
            "Provider",
            {
                "fields": (
                    "provider",
                    "transaction_id",
                    "dodo_payment_intent_id",
                    "webhook",
                )
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "payment_type",
                    "status",
                    "paid_at",
                    "error_message",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "metadata",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


# ============================================================
# PACKAGE HISTORY
# ============================================================

@admin.register(PackageHistory)
class PackageHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "package",
        "changed_by",
        "change_reason",
        "created_at",
    )

    list_filter = (
        "created_at",
    )

    search_fields = (
        "package__title",
        "changed_by__email",
        "change_reason",
    )

    ordering = (
        "-created_at",
    )

    readonly_fields = (
        "package",
        "changed_by",
        "changes",
        "package_snapshot",
        "change_reason",
        "created_at",
    )

    fieldsets = (
        (
            "Package",
            {
                "fields": (
                    "package",
                    "changed_by",
                    "change_reason",
                )
            },
        ),
        (
            "Changes",
            {
                "fields": (
                    "changes",
                    "package_snapshot",
                )
            },
        ),
        (
            "Timestamp",
            {
                "fields": (
                    "created_at",
                )
            },
        ),
    )


# ============================================================
# SUBSCRIPTION CHANGE LOG
# ============================================================

@admin.register(SubscriptionChangeLog)
class SubscriptionChangeLogAdmin(admin.ModelAdmin):
    list_display = (
        "subscription",
        "change_type",
        "changed_by",
        "old_package_plan",
        "new_package_plan",
        "created_at",
    )

    list_filter = (
        "change_type",
        "created_at",
    )

    search_fields = (
        "subscription__user__email",
        "changed_by__email",
        "reason",
    )

    ordering = (
        "-created_at",
    )

    readonly_fields = (
        "subscription",
        "changed_by",
        "change_type",
        "old_package_plan",
        "new_package_plan",
        "changes",
        "reason",
        "created_at",
    )

    fieldsets = (
        (
            "Subscription Change",
            {
                "fields": (
                    "subscription",
                    "changed_by",
                    "change_type",
                )
            },
        ),
        (
            "Plans",
            {
                "fields": (
                    "old_package_plan",
                    "new_package_plan",
                )
            },
        ),
        (
            "Details",
            {
                "fields": (
                    "changes",
                    "reason",
                )
            },
        ),
        (
            "Timestamp",
            {
                "fields": (
                    "created_at",
                )
            },
        ),
    )
