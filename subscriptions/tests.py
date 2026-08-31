from django.test import TestCase
from rest_framework.test import APIClient

from subscriptions.models import Duration, Package, PackagePlan


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
