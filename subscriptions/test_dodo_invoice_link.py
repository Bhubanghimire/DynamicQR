"""Dodo payment completion must persist the invoice subscription link."""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from subscriptions.models import Currency, Duration, Invoice, Package, PackagePlan, Subscription
from subscriptions.webhooks import handle_payment_succeeded


class DodoInvoiceSubscriptionLinkTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="dodo-buyer@example.com", password="password123", full_name="Dodo Buyer",
        )
        currency = Currency.objects.create(code="NPR", name="Nepalese Rupee")
        duration = Duration.objects.create(name="Monthly", days=30)
        package = Package.objects.create(title="Pro", description="Paid plan")
        plan = PackagePlan.objects.create(package=package, duration=duration)
        self.invoice = Invoice.objects.create(
            user=self.user, package_plan=plan, amount=Decimal("100.00"),
            total=Decimal("100.00"), currency=currency,
            due_date=timezone.now() + timezone.timedelta(days=1),
        )
        self.client = APIClient()

    def test_payment_success_saves_subscription_on_invoice(self):
        event = {
            "payment_id": "pay_invoice_link_test",
            "subscription_id": "sub_invoice_link_test",
            "metadata": {"invoice_number": self.invoice.invoice_number},
        }

        response = self.client.post(
            "/api/webhook/dodo/", {"type": "payment.succeeded", "data": event}, format="json",
        )

        self.invoice.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
        self.assertIsNotNone(self.invoice.subscription_id)
        self.assertEqual(self.invoice.subscription.status, Subscription.Status.ACTIVE)
        self.assertEqual(self.invoice.subscription.dodo_subscription_id, event["subscription_id"])

        original_expiry = self.invoice.subscription.expires_at
        self.client.post("/api/webhook/dodo/", {"type": "payment.succeeded", "data": event}, format="json")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.subscription.expires_at, original_expiry)
        self.assertEqual(Subscription.objects.filter(user=self.user, package_plan=self.invoice.package_plan).count(), 1)

    def test_next_paid_invoice_links_to_existing_subscription(self):
        first_event = {
            "payment_id": "pay_first_invoice",
            "subscription_id": "sub_existing_plan",
            "metadata": {"invoice_number": self.invoice.invoice_number},
        }
        handle_payment_succeeded(first_event)
        self.invoice.refresh_from_db()
        subscription = self.invoice.subscription
        first_expiry = subscription.expires_at

        next_invoice = Invoice.objects.create(
            user=self.user, package_plan=self.invoice.package_plan,
            amount=Decimal("100.00"), total=Decimal("100.00"),
            currency=self.invoice.currency,
            due_date=timezone.now() + timezone.timedelta(days=1),
        )
        next_event = {
            "payment_id": "pay_next_invoice",
            "subscription_id": "sub_existing_plan",
            "metadata": {"invoice_number": next_invoice.invoice_number},
        }

        response = handle_payment_succeeded(next_event)

        next_invoice.refresh_from_db()
        subscription.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(next_invoice.subscription_id, subscription.pk)
        self.assertEqual(subscription.expires_at, first_expiry + timezone.timedelta(days=30))
        self.assertEqual(Subscription.objects.filter(user=self.user, package_plan=self.invoice.package_plan).count(), 1)
