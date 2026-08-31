from rest_framework import serializers

from subscriptions.models import Duration, Invoice, Package, PackagePlan, PaymentMethod, Subscription


class DurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Duration
        fields = (
            "id",
            "name",
            "days",
        )


class PackagePlanSerializer(serializers.ModelSerializer):
    duration = DurationSerializer(read_only=True)

    class Meta:
        model = PackagePlan
        fields = (
            "id",
            "duration",
            "price",
            "currency",
            "max_qrs",
            "max_scans",
            "max_team_members",
            "features",
            "is_active",
        )


class PackageSerializer(serializers.ModelSerializer):
    plans = PackagePlanSerializer(source="packageplan_set", many=True, read_only=True)

    class Meta:
        model = Package
        fields = (
            "id",
            "title",
            "description",
            "is_free",
            "is_active",
            "is_featured",
            "display_order",
            "metadata",
            "plans",
        )


class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = (
            "id",
            "payment_type",
            "card_brand",
            "card_last_four",
            "is_default",
        )


class InvoicePackagePlanSerializer(serializers.ModelSerializer):
    package_id = serializers.UUIDField(source="package.id", read_only=True)
    package_title = serializers.CharField(source="package.title", read_only=True)
    duration = DurationSerializer(read_only=True)

    class Meta:
        model = PackagePlan
        fields = (
            "id",
            "package_id",
            "package_title",
            "duration",
            "price",
            "currency",
            "max_qrs",
            "max_scans",
            "max_team_members",
            "features",
            "is_active",
        )


class SubscriptionSummarySerializer(serializers.ModelSerializer):
    package_plan = InvoicePackagePlanSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = (
            "id",
            "status",
            "started_at",
            "expires_at",
            "auto_renew",
            "package_plan",
        )


class InvoiceSerializer(serializers.ModelSerializer):
    package_plan = InvoicePackagePlanSerializer(read_only=True)
    payment_method = PaymentMethodSerializer(read_only=True)
    subscription = SubscriptionSummarySerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Invoice
        fields = (
            "id",
            "invoice_number",
            "status",
            "status_display",
            "amount",
            "tax",
            "total",
            "currency",
            "due_date",
            "issued_at",
            "paid_at",
            "invoice_items",
            "notes",
            "package_plan",
            "payment_method",
            "subscription",
            "created_at",
            "updated_at",
        )


class UsageQuotaSerializer(serializers.Serializer):
    used = serializers.IntegerField()
    limit = serializers.IntegerField(allow_null=True)
    remaining = serializers.IntegerField(allow_null=True)
    unlimited = serializers.BooleanField()
    usage_percent = serializers.FloatField()


class SubscriptionUsageSerializer(serializers.Serializer):
    subscription = SubscriptionSummarySerializer(allow_null=True)
    subscription_status = serializers.CharField()
    qr_usage = UsageQuotaSerializer()
    scan_usage = UsageQuotaSerializer()
    total_scan_count = serializers.IntegerField()
    unique_scan_count = serializers.IntegerField()
    team_member_limit = serializers.IntegerField(allow_null=True)
    features = serializers.JSONField()
