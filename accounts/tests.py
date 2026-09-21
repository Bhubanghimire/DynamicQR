from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import Client, SimpleTestCase, TestCase
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


class AdminSwaggerQueryParameterTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        response = Client().get("/api/admin/schema/")
        assert response.status_code == 200
        cls.paths = response.json()["paths"]

    def parameters_for(self, path):
        return {
            parameter["name"]: parameter
            for parameter in self.paths[path]["get"].get("parameters", [])
        }

    def test_admin_model_lists_document_their_supported_filters(self):
        user_parameters = self.parameters_for("/api/v1.1/admin/accounts/users/")
        self.assertEqual(
            user_parameters["status"]["schema"]["enum"],
            ["active", "expired", "cancelled", "pending", "failed", "grace_period"],
        )
        self.assertIn("plan", user_parameters)

        domain_parameters = self.parameters_for("/api/v1.1/admin/projects/domains/")
        self.assertIn("search", domain_parameters)
        self.assertEqual(domain_parameters["user_id"]["schema"]["format"], "uuid")
        self.assertEqual(domain_parameters["is_default"]["schema"]["enum"], ["true", "false"])

        invoice_parameters = self.parameters_for("/api/v1.1/admin/subscriptions/invoices/")
        self.assertEqual(
            invoice_parameters["status"]["schema"]["enum"],
            ["draft", "pending", "paid", "overdue", "cancelled", "refunded"],
        )
        self.assertEqual(invoice_parameters["user_id"]["schema"]["format"], "uuid")

        invoice_status_count_parameters = self.parameters_for(
            "/api/v1.1/admin/subscriptions/invoices/status-counts/"
        )
        self.assertEqual(invoice_status_count_parameters["user_id"]["schema"]["format"], "uuid")

    def test_analytics_parameters_are_specific_to_each_list_action(self):
        top_users = self.parameters_for("/api/v1.1/admin/analytics/dashboard/top-power-users/")
        self.assertIn("search", top_users)
        self.assertIn("user_id", top_users)
        self.assertNotIn("period", top_users)

        qr_trend = self.parameters_for("/api/v1.1/admin/analytics/dashboard/qr-generation-trend/")
        self.assertTrue(qr_trend["period"]["required"])
        self.assertIn("qr_type", qr_trend)
        self.assertIn("qr_status", qr_trend)

        plan_metrics = self.parameters_for("/api/v1.1/admin/analytics/dashboard/plan-metrics/")
        self.assertIn("subscription_status", plan_metrics)
        self.assertIn("is_bot", plan_metrics)

    def test_system_search_is_only_shown_where_it_is_applied(self):
        categories = self.parameters_for("/api/v1.1/admin/system/config-categories/")
        choices = self.parameters_for("/api/v1.1/admin/system/config-categories/{id}/choices/")
        category_detail = self.parameters_for("/api/v1.1/admin/system/config-categories/{id}/")

        self.assertIn("search", categories)
        self.assertIn("search", choices)
        self.assertNotIn("search", category_detail)
