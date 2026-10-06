"""Subscription lifecycle and package quota regression tests."""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from analytics.models import QRAnalytics, ScanEvent, Visitor
from Qr.models import QRCode, QRScanSetting
from subscriptions.models import Currency, Duration, Invoice, Package, PackagePlan, PackagePlanPrice, Subscription
from system.models import ConfigCategory, ConfigChoice


class SubscriptionLifecycleTests(TestCase):
    def setUp(self):
        self.currency = Currency.objects.create(code="NPR", name="Nepalese Rupee")
        self.free_package = Package.objects.create(
            title="Free", description="Permanent free tier", is_free=True,
        )
        self.free_plan = PackagePlan.objects.create(
            package=self.free_package, duration=None, max_qrs=2, max_scans=1,
            max_team_members=3, max_bulk_upload=4, max_domain_add=5,
        )
        PackagePlanPrice.objects.create(
            package_plan=self.free_plan, currency=self.currency,
            price=Decimal("0.00"), is_default=True,
        )

    def create_user(self, email="buyer@example.com"):
        return User.objects.create_user(email=email, password="password123", full_name="Buyer")

    def test_new_user_gets_one_permanent_free_subscription_with_plan_limits(self):
        user = self.create_user()
        subscription = Subscription.objects.get(user=user, package_plan=self.free_plan)

        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertIsNone(subscription.expires_at)
        self.assertTrue(subscription.is_active())
        self.assertIsNone(subscription.days_remaining())
        self.assertEqual(subscription.qr_limit, 2)
        self.assertEqual(subscription.scan_limit, 1)
        self.assertEqual(subscription.team_member_limit, 3)
        self.assertEqual(subscription.bulk_upload_limit, 4)
        self.assertEqual(subscription.domain_add_limit, 5)
        self.assertIsNone(subscription.scan_limit_remaining)
        self.assertEqual(Subscription.get_or_create_default_subscription(user).pk, subscription.pk)
        self.assertEqual(Subscription.objects.filter(user=user, package_plan=self.free_plan).count(), 1)

    def test_expired_free_record_stays_expired_and_new_tier_is_active(self):
        user = self.create_user()
        old = Subscription.objects.get(user=user, package_plan=self.free_plan)
        old.expires_at = timezone.now() - timezone.timedelta(days=1)
        old.save(update_fields=["expires_at"])

        current = Subscription.get_usage_subscription_for_user(user)

        old.refresh_from_db()
        self.assertNotEqual(current.pk, old.pk)
        self.assertEqual(old.status, Subscription.Status.EXPIRED)
        self.assertFalse(old.is_active())
        self.assertIsNone(current.expires_at)
        self.assertEqual(Subscription.get_active_subscription_for_user(user).pk, current.pk)

    def test_free_plan_limit_changes_sync_without_new_subscription(self):
        user = self.create_user()
        original = Subscription.objects.get(user=user, package_plan=self.free_plan)
        self.free_plan.max_scans = 6
        self.free_plan.max_qrs = 8
        self.free_plan.save(update_fields=["max_scans", "max_qrs"])

        current = Subscription.get_usage_subscription_for_user(user)

        self.assertEqual(current.pk, original.pk)
        self.assertEqual(current.scan_limit, 6)
        self.assertEqual(current.qr_limit, 8)

    def test_cancelled_free_record_is_not_reactivated(self):
        user = self.create_user()
        old = Subscription.objects.get(user=user, package_plan=self.free_plan)
        old.status = Subscription.Status.CANCELLED
        old.save(update_fields=["status"])

        current = Subscription.get_usage_subscription_for_user(user)

        old.refresh_from_db()
        self.assertEqual(old.status, Subscription.Status.CANCELLED)
        self.assertNotEqual(current.pk, old.pk)
        self.assertEqual(current.status, Subscription.Status.ACTIVE)

    def test_paid_renewal_extends_expiry_and_preserves_usage(self):
        user = self.create_user()
        duration = Duration.objects.create(name="Monthly", days=30)
        paid_package = Package.objects.create(title="Pro", description="Paid tier")
        paid_plan = PackagePlan.objects.create(
            package=paid_package, duration=duration, max_qrs=20, max_scans=100,
        )

        def invoice(subscription=None):
            return Invoice.objects.create(
                user=user, subscription=subscription, package_plan=paid_plan,
                amount=Decimal("100.00"), total=Decimal("100.00"),
                currency=self.currency, due_date=timezone.now() + timezone.timedelta(days=1),
            )

        first = invoice()
        first.mark_as_paid()
        paid = first.subscription
        initial_expiry = paid.expires_at
        paid.scan_limit_remaining = 7  # Legacy counter must not be reset by renewal.
        paid.save(update_fields=["scan_limit_remaining"])

        second = invoice(subscription=paid)
        second.mark_as_paid()
        paid.refresh_from_db()

        self.assertEqual(second.subscription_id, paid.pk)
        self.assertEqual(paid.status, Subscription.Status.ACTIVE)
        self.assertEqual(paid.expires_at, initial_expiry + timezone.timedelta(days=30))
        self.assertEqual(paid.scan_limit_remaining, 7)
        self.assertEqual(Subscription.get_active_subscription_for_user(user).pk, paid.pk)
        self.assertEqual(Subscription.get_usage_subscription_for_user(user).pk, paid.pk)


class PackageScanQuotaTests(TestCase):
    def setUp(self):
        currency = Currency.objects.create(code="NPR", name="Nepalese Rupee")
        package = Package.objects.create(title="Free", description="Free tier", is_free=True)
        self.plan = PackagePlan.objects.create(package=package, max_qrs=1, max_scans=1)
        PackagePlanPrice.objects.create(
            package_plan=self.plan, currency=currency, price=Decimal("0.00"),
        )
        self.user = User.objects.create_user(
            email="scanner@example.com", password="password123", full_name="Scanner",
        )
        category = ConfigCategory.objects.create(name="QR Type", description="QR types")
        qr_type = ConfigChoice.objects.create(category=category, name="Website")
        self.qr = QRCode.objects.create(name="First", qr_type=qr_type, created_by=self.user)
        self.other_qr = QRCode.objects.create(name="Second", qr_type=qr_type, created_by=self.user)
        QRScanSetting.objects.create(qr_code=self.qr, is_scan_limit=True, scan_limit=10)
        self.client = APIClient()

    def test_package_quota_blocks_other_qr_and_does_not_count_rejected_scan(self):
        first = self.client.post(
            f"/api/v1.1/user/qr/{self.qr.short_code}/analytics/", {}, format="json",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(ScanEvent.objects.count(), 1)
        self.assertEqual(QRAnalytics.objects.get(qr=self.qr).total_scans, 1)
        visitor_scans = Visitor.objects.get().total_scans

        blocked = self.client.post(
            f"/api/v1.1/user/qr/{self.other_qr.short_code}/analytics/", {}, format="json",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.data["data"], {
            "limit": 1, "used": 1, "remaining": 0, "requested": 1,
        })
        self.assertEqual(ScanEvent.objects.count(), 1)
        self.assertEqual(Visitor.objects.get().total_scans, visitor_scans)
        self.assertFalse(QRAnalytics.objects.filter(qr=self.other_qr).exists())

        self.client.force_authenticate(self.user)
        for path, body in (
            (f"/api/v1.1/user/qr/{self.other_qr.short_code}/scan/", {}),
            ("/api/v1.1/user/qr/plans/scan/", {"qr_id": self.other_qr.short_code}),
        ):
            with self.subTest(path=path):
                response = self.client.post(path, body, format="json")
                self.assertEqual(response.status_code, 403)

    def test_usage_uses_existing_qrs_and_analytics_and_clamps_remaining(self):
        QRAnalytics.objects.create(qr=self.qr, total_scans=3, unique_scans=2)
        QRAnalytics.objects.create(qr=self.other_qr, total_scans=2, unique_scans=1)
        self.client.force_authenticate(self.user)

        response = self.client.get("/api/v1.1/user/subscriptions/usage/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["qr_usage"]["used"], 2)
        self.assertEqual(response.data["qr_usage"]["remaining"], 0)
        self.assertEqual(response.data["scan_usage"]["used"], 5)
        self.assertEqual(response.data["scan_usage"]["remaining"], 0)
        self.assertEqual(response.data["total_scan_count"], 5)

        self.other_qr.is_deleted = True
        self.other_qr.save(update_fields=["is_deleted"])
        response = self.client.get("/api/v1.1/user/subscriptions/usage/")
        self.assertEqual(response.data["scan_usage"]["used"], 3)

    def test_per_qr_visitor_limit_still_blocks_scans_below_package_quota(self):
        self.plan.max_scans = 5
        self.plan.save(update_fields=["max_scans"])
        QRScanSetting.objects.filter(qr_code=self.qr).update(scan_limit=1)

        path = f"/api/v1.1/user/qr/{self.qr.short_code}/analytics/"
        first = self.client.post(path, {}, format="json", REMOTE_ADDR="127.0.0.1")
        second = self.client.post(path, {}, format="json", REMOTE_ADDR="127.0.0.1")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)  # Existing QR-limit response behavior.
        self.assertEqual(ScanEvent.objects.filter(qr=self.qr).count(), 1)
        self.assertEqual(QRAnalytics.objects.get(qr=self.qr).total_scans, 1)
