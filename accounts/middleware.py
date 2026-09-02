import datetime
import jwt
import string
import math
import random
from .models import OTP, UserSession
from django.conf import settings


def _get_client_ip(request):
    if request is None:
        return None
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def create_user_session(user, request=None):
    return UserSession.objects.create(
        user=user,
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:512] if request else ""),
        ip_address=_get_client_ip(request) if request else None,
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(days=17, minutes=0),
    )


def generate_access_token(user, session_id=None):

    access_token_payload = {
        'user_id': str(user.id),
        "is_superuser":user.is_superuser,
        'session_id': str(session_id) if session_id else None,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=15, minutes=20),
        'iat': datetime.datetime.utcnow(),
    }
    access_token = jwt.encode(access_token_payload,settings.SECRET_KEY, algorithm='HS256')
    return access_token


def generate_refresh_token(user, session_id=None):
    refresh_token_payload = {
        'user_id': str(user.id),
        'session_id': str(session_id) if session_id else None,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=17,minutes=0),
        'iat': datetime.datetime.utcnow()
    }
    refresh_token = jwt.encode(
        refresh_token_payload, settings.SECRET_KEY, algorithm='HS256')

    return refresh_token


def generate_otp():
    first_digit = random.choice('123456789')          # avoids '0'
    remaining_digits = ''.join(random.choices(string.digits, k=5))  # allows '0'
    return first_digit + remaining_digits
