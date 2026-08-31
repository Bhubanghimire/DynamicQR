import os
import uuid
from urllib.parse import urlparse
from urllib.request import urlopen

from django.core.files.base import ContentFile
from allauth.account.models import EmailAddress
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialLogin

from accounts.models import User


class GoogleFirstExistingUserSocialAccountAdapter(DefaultSocialAccountAdapter):
    @staticmethod
    def _google_extra_data(sociallogin: SocialLogin):
        extra_data = getattr(sociallogin.account, "extra_data", {}) or {}
        name = (extra_data.get("name") or "").strip()
        picture_url = (extra_data.get("picture") or extra_data.get("avatar_url") or "").strip()
        return name, picture_url

    @classmethod
    def _sync_google_user_fields(cls, user, sociallogin: SocialLogin):
        if getattr(sociallogin.account, "provider", "") != "google":
            return False

        name, picture_url = cls._google_extra_data(sociallogin)
        updated = False

        if name and user.full_name != name:
            user.full_name = name
            updated = True

        if picture_url:
            try:
                with urlopen(picture_url) as response:
                    image_bytes = response.read()
                parsed_url = urlparse(picture_url)
                ext = os.path.splitext(parsed_url.path)[1] or ".jpg"
                file_name = f"google_{uuid.uuid4().hex}{ext}"
                user.profile.save(file_name, ContentFile(image_bytes), save=False)
                updated = True
            except Exception:
                pass

        if updated:
            user.save()

        return updated

    def pre_social_login(self, request, sociallogin: SocialLogin):
        if sociallogin.is_existing:
            return

        email = (sociallogin.user.email or "").strip().lower()
        if not email:
            return

        existing_user = User.objects.filter(email__iexact=email, is_active=True).first()
        if existing_user is None:
            return

        if request.user.is_authenticated:
            if request.user.pk == existing_user.pk:
                return
            sociallogin.connect(request, request.user)
            return

        email_address = EmailAddress.objects.filter(
            user=existing_user,
            email__iexact=email,
        ).first()
        if email_address is None:
            EmailAddress.objects.create(
                user=existing_user,
                email=email,
                verified=True,
                primary=True,
            )

        self._sync_google_user_fields(existing_user, sociallogin)
        sociallogin.connect(request, existing_user)

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form=form)
        self._sync_google_user_fields(user, sociallogin)
        return user
