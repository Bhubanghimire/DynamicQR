from rest_framework import serializers
from accounts.models import BillingAddress, ContactUs, FAQ, NotificationPreference, OTP, User, UserSession, Workspace
from system.models import ConfigChoice

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

class GoogleLoginSerializer(serializers.Serializer):
    code = serializers.CharField()

class GoogleOAuthExchangeSerializer(serializers.Serializer):
    code = serializers.CharField()

class RefreshSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()

class SendOtpSerializer(serializers.ModelSerializer):
    class Meta:
        model = OTP
        fields = ["email"]

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    otp = serializers.CharField(write_only=True, required=False, allow_blank=True)
    full_name = serializers.CharField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(required=False, allow_blank=True, default="")
    birth_date = serializers.DateField(required=False, allow_null=True)
    gender = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=ConfigChoice.objects.all())
    user_type = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=ConfigChoice.objects.all())

    class Meta:
        model = User
        fields = [
            "email",
            "otp",
            "password",
            "full_name",
            "phone",
            "birth_date",
            "gender",
            "user_type",
        ]

class ForgetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True)

class OtpVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)

class ChangeEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.RegexField(r"^\d{6}$", write_only=True)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

class ProfileDetailSerializer(serializers.ModelSerializer):
    profile = serializers.SerializerMethodField()
    workspace = serializers.SerializerMethodField()
    gender = serializers.PrimaryKeyRelatedField(read_only=True)
    status = serializers.SerializerMethodField()
    user_type = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "phone",
            "status",
            "profile",
            "workspace",
            "birth_date",
            "gender",
            "user_type",
            "is_two_factor_enabled",
            "date_joined",
        ]
        read_only_fields = fields

    def get_profile(self, obj):
        if not obj.profile:
            return None

        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.profile.url)
        return obj.profile.url

    def get_workspace(self, obj):
        workspace = getattr(obj, "owned_workspace", None)
        if workspace is None:
            return None
        return WorkspaceSerializer(workspace, context=self.context).data

    def get_status(self, obj):
        return "Active" if obj.is_active else "Inactive"

class ProfileUpdateSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    birth_date = serializers.DateField(required=False, allow_null=True)
    gender = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=ConfigChoice.objects.all())
    user_type = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=ConfigChoice.objects.all())
    is_two_factor_enabled = serializers.BooleanField(required=False)

    class Meta:
        model = User
        fields = [
            "full_name",
            "phone",
            "birth_date",
            "gender",
            "user_type",
            "is_two_factor_enabled",
        ]

class ProfileImageUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["profile"]


class BillingAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingAddress
        fields = [
            "id",
            "full_name",
            "company_name",
            "address_line_1",
            "address_line_2",
            "city",
            "state_province",
            "postal_code",
            "country",
            "phone",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_country(self, value):
        value = value.strip().upper()
        if len(value) != 2 or not value.isalpha():
            raise serializers.ValidationError("Country must be a two-letter ISO code, such as NP or US.")
        return value

class UserAdminUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "email",
            "full_name",
            "phone",
            "birth_date",
            "gender",
            "user_type",
            "is_two_factor_enabled",
            "is_active",
        ]

class TokenResponseSerializer(serializers.Serializer):
    data = serializers.DictField()
    message = serializers.CharField()

class MessageResponseSerializer(serializers.Serializer):
    message = serializers.CharField()

class ChangePasswordResponseSerializer(serializers.Serializer):
    data = serializers.DictField()
    message = serializers.CharField()

class ContactUsSubmitSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactUs
        fields = ['full_name', 'email', 'phone', 'subject', 'message']

class FAQListSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ['id', 'question', 'answer']

class FAQAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ['id', 'question', 'answer', 'is_active', 'display_order']

class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            'scan_alert',
            'weekly_performance',
            'product_updates',
            'security_alerts',
        ]

class WorkspaceSerializer(serializers.ModelSerializer):
    active_domain = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = [
            "id",
            "name",
            "active_domain",
            "default_json",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_active_domain(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        if user is None or not getattr(user, "is_authenticated", False):
            return None

        domain = user.custom_domains.filter(
            status="active",
            is_deleted=False,
        ).first()
        if domain is None:
            return None

        from Qr.serializers import CustomDomainSerializer
        return {"id":domain.id, "name":domain.domain}

class UserSessionSerializer(serializers.ModelSerializer):
    is_current = serializers.SerializerMethodField()

    class Meta:
        model = UserSession
        fields = [
            'session_id',
            'user_agent',
            'ip_address',
            'is_revoked',
            'created_at',
            'last_seen_at',
            'expires_at',
            'is_current',
        ]

    def get_is_current(self, obj):
        request = self.context.get('request')
        payload = getattr(request, 'auth', None) if request else None
        if not isinstance(payload, dict):
            return False
        return str(payload.get('session_id')) == str(obj.session_id)

class UserAdminCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    full_name = serializers.CharField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(required=False, allow_blank=True, default="")
    birth_date = serializers.DateField(required=False, allow_null=True)
    gender = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=ConfigChoice.objects.all())

    class Meta:
        model = User
        fields = [
            "email",
            "password",
            "full_name",
            "phone",
            "birth_date",
            "gender",
        ]

    def create(self, validated_data):
        # Set default user_type to normal user
        # Using the same fallback ID used in register view
        validated_data['user_type_id'] = "004dbed1-bb73-496a-b5f2-a244b42de122"
        user = User.objects.create_user(**validated_data)
        return user

class UserAdminSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    plan = serializers.SerializerMethodField()
    enrolled = serializers.SerializerMethodField()
    workspace = serializers.SerializerMethodField()
    joined_date = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "name", "email", "status", "plan", "enrolled", "workspace", "joined_date"]

    def get_name(self, obj):
        return obj.full_name

    def get_status(self, obj):
        return "Active" if obj.is_active else "Inactive"

    def get_plan(self, obj):
        from subscriptions.models import Subscription
        subscription = Subscription.get_active_subscription_for_user(obj)
        if subscription and subscription.package_plan and subscription.package_plan.package:
            return subscription.package_plan.package.title
        return "No Plan"

    def get_enrolled(self, obj):
        from subscriptions.models import Subscription
        subscription = Subscription.get_active_subscription_for_user(obj)
        if subscription:
            return subscription.started_at
        return None

    def get_workspace(self, obj):
        workspace = getattr(obj, "owned_workspace", None)
        return workspace.name if workspace else "No Workspace"

    def get_joined_date(self, obj):
        return obj.date_joined

class UserAdminDetailSerializer(ProfileDetailSerializer):
    current_package = serializers.SerializerMethodField()
    billing_address = BillingAddressSerializer(read_only=True)

    class Meta(ProfileDetailSerializer.Meta):
        fields = ProfileDetailSerializer.Meta.fields + ["current_package", "billing_address"]

    def get_current_package(self, obj):
        from subscriptions.models import Subscription
        subscription = Subscription.get_active_subscription_for_user(obj)
        if not subscription:
            return None

        plan = subscription.package_plan
        package = plan.package if plan else None

        return {
            "package_title": package.title if package else None,
            "package_description": package.description if package else None,
            "price": plan.price if plan else None,
            "currency": plan.currency if plan else None,
            "max_qrs": plan.max_qrs if plan else None,
            "max_scans": plan.max_scans if plan else None,
            "max_team_members": plan.max_team_members if plan else None,
            "max_bulk_upload": plan.max_bulk_upload if plan else None,
            "max_domain_add": plan.max_domain_add if plan else None,
            "status": subscription.status,
            "expires_at": subscription.expires_at,
            "started_at": subscription.started_at,
        }
