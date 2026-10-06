"""Regression coverage for repeat eSewa checkout requests."""

import base64
import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import BillingAddress, User
from subscriptions.models import Currency, Duration, Invoice, Package, PackagePlan, PackagePlanPrice, Payment, PaymentMethod, PaymentProvider
from subscriptions.services.esewa_service import _signature


@override_settings(
    ESEWA_PRODUCT_CODE="EPAYTEST",
    ESEWA_SECRET_KEY="test-secret",
    ESEWA_TEST_MODE=True,
    ESEWA_CALLBACK_BASE_URL="https://api.example.test",
    FRONTEND_URL="https://app.example.test",
)
class EsewaInvoiceIdempotencyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="repeat-buyer@example.com", password="password123", full_name="Repeat Buyer"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.billing_address = BillingAddress.objects.create(
            user=self.user,
            full_name="Repeat Buyer",
            company_name="Example Co",
            address_line_1="123 Main Street",
            address_line_2="Suite 4",
            city="Kathmandu",
            state_province="Bagmati",
            postal_code="44600",
            country="NP",
            phone="9800000000",
        )
        currency = Currency.objects.create(code="NPR", name="Nepalese Rupee")
        duration = Duration.objects.create(name="Monthly", days=30)
        package = Package.objects.create(title="Pro", description="Pro package")
        self.plan = PackagePlan.objects.create(package=package, duration=duration)
        self.price = PackagePlanPrice.objects.create(
            package_plan=self.plan, currency=currency, price=Decimal("100.00")
        )

    def initiate(self):
        return self.client.post(
            "/api/v1.1/user/subscriptions/payments/esewa/initiate/",
            {"package_plan_id": str(self.plan.id), "package_plan_price_id": str(self.price.id)},
            format="json",
        )

    def test_repeat_initiation_reuses_invoice_and_esewa_transaction(self):
        first = self.initiate()
        second = self.initiate()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.data["invoice_id"], second.data["invoice_id"])
        self.assertEqual(first.data["invoice_number"], second.data["invoice_number"])
        self.assertEqual(first.data["transaction_uuid"], second.data["transaction_uuid"])
        self.assertEqual(first.data["form_fields"], second.data["form_fields"])
        self.assertEqual(Invoice.objects.filter(user=self.user).count(), 1)

    def test_checkout_saves_billing_address_snapshot(self):
        first = self.initiate()
        invoice = Invoice.objects.get(pk=first.data["invoice_id"])
        self.assertEqual(invoice.billing_address, {
            "full_name": "Repeat Buyer",
            "company_name": "Example Co",
            "address_line_1": "123 Main Street",
            "address_line_2": "Suite 4",
            "city": "Kathmandu",
            "state_province": "Bagmati",
            "postal_code": "44600",
            "country": "NP",
            "phone": "9800000000",
        })

        self.billing_address.city = "Pokhara"
        self.billing_address.save(update_fields=["city"])
        second = self.initiate()
        invoice.refresh_from_db()
        self.assertEqual(first.data["invoice_id"], second.data["invoice_id"])
        self.assertEqual(invoice.billing_address["city"], "Kathmandu")

    def test_different_plan_price_creates_separate_invoice(self):
        first = self.initiate()
        second_package = Package.objects.create(title="Plus", description="Plus package")
        second_plan = PackagePlan.objects.create(package=second_package, duration=self.plan.duration)
        second_price = PackagePlanPrice.objects.create(
            package_plan=second_plan, currency=self.price.currency, price=Decimal("200.00")
        )
        second = self.client.post(
            "/api/v1.1/user/subscriptions/payments/esewa/initiate/",
            {"package_plan_id": str(second_plan.id), "package_plan_price_id": str(second_price.id)},
            format="json",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.data["invoice_id"], second.data["invoice_id"])
        self.assertEqual(Invoice.objects.filter(user=self.user).count(), 2)

    def test_expired_pending_invoice_is_not_reused(self):
        first = self.initiate()
        Invoice.objects.filter(pk=first.data["invoice_id"]).update(
            due_date=timezone.now() - timezone.timedelta(seconds=1)
        )

        second = self.initiate()

        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.data["invoice_id"], second.data["invoice_id"])

    def test_cancelled_invoice_is_not_reused(self):
        first = self.initiate()
        Invoice.objects.filter(pk=first.data["invoice_id"]).update(status=Invoice.Status.CANCELLED)

        second = self.initiate()

        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.data["invoice_id"], second.data["invoice_id"])

    @patch("subscriptions.views.verify_status")
    def test_repeat_initiation_and_success_return_leave_one_paid_invoice(self, verify_status):
        PaymentProvider.objects.create(code="esewa", name="eSewa", logo="esewa.png")
        saved_card = PaymentMethod.objects.create(
            user=self.user, payment_type=PaymentMethod.PaymentType.CARD,
            dodo_payment_method_id="pm_saved_card", is_default=True,
        )
        first = self.initiate()
        self.initiate()
        Invoice.objects.filter(pk=first.data["invoice_id"]).update(billing_address={})
        verify_status.return_value = {
            "status": "COMPLETE", "total_amount": "100.00", "refId": "ES123"
        }
        fields = {
            "transaction_code": "ES123",
            "status": "COMPLETE",
            "total_amount": "100.00",
            "transaction_uuid": first.data["transaction_uuid"],
            "product_code": "EPAYTEST",
            "signed_field_names": "transaction_code,status,total_amount,transaction_uuid,product_code,signed_field_names",
        }
        fields["signature"] = _signature(fields, fields["signed_field_names"].split(","))
        encoded = base64.b64encode(json.dumps(fields).encode()).decode()
        callback_url = f"/api/payment/esewa/success/{first.data['invoice_id']}/"

        callback_response = self.client.get(callback_url, {"data": encoded})
        self.assertEqual(callback_response.status_code, 302, callback_response.content)
        self.assertEqual(self.client.get(callback_url, {"data": encoded}).status_code, 302)
        invoice = Invoice.objects.get(user=self.user)
        self.assertEqual(invoice.status, Invoice.Status.PAID)
        self.assertEqual(invoice.billing_address["address_line_1"], "123 Main Street")
        self.assertEqual(invoice.payment_method.payment_type, PaymentMethod.PaymentType.ESEWA)
        self.assertEqual(invoice.payment_method.dodo_payment_method_id, None)
        self.assertEqual(PaymentMethod.objects.filter(user=self.user, payment_type="esewa").count(), 1)
        self.assertIsNone(invoice.subscription.payment_method)
        saved_card.refresh_from_db()
        self.assertTrue(saved_card.is_default)
        self.assertEqual(Payment.objects.filter(invoice=invoice).count(), 1)
        self.assertEqual(Invoice.objects.filter(user=self.user).count(), 1)
        detail = self.client.get(f"/api/v1.1/user/subscriptions/invoices/{invoice.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["payment_method"]["payment_type"], "esewa")
