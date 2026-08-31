from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import OTP, User
from subscriptions.models import Duration, Package, PackagePlan, Subscription


class PackageListDurationFilterTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.monthly = Duration.objects.create(name="Monthly", days=30)
        self.yearly = Duration.objects.create(name="Yearly", days=365)

        self.monthly_package = Package.objects.create(
            title="Monthly Pack",
            description="Package with monthly plan",
            is_active=True,
            display_order=1,
        )
        self.yearly_package = Package.objects.create(
            title="Yearly Pack",
            description="Package with yearly plan",
            is_active=True,
            display_order=2,
        )

        PackagePlan.objects.create(
            package=self.monthly_package,
            duration=self.monthly,
            price=10,
            currency="USD",
            is_active=True,
        )
        PackagePlan.objects.create(
            package=self.yearly_package,
            duration=self.yearly,
            price=100,
            currency="USD",
            is_active=True,
        )

    def test_package_list_can_filter_by_duration_uuid(self):
        response = self.client.get("/api/v1.1/user/subscriptions/packages/", {"duration": str(self.monthly.id)})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(len(response.data["data"]), 1)
        self.assertEqual(response.data["data"][0]["title"], self.monthly_package.title)


class SubscriptionUsageFallbackTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.free_package = Package.objects.create(
            title="Free",
            description="Default free package",
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
            is_active=True,
        )

        self.user = User.objects.create_user(
            email="usage@example.com",
            password="password123",
            full_name="Usage User",
            phone="9800000000",
        )
        self.client.force_authenticate(user=self.user)

    def test_usage_endpoint_creates_default_free_subscription(self):
        response = self.client.get("/api/v1.1/user/subscriptions/usage/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["subscription_status"], Subscription.Status.ACTIVE)
        self.assertEqual(response.data["package_title"], self.free_package.title)
        self.assertEqual(response.data["qr_usage"]["limit"], self.free_plan.max_qrs)
        self.assertEqual(response.data["scan_usage"]["limit"], self.free_plan.max_scans)
        self.assertEqual(response.data["qr_usage"]["used"], 0)
        self.assertEqual(response.data["scan_usage"]["used"], 0)
        self.assertTrue(
            Subscription.objects.filter(user=self.user, package_plan=self.free_plan, status=Subscription.Status.ACTIVE).exists()
        )


class RegisterFreeSubscriptionTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.free_package = Package.objects.create(
            title="Free",
            description="Default free package",
            is_free=True,
            is_active=True,
            display_order=0,
        )
        self.free_plan = PackagePlan.objects.create(
            package=self.free_package,
            duration=None,
            price=0,
            currency="USD",
            max_qrs=10,
            max_scans=50,
            max_team_members=0,
            is_active=True,
        )

    def test_register_assigns_default_free_subscription(self):
        OTP.objects.create(email="new@example.com", otp="123456")

        response = self.client.post(
            "/api/v1.1/user/accounts/auth/register/",
            {
                "email": "new@example.com",
                "otp": "123456",
                "password": "password123",
                "full_name": "New User",
                "phone": "9800000001",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        user = User.objects.get(email="new@example.com")
        subscription = Subscription.objects.get(user=user, package_plan=self.free_plan)
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertEqual(subscription.price, 0)
        self.assertEqual(response.data["message"], "loggedIn successfully.")
