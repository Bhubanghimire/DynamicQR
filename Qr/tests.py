import tempfile
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Qr.models import CustomDomain, Invitations, Project
from Qr.models import QRCode, QRScanSetting
from subscriptions.models import Package, PackagePlan, Subscription
from system.models import ConfigCategory, ConfigChoice
from Qr.services.domain_verification import DomainVerificationService


class DomainVerificationFlowTests(SimpleTestCase):
    @override_settings(CUSTOM_DOMAIN_CNAME_TARGET="customdomain.qrpac.com")
    def test_expected_cname_uses_custom_domain_gateway(self):
        service = DomainVerificationService()

        self.assertEqual(service.expected_cname, "customdomain.qrpac.com")

    @override_settings(CUSTOM_DOMAIN_CNAME_TARGET="http://customdomain.qrpac.com/")
    def test_expected_cname_strips_protocol_and_path(self):
        service = DomainVerificationService()

        self.assertEqual(service.expected_cname, "customdomain.qrpac.com")

    @override_settings(CUSTOM_DOMAIN_CNAME_TARGET="customdomain.qrpac.com")
    def test_cname_verification_does_not_require_existing_http_site(self):
        service = DomainVerificationService()
        domain = type(
            "DomainStub",
            (),
            {
                "domain": "brand.example.com",
                "status": None,
                "verification_attempts": 0,
                "last_verification_attempt": None,
                "verified_at": None,
                "save": lambda self: None,
            },
        )()

        with patch.object(service, "verify_cname_record", return_value=True) as verify_cname:
            with patch.object(service, "verify_http") as verify_http:
                result = service.verify_domain(domain)

        self.assertTrue(result["success"])
        self.assertEqual(result["method"], "cname")
        self.assertEqual(domain.status, CustomDomain.Status.VERIFIED)
        verify_cname.assert_called_once_with("brand.example.com")
        verify_http.assert_not_called()

    def test_acme_probe_confirms_public_challenge_file(self):
        service = DomainVerificationService()
        response = Mock(status_code=200)

        def fake_get(url, timeout):
            token = url.rsplit("/", 1)[-1]
            response.text = f"ok-{token}"
            return response

        with tempfile.TemporaryDirectory() as webroot:
            with patch("Qr.services.domain_verification.requests.get", side_effect=fake_get) as get:
                result = service.verify_acme_challenge_path("brand.example.com", webroot)

        self.assertTrue(result["success"])
        self.assertIn("http://brand.example.com/.well-known/acme-challenge/", result["url"])
        get.assert_called_once()

    def test_acme_probe_reports_unreachable_challenge_file(self):
        service = DomainVerificationService()
        response = Mock(status_code=404, text="not found")

        with tempfile.TemporaryDirectory() as webroot:
            with patch("Qr.services.domain_verification.requests.get", return_value=response):
                result = service.verify_acme_challenge_path("brand.example.com", webroot)

        self.assertFalse(result["success"])
        self.assertEqual(result["status_code"], 404)
        self.assertIn("ACME challenge file was not reachable", result["error"])

    def test_activation_stops_before_certbot_when_acme_probe_fails(self):
        service = DomainVerificationService()
        domain = type(
            "DomainStub",
            (),
            {
                "domain": "brand.example.com",
                "status": None,
                "verification_attempts": 0,
                "last_verification_attempt": None,
                "verified_at": None,
                "dns_verified_at": None,
                "automation_error": None,
                "save": lambda self: None,
            },
        )()

        with patch.object(service, "verify_domain", return_value={"success": True}):
            with patch("Qr.services.domain_verification.NginxConfigService") as nginx:
                nginx_service = nginx.return_value
                nginx_service.write_config.return_value = {"success": True}
                nginx_service.enable_site.return_value = {"success": True}
                nginx.full_nginx_reload.return_value = {"success": True}
                with patch.object(
                    service,
                    "verify_acme_challenge_path",
                    return_value={
                        "success": False,
                        "error": "challenge unreachable",
                        "url": "http://brand.example.com/.well-known/acme-challenge/check",
                        "status_code": 404,
                    },
                ):
                    with patch("Qr.services.domain_verification.SSLProvisioningService") as ssl:
                        result = service.verify_and_activate_domain(domain)

        self.assertFalse(result["success"])
        self.assertEqual(result["step"], "acme_challenge")
        self.assertEqual(domain.status, CustomDomain.Status.SSL_PENDING)
        self.assertEqual(domain.automation_error, "challenge unreachable")
        ssl.assert_not_called()


class ProjectInvitationReceiverListTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        User = get_user_model()
        self.sender = User.objects.create_user(
            email="sender@example.com",
            password="password123",
            full_name="Sender User",
            phone="1111111111",
        )
        self.receiver = User.objects.create_user(
            email="receiver@example.com",
            password="password123",
            full_name="Receiver User",
            phone="2222222222",
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="password123",
            full_name="Other User",
            phone="3333333333",
        )

        self.role_category = ConfigCategory.objects.create(
            name="Project Role",
            description="Project role category",
        )
        self.status_category = ConfigCategory.objects.create(
            name="Invitation Status",
            description="Invitation status category",
        )

        self.role = ConfigChoice.objects.create(
            category=self.role_category,
            name="Edit",
            status=True,
        )
        self.pending_status = ConfigChoice.objects.create(
            category=self.status_category,
            name="Pending",
            status=True,
        )

        self.project = Project.objects.create(
            owner=self.sender,
            name="Receiver Project",
            description="Project for invitation testing",
            status=True,
        )
        self.other_project = Project.objects.create(
            owner=self.sender,
            name="Other Project",
            description="Other project",
            status=True,
        )

        self.receiver_invitation = Invitations.objects.create(
            email=self.receiver.email,
            content_type=ContentType.objects.get_for_model(Project),
            resource_id=self.project.id,
            role=self.role,
            token="token-1",
            invited_by=self.sender,
            status=self.pending_status,
            expires_at=timezone.now(),
        )
        self.other_invitation = Invitations.objects.create(
            email="someoneelse@example.com",
            content_type=self.receiver_invitation.content_type,
            resource_id=self.other_project.id,
            role=self.role,
            token="token-2",
            invited_by=self.sender,
            status=self.pending_status,
            expires_at=timezone.now(),
        )

    def test_receiver_can_list_their_invitations(self):
        self.client.force_authenticate(user=self.receiver)

        response = self.client.get("/api/v1.1/user/project-invitation/my-invitations/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["message"], "User invitations fetched successfully.")
        self.assertTrue(response.data["data"])
        self.assertEqual(len(response.data["data"]), 1)

        invitation = response.data["data"][0]
        self.assertEqual(invitation["email"], self.receiver.email)
        self.assertEqual(invitation["project_id"], str(self.project.id))
        self.assertEqual(invitation["project_name"], self.project.name)
        self.assertEqual(invitation["invited_by_name"], self.sender.full_name)
        self.assertEqual(invitation["invited_by_email"], self.sender.email)
        self.assertEqual(invitation["role_name"], self.role.name)
        self.assertEqual(str(invitation["status"]), str(self.pending_status.id))
        self.assertIn("created_at", invitation)

    def test_unauthenticated_user_is_rejected(self):
        response = self.client.get("/api/v1.1/user/project-invitation/my-invitations/")

        self.assertEqual(response.status_code, 401)


class QRCodeListTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        User = get_user_model()
        self.user = User.objects.create_user(
            email="qr-user@example.com",
            password="password123",
            full_name="QR User",
            phone="4444444444",
        )

        self.qr_category = ConfigCategory.objects.create(
            name="QR Type",
            description="QR type category",
        )
        self.qr_type = ConfigChoice.objects.create(
            category=self.qr_category,
            name="Website",
            status=True,
        )

        self.qr_code = QRCode.objects.create(
            name="List QR",
            qr_type=self.qr_type,
            created_by=self.user,
            status=True,
        )
        QRScanSetting.objects.create(
            qr_code=self.qr_code,
            domain="https://example.com",
        )

    def test_qr_list_includes_domain_name(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get("/api/v1.1/user/qr/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"])
        self.assertEqual(response.data["data"][0]["domain_name"], "https://example.com")

    def test_qr_list_excludes_drafts(self):
        draft_qr = QRCode.objects.create(
            name="Draft QR",
            qr_type=self.qr_type,
            created_by=self.user,
            is_draft=True,
            status=True,
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.get("/api/v1.1/user/qr/")

        self.assertEqual(response.status_code, 200)
        qr_ids = {qr["id"] for qr in response.data["data"]}
        self.assertNotIn(str(draft_qr.id), qr_ids)
        self.assertIn(str(self.qr_code.id), qr_ids)

    def test_draft_qr_can_be_updated(self):
        draft_qr = QRCode.objects.create(
            name="Unsaved QR",
            qr_type=self.qr_type,
            created_by=self.user,
            is_draft=True,
            status=True,
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            f"/api/v1.1/user/qr/{draft_qr.id}/",
            {"QRCode": {"name": "Saved draft"}},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        draft_qr.refresh_from_db()
        self.assertEqual(draft_qr.name, "Saved draft")


class QRAnalyticsDetailSummaryTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        User = get_user_model()
        self.user = User.objects.create_user(
            email="analytics-user@example.com",
            password="password123",
            full_name="Analytics User",
            phone="6666666666",
        )

        self.project = Project.objects.create(
            owner=self.user,
            name="Analytics Project",
            description="Project for analytics testing",
            status=True,
        )

        self.qr_category = ConfigCategory.objects.create(
            name="QR Type",
            description="QR type category",
        )
        self.qr_type = ConfigChoice.objects.create(
            category=self.qr_category,
            name="Website",
            status=True,
        )

        self.qr_code = QRCode.objects.create(
            name="Analytics QR",
            qr_type=self.qr_type,
            created_by=self.user,
            project=self.project,
            status=True,
        )

    def test_detail_summary_returns_project_object(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            f"/api/v1.1/user/analytics/details/detail_summary/?qr_id={self.qr_code.id}&period=today"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["message"], "Analytics summary fetched successfully.")
        self.assertEqual(response.data["data"]["qr"]["project"]["id"], str(self.project.id))
        self.assertEqual(response.data["data"]["qr"]["project"]["name"], self.project.name)


class CustomDomainLimitTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        User = get_user_model()
        self.user = User.objects.create_user(
            email="domain-limit@example.com",
            password="password123",
            full_name="Domain Limit User",
            phone="5555555555",
        )
        self.free_package = Package.objects.create(
            title="No Domains",
            description="Package without custom domains",
            is_free=True,
            is_active=True,
            display_order=0,
        )
        self.free_plan = PackagePlan.objects.create(
            package=self.free_package,
            duration=None,
            price=0,
            currency="USD",
            max_qrs=5,
            max_scans=25,
            max_team_members=0,
            max_bulk_upload=10,
            max_domain_add=0,
            is_active=True,
        )
        Subscription.get_or_create_default_subscription(self.user)

    def test_domain_create_respects_package_limit(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            "/api/v1.1/user/domains/",
            {"domain": "example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["message"], "Custom domain limit reached for your package.")
        self.assertEqual(response.data["data"]["limit"], 0)


class CustomDomainDeleteTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        User = get_user_model()
        self.user = User.objects.create_user(
            email="domain-delete@example.com",
            password="password123",
            full_name="Domain Delete User",
            phone="5555555556",
        )

    def test_delete_domain_cleans_assets_and_removes_database_row(self):
        domain = CustomDomain.objects.create(
            user=self.user,
            domain="delete.example.com",
            status=CustomDomain.Status.ACTIVE,
            nginx_enabled=True,
            ssl_verified=True,
        )
        self.client.force_authenticate(user=self.user)

        with patch("Qr.normal_user.views.DomainVerificationService.cleanup_domain_assets") as cleanup:
            cleanup.return_value = {
                "success": True,
                "errors": [],
                "nginx": {"success": True},
                "ssl": {"success": True},
            }

            response = self.client.delete(f"/api/v1.1/user/domains/{domain.id}/")

        self.assertEqual(response.status_code, 204)
        cleanup.assert_called_once()
        self.assertFalse(CustomDomain._base_manager.filter(id=domain.id).exists())

    def test_delete_domain_preserves_row_when_cleanup_fails(self):
        domain = CustomDomain.objects.create(
            user=self.user,
            domain="cleanup-fails.example.com",
            status=CustomDomain.Status.ACTIVE,
            nginx_enabled=True,
            ssl_verified=True,
        )
        self.client.force_authenticate(user=self.user)

        with patch("Qr.normal_user.views.DomainVerificationService.cleanup_domain_assets") as cleanup:
            cleanup.return_value = {
                "success": False,
                "errors": ["SSL cleanup failed"],
                "nginx": {"success": True},
                "ssl": {"success": False},
            }

            response = self.client.delete(f"/api/v1.1/user/domains/{domain.id}/")

        self.assertEqual(response.status_code, 400)
        domain.refresh_from_db()
        self.assertFalse(domain.is_deleted)
        self.assertEqual(domain.automation_error, "SSL cleanup failed")
