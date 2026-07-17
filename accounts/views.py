import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.core.mail import EmailMultiAlternatives
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import exceptions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.schemas.openapi import AutoSchema
from rest_framework import status
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED

from accounts.middleware import generate_access_token, generate_refresh_token, generate_otp
from accounts.models import OTP, User
from accounts.serializers import LoginSerializer, RefreshSerializer, SendOtpSerializer, RegisterSerializer, \
    ForgetPasswordSerializer, OtpVerifySerializer, ChangePasswordSerializer, TokenResponseSerializer, \
    MessageResponseSerializer, ChangePasswordResponseSerializer, ProfileDetailSerializer, ProfileUpdateSerializer, \
    ProfileImageUpdateSerializer


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
        check_status = OTP.objects.filter(email=email)
        if check_status.exists():
            check_status.update(otp=generated_otp)
        else:
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

        user = User.objects.create_user(
            email=data['email'],
            password=data['password'],
            full_name=data.get('full_name', ''),
            phone=data.get('phone', ''),
            birth_date=data.get('birth_date'),
            gender=data.get('gender'),
            user_type_id=data.get('user_type').pk if data.get('user_type') else "004dbed1-bb73-496a-b5f2-a244b42de122",
        )
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
