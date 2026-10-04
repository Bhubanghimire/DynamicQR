from rest_framework import serializers

from subscriptions.models import Duration, Invoice, Package, PackagePlan, PaymentMethod, Subscription, Currency, \
    PaymentProvider, PackagePlanPrice


class DurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Duration
        fields = (
            "id",
            "name",
            "discount",
            "days",
        )


class AdminDurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Duration
        fields = (
            "id",
            "name",
            "days",
            "discount",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
        )


class CheckoutSessionCreateSerializer(serializers.Serializer):
    product_id = serializers.CharField(required=False, allow_blank=False)
    package_plan_id = serializers.CharField(required=False, allow_blank=False)
    quantity = serializers.IntegerField(min_value=1, default=1)
    auto_renew = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        product_id = attrs.get("product_id")
        package_plan_id = attrs.get("package_plan_id")

        if not product_id and not package_plan_id:
            raise serializers.ValidationError("Provide either product_id or package_plan_id.")

        if package_plan_id:
            try:
                from uuid import UUID
                UUID(str(package_plan_id))
            except (ValueError, TypeError):
                raise serializers.ValidationError({"package_plan_id": "A valid UUID is required."})

        return attrs


class PackagePlanPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PackagePlanPrice
        fields = ("id", "currency", "price", "is_default", "dodo_product_id", "is_active")
        read_only_fields = ("id",)


class PackagePlanSerializer(serializers.ModelSerializer):
    duration = DurationSerializer(read_only=True)
    prices = PackagePlanPriceSerializer(many=True, read_only=True)

    class Meta:
        model = PackagePlan
        fields = (
            "id",
            "duration",
            "prices",
            "max_qrs",
            "max_scans",
            "max_team_members",
            "max_bulk_upload",
            "max_domain_add",
            "features",
            "is_active",
        )


class AdminPackagePlanPriceSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(required=False)

    class Meta:
        model = PackagePlanPrice
        fields = ("id", "currency", "price", "is_default", "dodo_product_id", "is_active")
        read_only_fields = ()


class AdminPackagePlanSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(required=False)
    duration = DurationSerializer(read_only=True)
    duration_id = serializers.PrimaryKeyRelatedField(
        queryset=Duration.objects.all(),
        source="duration",
        write_only=True,
    )
    prices = AdminPackagePlanPriceSerializer(many=True, required=False)

    class Meta:
        model = PackagePlan
        fields = (
            "id",
            "duration",
            "duration_id",
            "prices",
            "max_qrs",
            "max_scans",
            "max_team_members",
            "max_bulk_upload",
            "max_domain_add",
            "features",
            # "dodo_product_id",
            "is_active",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        prices = attrs.get("prices")
        if prices is not None:
            currencies = [price["currency"].pk for price in prices]
            if len(currencies) != len(set(currencies)):
                raise serializers.ValidationError({"prices": "Each currency can appear only once per plan."})
            defaults = sum(1 for price in prices if price.get("is_default", True))
            if prices and defaults != 1:
                raise serializers.ValidationError({"prices": "Exactly one price must be the default."})
        return attrs


class AdminPackageSerializer(serializers.ModelSerializer):
    plans = AdminPackagePlanSerializer(source="packageplan_set", many=True, required=False)

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
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
        )

    def create(self, validated_data):
        plans_data = validated_data.pop("packageplan_set", [])
        package = Package.objects.create(**validated_data)
        for plan_data in plans_data:
            # A package create always creates new plans. Never reuse a plan
            # UUID supplied by the client, otherwise SQLite/PostgreSQL can
            # raise UNIQUE constraint failed on subscriptions_packageplan.id.
            plan_data.pop("id", None)
            prices_data = plan_data.pop("prices", [])
            plan = PackagePlan.objects.create(package=package, **plan_data)
            for price in prices_data:
                price.pop("id", None)
                PackagePlanPrice.objects.create(package_plan=plan, **price)
        return package

    def update(self, instance, validated_data):
        plans_data = validated_data.pop("packageplan_set", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if plans_data is not None:
            existing_plans = {plan.id: plan for plan in instance.packageplan_set.all()}
            for plan_data in plans_data:
                plan_id = plan_data.pop("id", None)
                prices_data = plan_data.pop("prices", None)
                if plan_id:
                    if plan_id not in existing_plans:
                        raise serializers.ValidationError({
                            "plans": f"Plan id {plan_id} does not belong to this package."
                        })
                    plan = existing_plans[plan_id]
                    for attr, value in plan_data.items():
                        setattr(plan, attr, value)
                    plan.save()
                    if prices_data is not None:
                        existing_prices = {price.id: price for price in plan.prices.all()}
                        submitted_ids = set()
                        for price in prices_data:
                            price_id = price.pop("id", None)
                            if price_id:
                                if price_id not in existing_prices:
                                    raise serializers.ValidationError({
                                        "plans": f"Price id {price_id} does not belong to this plan."
                                    })
                                existing_price = existing_prices[price_id]
                                for attr, value in price.items():
                                    setattr(existing_price, attr, value)
                                existing_price.save()
                                submitted_ids.add(price_id)
                            else:
                                created_price = PackagePlanPrice.objects.create(
                                    package_plan=plan,
                                    **price,
                                )
                                submitted_ids.add(created_price.id)

                        for price_id, existing_price in existing_prices.items():
                            if price_id not in submitted_ids:
                                existing_price.hard_delete()
                else:
                    plan = PackagePlan.objects.create(package=instance, **plan_data)
                    for price in prices_data or []:
                        price.pop("id", None)
                        PackagePlanPrice.objects.create(package_plan=plan, **price)

        return instance


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
            "card_expiry_month",
            "card_expiry_year",
            "is_default",
            "is_active",
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
            # "price",
            # "currency",
            "max_qrs",
            "max_scans",
            "max_team_members",
            "max_bulk_upload",
            "max_domain_add",
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
            "billing_duration_days",
            "auto_renew",
            "package_plan",
        )


class InvoiceSerializer(serializers.ModelSerializer):
    payment_provider = serializers.SerializerMethodField()
    payment_reference = serializers.SerializerMethodField()
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    package_plan = InvoicePackagePlanSerializer(read_only=True)
    payment_method = PaymentMethodSerializer(read_only=True)
    subscription = SubscriptionSummarySerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Invoice
        fields = (
            "id",
            "invoice_number",
            "full_name",
            "status",
            "status_display",
            "amount",
            "tax",
            "total",
            "currency",
            "due_date",
            "issued_at",
            "paid_at",
            "payment_provider",
            "payment_reference",
            "invoice_items",
            "notes",
            "billing_address",
            "package_plan",
            "payment_method",
            "subscription",
            "created_at",
            "updated_at",
        )


    def get_payment_provider(self, obj):
        return (obj.metadata or {}).get("payment_provider", "dodo")

    def get_payment_reference(self, obj):
        if self.get_payment_provider(obj) == "esewa":
            return (obj.metadata or {}).get("esewa_transaction_code")
        return obj.dodo_payment_id


class InvoiceUserSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(source="full_name", read_only=True)


class AdminInvoiceSerializer(InvoiceSerializer):
    user = InvoiceUserSerializer(read_only=True)

    class Meta(InvoiceSerializer.Meta):
        fields = tuple(
            "user" if field == "full_name" else field
            for field in InvoiceSerializer.Meta.fields
        )


class UsageQuotaSerializer(serializers.Serializer):
    used = serializers.IntegerField()
    limit = serializers.IntegerField(allow_null=True)
    remaining = serializers.IntegerField(allow_null=True)
    unlimited = serializers.BooleanField()
    usage_percent = serializers.FloatField()


class UsagePackageSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    is_free = serializers.BooleanField()
    is_active = serializers.BooleanField()


class SubscriptionUsageSerializer(serializers.Serializer):
    subscription = SubscriptionSummarySerializer(allow_null=True)
    subscription_status = serializers.CharField()
    package = UsagePackageSerializer(allow_null=True)
    package_title = serializers.CharField(allow_null=True, allow_blank=True)
    package_plan = InvoicePackagePlanSerializer(allow_null=True)
    qr_generated_count = serializers.IntegerField()
    qr_usage = UsageQuotaSerializer()
    scan_usage = UsageQuotaSerializer()
    total_scan_count = serializers.IntegerField()
    unique_scan_count = serializers.IntegerField()
    team_member_limit = serializers.IntegerField(allow_null=True)
    bulk_upload_limit = serializers.IntegerField(allow_null=True)
    domain_add_limit = serializers.IntegerField(allow_null=True)
    domain_add_usage = UsageQuotaSerializer()
    features = serializers.JSONField()


class SubscriptionUsageSummarySerializer(serializers.Serializer):
    subscription = serializers.JSONField()
    features = serializers.JSONField()
    quotas = serializers.JSONField()
    metrics = serializers.JSONField()


# serializers.py - Add SubscriptionSerializer

class SubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for Subscription with auto-renew support"""

    package_name = serializers.CharField(source='package_plan.package.title', read_only=True)
    duration_name = serializers.CharField(source='package_plan.duration.name', read_only=True)
    days_remaining = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = (
            'id',
            'user',
            'package_plan',
            'package_name',
            'duration_name',
            'price',
            'currency',
            'billing_duration_days',
            'started_at',
            'expires_at',
            'status',
            'auto_renew',
            'dodo_subscription_id',
            'last_renewal_date',
            'next_billing_date',
            'cancelled_at',
            'created_at',
            'updated_at',
            'days_remaining',
            'is_active',
        )
        read_only_fields = (
            'id',
            'user',
            'package_plan',
            'price',
            'currency',
            'billing_duration_days',
            'started_at',
            'expires_at',
            'status',
            'dodo_subscription_id',
            'last_renewal_date',
            'next_billing_date',
            'cancelled_at',
            'created_at',
            'updated_at',
        )

    def get_days_remaining(self, obj):
        return obj.days_remaining()

    def get_is_active(self, obj):
        return obj.is_active()


class SubscriptionUpdateSerializer(serializers.ModelSerializer):
    """Simplified serializer for updating subscription"""

    class Meta:
        model = Subscription
        fields = ('auto_renew',)
        extra_kwargs = {
            'auto_renew': {'required': True},
        }


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = (
            "id",
            "code",
            "name",
            "symbol",
        )



class PaymentProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentProvider
        fields = (
            "id",
            "code",
            "name",
            "is_active",
            "display_order",
        )
