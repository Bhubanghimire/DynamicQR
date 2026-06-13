import json
import os
from datetime import datetime, timedelta

from django.db.models import Q
from fcm_django.models import FCMDevice

from django.contrib.auth.hashers import check_password
from django.core.mail import EmailMultiAlternatives
from django.http import JsonResponse
from django.utils.html import strip_tags
from django.views.generic.base import TemplateView
from rest_framework.response import Response
import jwt
from rest_framework.response import Response
from rest_framework import serializers, viewsets, status
from rest_framework.schemas.openapi import AutoSchema

from django.contrib.auth import authenticate
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_401_UNAUTHORIZED,
    HTTP_400_BAD_REQUEST
)
from rest_framework import exceptions
#
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from rest_framework.decorators import action
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth import get_user_model
from accounts.middleware import generate_access_token, generate_refresh_token, generate_otp
# from accounts.models import OTP, Advertise, About, Conversation, Message
# from accounts.serializers import UserSerializers, AdvertiseSerializer, UserUpdateSerializer, FCMDeviceSerializer, \
#     UserDetailSerializers, MessageSerializer

# from accounts.models import OTP
# from .serializers import UserSerializers
#
User = get_user_model()


class AccountsAuthSchema(AutoSchema):
    def get_tags(self, path, method):
        return ["Accounts"]

    def get_operation_id(self, path, method):
        return f"accounts_{self.view.action}"


class AuthViewSet(viewsets.ViewSet):
    schema = AccountsAuthSchema()
    permission_classes_by_action = {
        'refresh': [IsAuthenticated],
        'login': [AllowAny],
        'signup_otp': [AllowAny],
        'register': [AllowAny],
    }

    def get_permissions(self):
        try:
            return [permission() for permission in self.permission_classes_by_action[self.action]]
        except KeyError:
            return [permission() for permission in self.permission_classes]

    @action(detail=False, methods=['POST'], url_path='refresh')
    def refresh(self, request):
        token = request.POST.get('refresh_token')
        if token is None:
            return Response({"message": "please send refresh token in payload"}, status=HTTP_400_BAD_REQUEST)

        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed('Refresh Token expired')
        except Exception:
            raise exceptions.AuthenticationFailed("Invalid Refresh Token")

        user = User.objects.filter(id=payload.get('user_id')).first()
        if user is None:
            raise exceptions.AuthenticationFailed('User not found')

        if not user.is_active:
            raise exceptions.AuthenticationFailed('user is inactive')

        access_token = generate_access_token(user)
        refresh_token = generate_refresh_token(user)
        response = {
            "data": {
                "access_token": access_token,
                "refresh_token": refresh_token,
            },
            "message": "New Generated Credentials."
        }
        return Response(response)

    @action(detail=False, methods=['POST'], url_path='login')
    def login(self, request):
        password = request.data.get('password', False)
        email = request.data.get('email', False)
        print(email, password)

        if not (email or password):
            raise serializers.ValidationError(
                {"message": "Enter Email and password"}
            )

        # user = authenticate(request, email=email, password=password)
        user = User.objects.filter(email=email).first()
        if user is None:
            raise serializers.ValidationError(
                {"message": "A user with this email and password was not found."}
            )

        is_correct = check_password(password, user.password)
        print(user, is_correct)


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

    @action(detail=False, methods=['POST'], url_path='send-otp')
    def otp_send(self, request):
        data = request.data
        email = data['email']
        generated_otp = generate_otp()
        check_status = OTP.objects.filter(email=email)
        about = About.objects.first()
        if check_status.exists():
            check_status.update(otp=generated_otp)
        else:
            obj = OTP.objects.create(email=email, otp=generated_otp)
        context = {'title': 'Otp',
                   'content': generated_otp,
                   'location': about.address if about else "Australia",
                   'phone': about.phone if about else "1234567890",
                   "logo": about.logo.url if about else ""

                   }
        html_content = render_to_string("email_template.html", context=context)
        text_content = strip_tags(html_content)
        email = EmailMultiAlternatives('Otp for email verification', text_content, settings.DEFAULT_FROM_EMAIL, [email])
        email.attach_alternative(html_content, 'text/html')
        try:
            email.send()
        except Exception as e:
            print(e)
            return Response({"message": "Email not sending. Try again."}, status=HTTP_400_BAD_REQUEST)

        return Response({'message': 'OTP is sent to provided email.'})

    @action(detail=False, methods=['POST'], url_path='register')
    def register(self, request):
        data = request.data
        try:
            check_otp = OTP.objects.get(email=data['email'], otp=data['otp'])
        except OTP.DoesNotExist:
            return Response({'message': 'OTP not found'}, status=HTTP_400_BAD_REQUEST)

        # if User.objects.filter(email=data['email']).exists():
        #     return Response({'message': 'User already exists'}, status=HTTP_400_BAD_REQUEST)

        user_serializer = UserSerializers(data=data)
        user_serializer.is_valid(raise_exception=True)
        user_serializer.save()
        check_otp.delete()
        user = User.objects.get(id=user_serializer.data["id"])
        # user.set_password(data['password'])
        user.user_type_id = 2
        user.save()
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
        data = request.data
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
        data = request.data
        check_otp = OTP.objects.filter(email=data['email'], otp=data['otp'])
        if check_otp.exists():
            return JsonResponse({'message': 'OTP  matched'}, status=status.HTTP_200_OK)
        return Response({'message': 'OTP not matched'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['POST'], url_path='password-change')
    def change_password(self, request, *args, **kwargs):
        user = self.request.user
        old_pw = request.data.get('old_password', False)
        new_pw = request.data.get('new_password')

        if (old_pw or new_pw) is None:
            return Response({'data': {}, 'message': 'Please provide old and new password!'}, status=400)

        if check_password(old_pw, user.password):
            user.set_password(new_pw)
            user.save()
            return Response({'data': {}, 'message': 'Password changed successfully!'}, status=200)
        else:
            return Response({'data': {}, 'message': 'The Old Password does not match!'}, status=400)
