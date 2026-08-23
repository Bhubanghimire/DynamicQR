from allauth.account.models import EmailAddress
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialLogin

from accounts.models import User


class GoogleFirstExistingUserSocialAccountAdapter(DefaultSocialAccountAdapter):
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

        sociallogin.connect(request, existing_user)
