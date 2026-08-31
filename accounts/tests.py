from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase

from accounts.adapters import GoogleFirstExistingUserSocialAccountAdapter
from accounts.models import User


class GoogleSocialSyncTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="google@example.com",
            password="password123",
            full_name="Old Name",
            phone="9800000000",
        )

    def test_google_login_syncs_name_and_profile_image(self):
        sociallogin = SimpleNamespace(
            account=SimpleNamespace(
                provider="google",
                extra_data={
                    "name": "Google User",
                    "picture": "https://example.com/avatar.jpg",
                },
            )
        )
        mock_response = MagicMock()
        mock_response.__enter__.return_value.read.return_value = b"fake-image-bytes"

        with patch("accounts.adapters.urlopen", return_value=mock_response):
            updated = GoogleFirstExistingUserSocialAccountAdapter._sync_google_user_fields(self.user, sociallogin)

        self.user.refresh_from_db()
        self.assertTrue(updated)
        self.assertEqual(self.user.full_name, "Google User")
        self.assertTrue(bool(self.user.profile))

    def test_non_google_social_login_does_not_change_user(self):
        sociallogin = SimpleNamespace(
            account=SimpleNamespace(
                provider="facebook",
                extra_data={"name": "Facebook User", "picture": "https://example.com/avatar.jpg"},
            )
        )

        with patch("accounts.adapters.urlopen") as mocked_urlopen:
            updated = GoogleFirstExistingUserSocialAccountAdapter._sync_google_user_fields(self.user, sociallogin)

        self.user.refresh_from_db()
        self.assertFalse(updated)
        self.assertEqual(self.user.full_name, "Old Name")
        self.assertFalse(mocked_urlopen.called)
