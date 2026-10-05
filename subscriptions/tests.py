

from accounts.models import OTP, User
import base64
import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from subscriptions.models import Duration, Invoice, Package, PackagePlan, Payment, Subscription
from subscriptions.services.esewa_service import _signature

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

    def test_admin_package_detail_includes_duration_object(self):
        admin = User.objects.create_user(
            email="package-admin@example.com",
            password="password123",
            is_staff=True,
        )
        self.client.force_authenticate(user=admin)

        response = self.client.get(
            f"/api/v1.1/admin/subscriptions/packages/{self.monthly_package.id}/"
        )

        self.assertEqual(response.status_code, 200)
        plan = response.data["plans"][0]
        self.assertEqual(plan["duration"]["id"], str(self.monthly.id))
        self.assertEqual(plan["duration"]["name"], self.monthly.name)
        self.assertEqual(plan["duration"]["days"], self.monthly.days)


class NormalUserPackagePriceTests(TestCase):
    def setUp(self):
        from subscriptions.models import Currency, PackagePlanPrice

        self.client = APIClient()
        self.package = Package.objects.create(
            title="Pro", description="Pro package", is_active=True,
        )
        self.plan = PackagePlan.objects.create(package=self.package, is_active=True)
        usd = Currency.objects.create(code="USD", name="US Dollar", is_active=True)
        npr = Currency.objects.create(code="NPR", name="Nepalese Rupee", is_active=True)
        self.usd_price = PackagePlanPrice.objects.create(
            package_plan=self.plan, currency=usd, price=Decimal("10.00"), is_active=True,
        )
        self.npr_price = PackagePlanPrice.objects.create(
            package_plan=self.plan, currency=npr, price=Decimal("1300.00"), is_active=True,
        )

    def _country_response(self, country_code, path):
        from types import SimpleNamespace

        with patch("subscriptions.normal_user.pricing.GeoParser.get_reader") as reader:
            reader.return_value.city.return_value = SimpleNamespace(
                country=SimpleNamespace(iso_code=country_code)
            )
            return self.client.get(path, HTTP_X_FORWARDED_FOR="1.1.1.1")

    def test_package_list_uses_local_currency_price_object(self):
        response = self._country_response("NP", "/api/v1.1/user/subscriptions/packages/")

        self.assertEqual(response.status_code, 200)
        plan = response.data["data"][0]["plans"][0]
        self.assertNotIn("prices", plan)
        self.assertIsInstance(plan["price"], dict)
        self.assertEqual(plan["price"]["id"], str(self.npr_price.id))
        self.assertEqual(plan["price"]["currency"]["code"], "NPR")

    def test_package_and_plan_detail_fall_back_to_usd(self):
        paths = (
            f"/api/v1.1/user/subscriptions/packages/{self.package.id}/",
            f"/api/v1.1/user/subscriptions/package-plans/{self.plan.id}/",
        )
        for path in paths:
            with self.subTest(path=path):
                response = self._country_response("GB", path)
                self.assertEqual(response.status_code, 200)
                plan = response.data["data"]["plans"][0] if "/packages/" in path else response.data["data"]
                self.assertEqual(plan["price"]["id"], str(self.usd_price.id))
                self.assertNotIn("prices", plan)

    def test_unresolved_ip_and_inactive_local_price_use_usd(self):
        path = f"/api/v1.1/user/subscriptions/package-plans/{self.plan.id}/"
        response = self.client.get(path, REMOTE_ADDR="127.0.0.1")
        self.assertEqual(response.data["data"]["price"]["id"], str(self.usd_price.id))

        self.npr_price.is_active = False
        self.npr_price.save(update_fields=["is_active"])
        response = self._country_response("NP", path)
        self.assertEqual(response.data["data"]["price"]["id"], str(self.usd_price.id))

    def test_admin_plan_detail_still_has_price_list(self):
        admin = User.objects.create_superuser(
            email="price-admin@example.com", password="password123", full_name="Price Admin",
        )
        self.client.force_authenticate(user=admin)
        response = self.client.get(
            f"/api/v1.1/admin/subscriptions/package-plans/{self.plan.id}/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("prices", response.data)
        self.assertIsInstance(response.data["prices"], list)
        self.assertEqual(len(response.data["prices"]), 2)


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
            max_bulk_upload=10,
            max_domain_add=2,
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
        self.assertEqual(response.data["bulk_upload_limit"], self.free_plan.max_bulk_upload)
        self.assertEqual(response.data["domain_add_limit"], self.free_plan.max_domain_add)
        self.assertEqual(response.data["domain_add_usage"]["limit"], self.free_plan.max_domain_add)
        self.assertEqual(response.data["domain_add_usage"]["used"], 0)
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
            max_bulk_upload=10,
            max_domain_add=1,
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
        self.assertEqual(subscription.bulk_upload_limit, self.free_plan.max_bulk_upload)
        self.assertEqual(subscription.domain_add_limit, self.free_plan.max_domain_add)
        self.assertEqual(response.data["message"], "loggedIn successfully.")




@override_settings(
    ESEWA_PRODUCT_CODE='EPAYTEST', ESEWA_SECRET_KEY='test-secret',
    ESEWA_TEST_MODE=True, ESEWA_CALLBACK_BASE_URL='https://api.example.test',
    FRONTEND_URL='https://app.example.test',
)
class EsewaCheckoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='buyer@example.com', password='password123', full_name='Buyer', phone='9800000000'
        )
        self.other = User.objects.create_user(
            email='other@example.com', password='password123', full_name='Other', phone='9800000001'
        )
        duration = Duration.objects.create(name='Monthly', days=30)
        package = Package.objects.create(title='Pro', description='Pro package')
        self.plan = PackagePlan.objects.create(package=package, duration=duration, price=Decimal('100.00'), currency='NPR')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.base = '/api/v1.1/user/subscriptions/payments/'

    def initiate(self):
        return self.client.post(self.base + 'esewa/initiate/', {'package_plan_id': str(self.plan.id)}, format='json')

    def test_checkout_uses_saved_price_and_signed_form(self):
        response = self.initiate()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['amount'], '100.00')
        fields = response.data['form_fields']
        self.assertEqual(fields['total_amount'], '100.00')
        self.assertEqual(fields['signature'], _signature(fields, fields['signed_field_names'].split(',')))
        invoice = Invoice.objects.get(invoice_number=response.data['invoice_number'])
        self.assertEqual(invoice.status, Invoice.Status.PENDING)
        self.assertEqual(invoice.metadata['esewa_transaction_uuid'], fields['transaction_uuid'])
        self.assertFalse(Payment.objects.filter(invoice=invoice).exists())

    def test_rejects_non_npr_plan_and_auto_renew(self):
        self.plan.currency = 'USD'
        self.plan.save()
        self.assertEqual(self.initiate().status_code, 400)
        self.plan.currency = 'NPR'
        self.plan.save()
        self.assertEqual(self.client.post(
            self.base + 'esewa/initiate/',
            {'package_plan_id': str(self.plan.id), 'auto_renew': True}, format='json'
        ).status_code, 400)

    @patch('subscriptions.esewa_views.verify_status')
    def test_signed_return_creates_existing_payment_and_paid_invoice_once(self, verify_status):
        response = self.initiate()
        invoice_number = response.data['invoice_number']
        invoice = Invoice.objects.get(invoice_number=invoice_number)
        transaction_uuid = invoice.metadata['esewa_transaction_uuid']
        verify_status.return_value = {'status': 'COMPLETE', 'total_amount': '100.00', 'refId': 'ABC123'}
        fields = {
            'transaction_code': 'ABC123', 'status': 'COMPLETE', 'total_amount': '100.00',
            'transaction_uuid': transaction_uuid, 'product_code': 'EPAYTEST',
            'signed_field_names': 'transaction_code,status,total_amount,transaction_uuid,product_code,signed_field_names',
        }
        fields['signature'] = _signature(fields, fields['signed_field_names'].split(','))
        encoded = base64.b64encode(json.dumps(fields).encode()).decode()
        callback_url = f'/api/payment/esewa/success/{invoice.id}/'
        self.assertEqual(self.client.get(callback_url, {'data': encoded}).status_code, 302)
        self.assertEqual(self.client.get(callback_url, {'data': encoded}).status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.PAID)
        self.assertEqual(Subscription.objects.filter(user=self.user, package_plan=self.plan).count(), 1)
        self.assertFalse(invoice.subscription.auto_renew)
        self.assertEqual(invoice.subscription.billing_duration_days, 30)
        payment = Payment.objects.get(invoice=invoice)
        self.assertEqual(payment.provider, Payment.Provider.ESEWA)
        self.assertEqual(payment.subscription_id, invoice.subscription_id)
        self.assertEqual(payment.amount, invoice.total)
        self.assertEqual(payment.metadata['esewa_transaction_code'], 'ABC123')
        detail = self.client.get(f'/api/v1.1/user/subscriptions/invoices/{invoice.id}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['payment_provider'], 'esewa')
        self.assertEqual(detail.data['payment_reference'], 'ABC123')
        paid_list = self.client.get('/api/v1.1/user/subscriptions/invoices/', {'status': 'paid'})
        self.assertEqual(paid_list.status_code, 200)
        self.assertEqual(paid_list.data['total'], 1)

    @patch('subscriptions.esewa_views.verify_status')
    def test_tampered_return_never_fulfills_and_status_is_owner_only(self, verify_status):
        response = self.initiate()
        invoice_number = response.data['invoice_number']
        invoice = Invoice.objects.get(invoice_number=invoice_number)
        payload = {
            'transaction_code': 'ABC123', 'status': 'COMPLETE', 'total_amount': '1.00',
            'transaction_uuid': invoice.metadata['esewa_transaction_uuid'], 'product_code': 'EPAYTEST',
            'signed_field_names': 'transaction_code,status,total_amount,transaction_uuid,product_code,signed_field_names',
            'signature': 'bad',
        }
        encoded = base64.b64encode(json.dumps(payload).encode()).decode()
        self.assertEqual(self.client.get(f'/api/payment/esewa/success/{invoice.id}/', {'data': encoded}).status_code, 400)
        self.assertFalse(verify_status.called)
        self.client.force_authenticate(self.other)
        status = self.client.get(self.base + 'esewa/status/', {'invoice_number': invoice_number})
        self.assertEqual(status.status_code, 404)
