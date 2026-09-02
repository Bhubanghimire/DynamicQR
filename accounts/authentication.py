import jwt
from django.conf import settings
from django.utils import timezone
from rest_framework import authentication, exceptions

from accounts.models import User, UserSession


class JWTAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()

        if not header:
            return None

        if len(header) != 2 or header[0].decode().lower() != self.keyword.lower():
            return None

        token = header[1].decode()

        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=["HS256"]
            )
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Access token expired")
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed("Invalid access token")

        user = User.objects.filter(id=payload.get("user_id")).first()

        if user is None:
            raise exceptions.AuthenticationFailed("User not found")

        if not user.is_active:
            raise exceptions.AuthenticationFailed("User is inactive")

        session_id = payload.get("session_id")
        if session_id:
            session = UserSession.objects.filter(
                user=user,
                session_id=session_id,
                is_revoked=False,
                expires_at__gt=timezone.now(),
            ).first()
            if session is None:
                raise exceptions.AuthenticationFailed("Session is no longer active")
            session.save(update_fields=["last_seen_at"])

        return (user, payload)

    def authenticate_header(self, request):
        return self.keyword
