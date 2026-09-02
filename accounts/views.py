import jwt
import os
import hashlib
from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.core.mail import EmailMultiAlternatives
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.apps import apps
from django.db import transaction
from django.db.models.deletion import ProtectedError, RestrictedError
from rest_framework import exceptions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.schemas.openapi import AutoSchema
from rest_framework import status
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED, HTTP_500_INTERNAL_SERVER_ERROR

from accounts.middleware import generate_access_token, generate_refresh_token, generate_otp
from accounts.models import FAQ, NotificationPreference, OTP, User, GoogleOAuthExchangeCode
from accounts.serializers import LoginSerializer, RefreshSerializer, SendOtpSerializer, RegisterSerializer, \
    ForgetPasswordSerializer, OtpVerifySerializer, ChangePasswordSerializer, TokenResponseSerializer, \
    MessageResponseSerializer, ChangePasswordResponseSerializer, ProfileDetailSerializer, ProfileUpdateSerializer, \
    ProfileImageUpdateSerializer, GoogleOAuthExchangeSerializer, ContactUsSubmitSerializer, FAQListSerializer, \
    NotificationPreferenceSerializer
from subscriptions.models import Subscription
from subscriptions.models import Invoice, Payment, PaymentMethod

from django.core import signing
from urllib.parse import urlencode

def set_refresh_cookie(response, refresh_token):
    """
    Use HTTPS-only cookie settings in production, but allow local HTTP dev.
    """
    cookie_kwargs = {
        "key": "refresh_token",
        "value": refresh_token,
        "httponly": True,
        "secure": settings.DEBUG,
        "samesite":"None", #"Lax" if settings.DEBUG else "None",
        "path": "/",  # CHANGE: Use "/" instead of specific path
        "max_age": 20 * 24 * 60 * 60
    }

    # Only add domain in production
    if not settings.DEBUG:
        cookie_domain = getattr(settings, "REFRESH_COOKIE_DOMAIN", None)
        if cookie_domain:
            cookie_kwargs["domain"] = cookie_domain
        cookie_kwargs["samesite"] = "None"
        cookie_kwargs["secure"] = True
    print(cookie_kwargs)
    # response.set_cookie(**cookie_kwargs)
    response.set_cookie(**cookie_kwargs)
    return response


class AccountsAuthSchema(AutoSchema):
    def get_tags(self, path, method):
        return ["Accounts"]

    def get_operation_id(self, path, method):
        return f"accounts_{self.view.action}"

    def get_request_serializer(self, path, method):
        action = getattr(self.view, "action", None)
        if action == "login":
            return LoginSerializer()
        if action == "refresh":
            return RefreshSerializer()
        if action == "otp_send":
            return SendOtpSerializer()
        if action == "register":
            return RegisterSerializer()
        if action == "forget_password":
            return ForgetPasswordSerializer()
        if action == "otp_verify":
            return OtpVerifySerializer()
        if action == "change_password":
            return ChangePasswordSerializer()
        return super().get_request_serializer(path, method)

    def get_request_body(self, path, method):
        return super().get_request_body(path, method)

    def get_response_serializer(self, path, method):
        action = getattr(self.view, "action", None)
        if method.upper() != "POST":
            return super().get_response_serializer(path, method)

        if action in {"login", "refresh", "register"}:
            return TokenResponseSerializer()
        if action in {"otp_send", "otp_verify", "forget_password"}:
            return MessageResponseSerializer()
        if action == "change_password":
            return ChangePasswordResponseSerializer()
        return super().get_response_serializer(path, method)

    def get_responses(self, path, method):
        return super().get_responses(path, method)


@method_decorator(csrf_exempt, name='dispatch')
class AuthViewSet(viewsets.ViewSet):
    schema = AccountsAuthSchema()
    permission_classes_by_action = {
        'refresh': [AllowAny],
        'login': [AllowAny],
        'signup_otp': [AllowAny],
        'register': [AllowAny],
        'otp_send': [AllowAny],
        'forget_password': [AllowAny],
        'otp_verify': [AllowAny],
        'change_password': [IsAuthenticated],
    }

    def get_permissions(self):
        try:
            return [permission() for permission in self.permission_classes_by_action[self.action]]
        except KeyError:
            return [permission() for permission in self.permission_classes]

    @action(detail=False, methods=['POST'], url_path='refresh')
    @csrf_exempt
    def refresh(self, request):
        # serializer = RefreshSerializer(data=refresh_token)
        # serializer.is_valid(raise_exception=True)
        # token = serializer.validated_data['refresh_token']
        # if token is None:
        #     return Response({"message": "please send refresh token in payload"}, status=HTTP_400_BAD_REQUEST)

        refresh_token = request.COOKIES.get("refresh_token")

        if not refresh_token:
            return Response(
                {"message": "Refresh token not found"},
                status=HTTP_401_UNAUTHORIZED,
            )

        try:
            payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed('Refresh Token expired')
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed("Invalid Refresh Token")

        user = User.objects.filter(id=payload.get('user_id')).first()
        if user is None:
            raise exceptions.AuthenticationFailed('User not found')

        if not user.is_active:
            raise exceptions.AuthenticationFailed('user is inactive')

        access_token = generate_access_token(user)
        refresh_token = generate_refresh_token(user)

        response = Response(
            {
                "data": {
                    "access_token": access_token,
                },
                "message": "Logged in successfully."
            },
            status=HTTP_200_OK,
        )

        return set_refresh_cookie(response, refresh_token)

    @action(detail=False, methods=['POST'], url_path='login')
    def login(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        user = User.objects.filter(email=email).first()
        if user is None:
            raise serializers.ValidationError(
                {"message": "A user with this email and password was not found."}
            )

        is_correct = check_password(password, user.password)
        if not is_correct:
            raise serializers.ValidationError(
                {"message": "A user with this email and password was not found."}
            )


        access_token = generate_access_token(user)
        refresh_token = generate_refresh_token(user)


        response = Response(
            {
                "data": {
                    "access_token": access_token,
                },
                "message": "Logged in successfully."
            },
            status=HTTP_200_OK,
        )

        return set_refresh_cookie(response, refresh_token)

    @action(detail=False, methods=['POST'], url_path='send-otp')
    def otp_send(self, request):
        serializer = SendOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        generated_otp = generate_otp()
        OTP.objects.filter(email=email).delete()
        OTP.objects.create(email=email, otp=generated_otp)
        context = {
            'title': 'Otp',
            'content': generated_otp,
            'location': 'Australia',
            'phone': '1234567890',
            'logo': ''
        }
        html_content = render_to_string("email_template.html", context=context)
        text_content = strip_tags(html_content)
        message = EmailMultiAlternatives('Otp for email verification', text_content, settings.DEFAULT_FROM_EMAIL, [email])
        message.attach_alternative(html_content, 'text/html')
        try:
            message.send()
        except Exception as e:
            print(e)
            return Response({"message": "Email not sending. Try again."}, status=HTTP_400_BAD_REQUEST)

        return Response({'message': 'OTP is sent to provided email.'})

    @action(detail=False, methods=['POST'], url_path='register')
    def register(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            check_otp = OTP.objects.get(email=data['email'], otp=data['otp'])
        except OTP.DoesNotExist:
            return Response({'message': 'OTP not found'}, status=HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user = User.objects.create_user(
                email=data['email'],
                password=data['password'],
                full_name=data.get('full_name', ''),
                phone=data.get('phone', ''),
                birth_date=data.get('birth_date'),
                gender=data.get('gender'),
                user_type_id=data.get('user_type').pk if data.get('user_type') else "004dbed1-bb73-496a-b5f2-a244b42de122",
            )
            Subscription.get_or_create_default_subscription(user)
            check_otp.delete()
        access_token = generate_access_token(user)
        refresh_token = generate_refresh_token(user)

        response = {
            "data": {
                "access_token": access_token,
                "refresh_token": refresh_token,
            },
            "message": "loggedIn successfully."
        }
        return Response(response, status=HTTP_200_OK)

    @action(detail=False, methods=['POST'], url_path='forget-password')
    def forget_password(self, request):
        serializer = ForgetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        check_otp = OTP.objects.filter(email=data['email'], otp=data['otp'])
        if check_otp.exists():
            try:
                user = User.objects.get(email=data['email'])
            except Exception:
                return Response({'message': 'User not found.'}, status=status.HTTP_400_BAD_REQUEST)

            user.set_password(data['new_password'])
            user.save()
            check_otp.delete()
            return Response({'message': 'Done'})
        else:
            return Response({'message': 'Otp is not matched'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['POST'], url_path='otp-verify')
    def otp_verify(self, request):
        serializer = OtpVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        check_otp = OTP.objects.filter(email=data['email'], otp=data['otp'])
        if check_otp.exists():
            return JsonResponse({'message': 'OTP  matched'}, status=status.HTTP_200_OK)
        return Response({'message': 'OTP not matched'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['POST'], url_path='password-change')
    def change_password(self, request, *args, **kwargs):
        user = self.request.user
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        old_pw = serializer.validated_data['old_password']
        new_pw = serializer.validated_data['new_password']

        if check_password(old_pw, user.password):
            user.set_password(new_pw)
            user.save()
            return Response({'data': {}, 'message': 'Password changed successfully!'}, status=200)
        else:
            return Response({'data': {}, 'message': 'The Old Password does not match!'}, status=400)


class ProfileViewset(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ProfileDetailSerializer
    schema = AccountsAuthSchema()

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.action == "update_profile":
            return ProfileUpdateSerializer
        if self.action == "update_profile_image":
            return ProfileImageUpdateSerializer
        if self.action in {"notification_preferences", "update_notification_preferences"}:
            return NotificationPreferenceSerializer
        return ProfileDetailSerializer

    @action(detail=False, methods=["GET"], url_path="detail")
    def profile_detail(self, request):
        serializer = self.get_serializer(self.get_object(), context={"request": request})
        return Response({"data": serializer.data}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["PATCH"], url_path="update")
    def update_profile(self, request):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        response_serializer = ProfileDetailSerializer(serializer.instance, context={"request": request})
        return Response(
            {"data": response_serializer.data, "message": "Profile updated successfully."},
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=["PATCH"],
        url_path="profile-image",
        parser_classes=[MultiPartParser, FormParser],
    )
    def update_profile_image(self, request):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        response_serializer = ProfileDetailSerializer(serializer.instance, context={"request": request})
        return Response(
            {"data": response_serializer.data, "message": "Profile image updated successfully."},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["GET"], url_path="notification-preferences")
    def notification_preferences(self, request):
        preference, _ = NotificationPreference.objects.get_or_create(
            user=request.user
        )
        serializer = self.get_serializer(preference)
        return Response({"data": serializer.data}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["PATCH"], url_path="notification-preferences")
    def update_notification_preferences(self, request):
        preference, _ = NotificationPreference.objects.get_or_create(
            user=request.user
        )
        serializer = self.get_serializer(preference, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "data": serializer.data,
                "message": "Notification preferences updated successfully.",
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["DELETE"], url_path="delete-account")
    def delete_account(self, request):
        user = request.user
        qr_code_model = apps.get_model("Qr", "QRCode")
        has_payments = (
            Payment.objects.filter(user=user).exists()
            or Invoice.objects.filter(user=user).exists()
            or PaymentMethod.objects.filter(user=user).exists()
            or Subscription.objects.filter(user=user).exists()
        )
        has_created_qr = qr_code_model.objects.filter(created_by=user).exists()

        deletion_mode = "hard"
        message = "Account deleted permanently."

        try:
            with transaction.atomic():
                if has_payments or has_created_qr:
                    deletion_mode = "soft"
                    message = "Account deleted successfully."
                    user.is_active = False
                    user.delete()
                else:
                    try:
                        user.hard_delete()
                    except (ProtectedError, RestrictedError):
                        deletion_mode = "soft"
                        message = "Account deleted successfully."
                        user.is_active = False
                        user.delete()
        except Exception:
            return Response(
                {"message": "Account could not be deleted."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = Response(
            {
                "data": {
                    "deletion_mode": deletion_mode,
                },
                "message": message,
            },
            status=status.HTTP_200_OK,
        )
        response.delete_cookie("refresh_token", path="/")
        return response


def _get_dev_social_user():
    email = os.getenv("DEV_SOCIAL_LOGIN_EMAIL", "test@example.com").strip() or "test@example.com"
    first_name = os.getenv("DEV_SOCIAL_LOGIN_FIRST_NAME", "Test").strip() or "Test"
    last_name = os.getenv("DEV_SOCIAL_LOGIN_LAST_NAME", "User").strip() or "User"
    full_name = os.getenv("DEV_SOCIAL_LOGIN_FULL_NAME", f"{first_name} {last_name}").strip() or f"{first_name} {last_name}"
    phone = os.getenv("DEV_SOCIAL_LOGIN_PHONE", "0000000000").strip() or "0000000000"

    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            "full_name": full_name,
            "phone": phone,
            "is_active": True,
        },
    )

    update_fields = []
    if not created:
        desired_values = {
            "full_name": full_name,
            "phone": phone,
            "is_active": True,
        }
        for field_name, value in desired_values.items():
            if getattr(user, field_name) != value:
                setattr(user, field_name, value)
                update_fields.append(field_name)
        if update_fields:
            user.save(update_fields=update_fields)

    return user

class GoogleLoginRedirectSchema(AutoSchema):
    def get_tags(self, path, method):
        return ["Accounts"]

    def get_operation_id(self, path, method):
        return "accounts_google_login"


class GoogleLoginCompleteSchema(AutoSchema):
    def get_tags(self, path, method):
        return ["Accounts"]

    def get_operation_id(self, path, method):
        return "accounts_google_login_complete"

@method_decorator(csrf_exempt, name='dispatch')
class GoogleLoginRedirectAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []
    schema = GoogleLoginRedirectSchema()

    def get(self, request):
        frontend_url = settings.GOOGLE_FRONTEND_CALLBACK

        print("=== GOOGLE LOGIN REDIRECT ===")
        print("FRONTEND CALLBACK:", frontend_url)

        return redirect(
            "/api/v1.1/user/accounts/allauth/google/login/"
        )

@method_decorator(csrf_exempt, name='dispatch')
class GoogleLoginCompleteAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]
    throttle_classes = []
    schema = GoogleLoginCompleteSchema()

    def get(self, request):
        print("=== GOOGLE LOGIN COMPLETE ===")
        print("SESSION:", dict(request.session))
        print("USER:", request.user)
        print("AUTHENTICATED:", request.user.is_authenticated)

        user = request.user

        if not user or not user.is_authenticated:
            return Response(
                {"message": "Authentication required."},
                status=HTTP_401_UNAUTHORIZED
            )

        raw_code = GoogleOAuthExchangeCode.issue_for_user(
            user,
            ttl_seconds=60
        )

        frontend_url = settings.GOOGLE_FRONTEND_CALLBACK

        separator = "&" if "?" in frontend_url else "?"

        return redirect(
            f"{frontend_url}{separator}code={raw_code}"
        )

class GoogleOAuthExchangeSchema(AutoSchema):
    def get_tags(self, path, method):
        return ["Accounts"]

    def get_operation_id(self, path, method):
        return "accounts_google_oauth_exchange"

    def get_request_serializer(self, path, method):
        if method.upper() == "POST":
            return GoogleOAuthExchangeSerializer()
        return super().get_request_serializer(path, method)

    def get_response_serializer(self, path, method):
        if method.upper() == "POST":
            return TokenResponseSerializer()
        return super().get_response_serializer(path, method)


@method_decorator(csrf_exempt, name='dispatch')
class GoogleOAuthExchangeAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []
    schema = GoogleOAuthExchangeSchema()

    def post(self, request):
        serializer = GoogleOAuthExchangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_code = serializer.validated_data["code"]
        code_hash = hashlib.sha256(raw_code.encode("utf-8")).hexdigest()

        with transaction.atomic():
            exchange_code = (
                GoogleOAuthExchangeCode.objects.select_for_update()
                .select_related("user")
                .filter(code_hash=code_hash, used_at__isnull=True)
                .first()
            )
            if exchange_code is None:
                return Response({"message": "Invalid or expired code."}, status=HTTP_400_BAD_REQUEST)
            if exchange_code.is_expired():
                exchange_code.delete()
                return Response({"message": "Invalid or expired code."}, status=HTTP_400_BAD_REQUEST)

            exchange_code.used_at = timezone.now()
            exchange_code.save(update_fields=["used_at"])
            user = exchange_code.user

        access_token = generate_access_token(user)
        refresh_token = generate_refresh_token(user)
        user_data = ProfileDetailSerializer(user, context={"request": request}).data

        response = Response(
            {
                "data": {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "user": user_data,
                },
                "message": "login successful",
            },
            status=HTTP_200_OK,
        )
        return set_refresh_cookie(response, refresh_token)


@method_decorator(csrf_exempt, name='dispatch')
class ContactUsSubmitAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def post(self, request):
        serializer = ContactUsSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"message": "Contact request submitted successfully."},
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_exempt, name='dispatch')
class FAQListAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request):
        faqs = FAQ.objects.filter(is_active=True).order_by('display_order', 'id')
        serializer = FAQListSerializer(faqs, many=True)
        return Response(
            {
                "data": serializer.data,
                "message": "FAQs fetched successfully.",
            },
            status=status.HTTP_200_OK,
        )
