
from rest_framework import serializers
from accounts.models import ContactUs, FAQ, NotificationPreference, OTP, User, UserSession
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


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)


class ProfileDetailSerializer(serializers.ModelSerializer):
    profile = serializers.SerializerMethodField()
    gender = serializers.PrimaryKeyRelatedField(read_only=True)
    user_type = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "phone",
            "profile",
            "birth_date",
            "gender",
            "user_type",
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


class ProfileUpdateSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    birth_date = serializers.DateField(required=False, allow_null=True)
    gender = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=ConfigChoice.objects.all())
    user_type = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=ConfigChoice.objects.all())

    class Meta:
        model = User
        fields = [
            "full_name",
            "phone",
            "birth_date",
            "gender",
            "user_type",
        ]


class ProfileImageUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["profile"]


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


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            'scan_alert',
            'weekly_performance',
            'product_updates',
            'security_alerts',
        ]


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
