import datetime
import jwt
import string
import math
import random
from .models import OTP
from django.conf import settings


def generate_access_token(user):

    access_token_payload = {
        'user_id': user.id,
        "is_superuser":user.is_superuser,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=70, minutes=1),
        'iat': datetime.datetime.utcnow(),
    }
    access_token = jwt.encode(access_token_payload,settings.SECRET_KEY, algorithm='HS256')
    return access_token


def generate_refresh_token(user):
    refresh_token_payload = {
        'user_id': user.id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=17,minutes=1),
        'iat': datetime.datetime.utcnow()
    }
    refresh_token = jwt.encode(
        refresh_token_payload, settings.SECRET_KEY, algorithm='HS256')

    return refresh_token


def generate_otp():
    first_digit = random.choice('123456789')          # avoids '0'
    remaining_digits = ''.join(random.choices(string.digits, k=4))  # allows '0'
    return first_digit + remaining_digits