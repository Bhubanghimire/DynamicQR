import base64
import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from subscriptions.models import Duration, Invoice, Package, PackagePlan, Payment, Subscription
from subscriptions.services.esewa_service import _signature


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
