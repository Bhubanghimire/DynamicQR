import tempfile
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from Qr.models import CustomDomain, Invitations, Project, SharePermissions, TemplateDesign
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


class ProjectRoleAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.owner = User.objects.create_user(email="owner@example.com", password="password123")
        self.admin = User.objects.create_user(email="admin@example.com", password="password123")
        self.editor = User.objects.create_user(email="editor@example.com", password="password123")
        self.viewer = User.objects.create_user(email="viewer@example.com", password="password123")
        self.outsider = User.objects.create_user(email="outsider@example.com", password="password123")
        category = ConfigCategory.objects.create(name="sharing_permission")
        self.roles = {
            name: ConfigChoice.objects.create(category=category, name=name, status=True)
            for name in ("Admin", "Edit", "View")
        }
        self.pending = ConfigChoice.objects.create(
            category=ConfigCategory.objects.create(name="invitation_status"),
            name="Pending",
            status=True,
        )
        self.project = Project.objects.create(owner=self.owner, name="Shared project")
        content_type = ContentType.objects.get_for_model(Project)
        for user, name in ((self.admin, "Admin"), (self.editor, "Edit"), (self.viewer, "View")):
            SharePermissions.objects.create(
                user_id=user, content_type=content_type, resource_id=self.project.id, role=self.roles[name]
            )
        qr_type = ConfigChoice.objects.create(
            category=ConfigCategory.objects.create(name="QR Type"), name="Website", status=True
        )
        self.qr = QRCode.objects.create(
            name="Shared QR", qr_type=qr_type, created_by=self.owner, project=self.project
        )

    def test_view_can_read_but_cannot_change_project_or_qr(self):
        self.client.force_authenticate(user=self.viewer)
        project_url = f"/api/v1.1/user/project/{self.project.id}/"
        qr_url = f"/api/v1.1/user/qr/{self.qr.id}/"
        self.assertEqual(self.client.get(project_url).status_code, 200)
        self.assertEqual(self.client.get(qr_url).status_code, 200)
        self.assertEqual(self.client.patch(project_url, {"name": "Changed"}, format="json").status_code, 403)
        self.assertEqual(self.client.patch(qr_url, {"QRCode": {"name": "Changed"}}, format="json").status_code, 403)
        self.assertEqual(
            self.client.post(
                f"/api/v1.1/user/project/{self.project.id}/add-qr/",
                {"qr_id": str(self.qr.id)}, format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1.1/user/qr/design/",
                {"qr_code": str(self.qr.id), "design_data": {}}, format="json",
            ).status_code,
            403,
        )
        self.assertEqual(self.client.delete(qr_url).status_code, 403)
        self.assertEqual(self.client.delete(project_url).status_code, 403)
        create_response = self.client.post(
            "/api/v1.1/user/qr/",
            {"QRCode": {"name": "New QR", "qr_type": str(self.qr.qr_type_id), "project": str(self.project.id)}},
            format="json",
        )
        self.assertEqual(create_response.status_code, 400)
        self.assertIn("You cannot modify QR codes in this project", str(create_response.data))

    def test_edit_can_change_content_but_cannot_delete_or_invite(self):
        self.client.force_authenticate(user=self.editor)
        project_url = f"/api/v1.1/user/project/{self.project.id}/"
        qr_url = f"/api/v1.1/user/qr/{self.qr.id}/"
        self.assertEqual(self.client.patch(project_url, {"name": "Edited"}, format="json").status_code, 200)
        self.assertEqual(self.client.patch(qr_url, {"QRCode": {"name": "Edited"}}, format="json").status_code, 200)
        self.assertEqual(self.client.put(project_url, {"name": "Edited again"}, format="json").status_code, 200)
        self.assertEqual(
            self.client.put(
                qr_url,
                {"QRCode": {"name": "Edited again", "qr_type": str(self.qr.qr_type_id), "project": str(self.project.id)}},
                format="json",
            ).status_code,
            200,
        )
        self.project.refresh_from_db()
        self.qr.refresh_from_db()
        self.assertEqual(self.project.owner_id, self.owner.id)
        self.assertEqual(self.qr.created_by_id, self.owner.id)
        self.assertEqual(self.client.delete(qr_url).status_code, 403)
        self.assertEqual(self.client.delete(project_url).status_code, 403)
        response = self.client.post(
            "/api/v1.1/user/project-invitation/invitations/",
            {"emails": ["new@example.com"], "role": str(self.roles["View"].id), "project_ids": [str(self.project.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_admin_can_invite_and_manage_project(self):
        self.client.force_authenticate(user=self.admin)
        with patch("Qr.normal_user.views.send_project_invitation_email"):
            response = self.client.post(
                "/api/v1.1/user/project-invitation/invitations/",
                {"emails": ["new@example.com"], "role": str(self.roles["View"].id), "project_ids": [str(self.project.id)]},
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.delete(f"/api/v1.1/user/qr/{self.qr.id}/").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/v1.1/user/project/{self.project.id}/").status_code, 200)

    def test_only_admin_can_list_other_senders_project_invitations(self):
        invitation = Invitations.objects.create(
            email="new@example.com",
            content_type=ContentType.objects.get_for_model(Project),
            resource_id=self.project.id,
            role=self.roles["View"],
            token="shared-project-invitation",
            invited_by=self.owner,
            status=self.pending,
            expires_at=timezone.now(),
        )
        url = "/api/v1.1/user/project-invitation/sent-invitations/"
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(self.client.get(url).data["data"][0]["email"], invitation.email)
        self.client.force_authenticate(user=self.viewer)
        self.assertEqual(self.client.get(url).data["data"], [])

    def test_admin_can_list_change_and_remove_project_member(self):
        self.client.force_authenticate(user=self.admin)
        members_url = f"/api/v1.1/user/project/{self.project.id}/members/"
        response = self.client.get(members_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual({member["role"] for member in response.data["data"]}, {"Admin", "Edit", "View"})

        member_url = f"{members_url}{self.viewer.id}/"
        response = self.client.patch(
            member_url,
            {"role": str(self.roles["Edit"].id)},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["role"], "Edit")
        self.assertEqual(
            SharePermissions.objects.get(user_id=self.viewer, resource_id=self.project.id).role,
            self.roles["Edit"],
        )

        response = self.client.delete(member_url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            SharePermissions.objects.filter(
                user_id=self.viewer,
                resource_id=self.project.id,
                is_deleted=False,
            ).exists()
        )

    def test_edit_and_view_cannot_manage_project_members(self):
        members_url = f"/api/v1.1/user/project/{self.project.id}/members/"
        member_url = f"{members_url}{self.viewer.id}/"
        for user in (self.editor, self.viewer):
            self.client.force_authenticate(user=user)
            self.assertEqual(self.client.get(members_url).status_code, 403)
            self.assertEqual(
                self.client.patch(
                    member_url,
                    {"role": str(self.roles["Edit"].id)},
                    format="json",
                ).status_code,
                403,
            )
            self.assertEqual(self.client.delete(member_url).status_code, 403)

    def test_member_role_update_rejects_invalid_role(self):
        unrelated = ConfigChoice.objects.create(
            category=ConfigCategory.objects.create(name="Other Role"),
            name="Admin",
            status=True,
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            f"/api/v1.1/user/project/{self.project.id}/members/{self.viewer.id}/",
            {"role": str(unrelated.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_invitation_rejects_non_role_and_inactive_role(self):
        self.client.force_authenticate(user=self.owner)
        unrelated = ConfigChoice.objects.create(
            category=ConfigCategory.objects.create(name="Other"), name="View", status=True
        )
        payload = {"emails": ["new@example.com"], "project_ids": [str(self.project.id)]}
        for role in (unrelated,):
            response = self.client.post(
                "/api/v1.1/user/project-invitation/invitations/",
                {**payload, "role": str(role.id)}, format="json",
            )
            self.assertEqual(response.status_code, 400)
        self.roles["Admin"].status = False
        self.roles["Admin"].save(update_fields=["status"])
        response = self.client.post(
            "/api/v1.1/user/project-invitation/invitations/",
            {**payload, "role": str(self.roles["Admin"].id)}, format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_outsider_cannot_read_project_or_qr(self):
        self.client.force_authenticate(user=self.outsider)
        self.assertEqual(self.client.get(f"/api/v1.1/user/project/{self.project.id}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1.1/user/qr/{self.qr.id}/").status_code, 404)

    def test_template_access_uses_qr_role_and_public_visibility(self):
        linked_template = TemplateDesign.objects.create(
            design_data={"name": "private"},
            status=True,
            is_public=False,
            qr_code=self.qr,
            created_by=self.owner,
        )
        public_template = TemplateDesign.objects.create(
            design_data={"name": "public"},
            status=True,
            is_public=True,
            created_by=self.owner,
        )
        linked_url = f"/api/v1.1/user/template/{linked_template.id}/"
        public_url = f"/api/v1.1/user/template/{public_template.id}/"

        self.client.force_authenticate(user=self.viewer)
        self.assertEqual(self.client.get(linked_url).status_code, 200)
        self.assertEqual(
            self.client.patch(linked_url, {"design_data": {"name": "changed"}}, format="json").status_code,
            403,
        )

        self.client.force_authenticate(user=self.outsider)
        self.assertEqual(self.client.get(linked_url).status_code, 404)
        self.assertEqual(self.client.get(public_url).status_code, 200)
        self.assertEqual(
            self.client.patch(public_url, {"design_data": {"name": "changed"}}, format="json").status_code,
            403,
        )
        self.assertEqual(self.client.delete(public_url).status_code, 403)

        self.client.force_authenticate(user=self.editor)
        self.assertEqual(
            self.client.patch(linked_url, {"design_data": {"name": "edited"}}, format="json").status_code,
            200,
        )
        self.assertEqual(self.client.delete(linked_url).status_code, 403)

        self.client.force_authenticate(user=self.admin)
        self.assertEqual(self.client.delete(linked_url).status_code, 200)


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

    def test_draft_qr_cannot_be_scanned_publicly(self):
        draft_qr = QRCode.objects.create(
            name="Unpublished QR",
            qr_type=self.qr_type,
            created_by=self.user,
            is_draft=True,
            status=True,
        )

        response = self.client.post(
            f"/api/v1.1/user/qr/{draft_qr.short_code}/scan/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 404)


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
