
from rest_framework import serializers
from accounts.models import OTP, User
from system.models import ConfigChoice



class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class RefreshSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()





class SendOtpSerializer(serializers.ModelSerializer):
    class Meta:
        model = OTP
        fields = ["email"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    otp = serializers.CharField(write_only=True, required=False, allow_blank=True)
    first_name = serializers.CharField(required=False, allow_blank=True, default="")
    last_name = serializers.CharField(required=False, allow_blank=True, default="")
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
            "first_name",
            "last_name",
            "phone",
            "birth_date",
            "gender",
            "user_type",
        ]


class ForgetPasswordSerializer(serializers.ModelSerializer):
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True)

    class Meta:
        model = OTP
        fields = ["email", "otp", "new_password"]


class OtpVerifySerializer(serializers.ModelSerializer):
    class Meta:
        model = OTP
        fields = ["email", "otp"]


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
            "first_name",
            "last_name",
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
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    birth_date = serializers.DateField(required=False, allow_null=True)
    gender = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=ConfigChoice.objects.all())
    user_type = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=ConfigChoice.objects.all())

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
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
