from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from Qr.models import Invitations, Project
from Qr.models import QRCode, QRScanSetting
from system.models import ConfigCategory, ConfigChoice


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
