
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


class TokenResponseSerializer(serializers.Serializer):
    data = serializers.DictField()
    message = serializers.CharField()


class MessageResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


class ChangePasswordResponseSerializer(serializers.Serializer):
    data = serializers.DictField()
    message = serializers.CharField()
