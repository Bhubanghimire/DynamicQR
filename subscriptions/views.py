from django.shortcuts import render

# Create your views here.
"""Public eSewa browser returns and invoice reconciliation."""
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.views.decorators.http import require_GET

from subscriptions.models import Invoice, Payment, PaymentProvider
from subscriptions.services.esewa_service import EsewaError, decode_callback, verify_status

logger = logging.getLogger(__name__)


def _money(value):
    try:
        return Decimal(str(value).replace(',', '')).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise EsewaError('Invalid eSewa amount') from exc


def reconcile_esewa_invoice(invoice, callback=None):
    """Verify with eSewa and record a paid invoice and payment exactly once."""
    metadata = invoice.metadata or {}
    transaction_uuid = metadata.get('esewa_transaction_uuid')
    if metadata.get('payment_provider') != 'esewa' or not transaction_uuid:
        raise EsewaError('Not an eSewa invoice')
    if invoice.status == Invoice.Status.PAID:
        return invoice
    if callback:
        if callback.get('transaction_uuid') != transaction_uuid:
            raise EsewaError('eSewa transaction mismatch')
        if callback.get('product_code') != settings.ESEWA_PRODUCT_CODE:
            raise EsewaError('eSewa merchant mismatch')
        if _money(callback.get('total_amount')) != invoice.total:
            raise EsewaError('eSewa amount mismatch')
        if callback.get('status') != 'COMPLETE':
            raise EsewaError('Payment is not complete')

    verified = verify_status(invoice)
    status = verified['status']
    if status == 'COMPLETE':
        code = verified.get('ref_id') or verified.get('refId')
        if callback:
            callback_code = callback.get('transaction_code')
            if code and callback_code != code:
                raise EsewaError('eSewa reference mismatch')
            code = code or callback_code
        if not code:
            raise EsewaError('eSewa confirmation has no transaction code')
        with transaction.atomic():
            locked = Invoice.objects.select_for_update().select_related('package_plan').get(pk=invoice.pk)
            current = locked.metadata or {}
            if current.get('payment_provider') != 'esewa' or current.get('esewa_transaction_uuid') != transaction_uuid:
                raise EsewaError('Invoice transaction mismatch')
            if locked.status == Invoice.Status.PAID:
                return locked
            if locked.currency.code.upper() != 'NPR' or locked.total != invoice.total:
                raise EsewaError('Invoice amount mismatch')
            current['esewa_transaction_code'] = str(code)
            current['esewa_payment_status'] = 'success'
            locked.metadata = current
            locked.save(update_fields=['metadata', 'updated_at'])
            locked.mark_as_paid()
            if locked.subscription and not locked.subscription.auto_renew:
                locked.subscription.next_billing_date = None
                locked.subscription.save(update_fields=['next_billing_date', 'updated_at'])

            esewa_provider = PaymentProvider.objects.get(
                code="esewa",
                is_active=True,
            )

            Payment.objects.create(
                user=locked.user,
                subscription=locked.subscription,
                invoice=locked,
                amount=locked.total,
                currency=locked.currency,
                provider=esewa_provider,
                transaction_id=f'esewa:{transaction_uuid}',
                payment_type=Payment.PaymentType.INITIAL,
                status=Payment.Status.SUCCESS,
                paid_at=locked.paid_at,
                metadata={'esewa_transaction_code': str(code)},
            )
            return locked
    if status in {'CANCELED', 'NOT_FOUND'}:
        with transaction.atomic():
            locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
            if locked.status != Invoice.Status.PAID:
                current = locked.metadata or {}
                current['esewa_payment_status'] = 'cancelled'
                locked.metadata = current
                locked.status = Invoice.Status.CANCELLED
                locked.save(update_fields=['metadata', 'status', 'updated_at'])
            return locked
    return invoice


def _frontend_return(invoice):
    base = (settings.FRONTEND_URL or '').rstrip('/')
    if not base:
        return HttpResponseBadRequest('Frontend URL is not configured')
    outcome = 'success' if invoice.status == Invoice.Status.PAID else (
        'failed' if invoice.status == Invoice.Status.CANCELLED else 'pending'
    )
    query = urlencode({'invoice': invoice.invoice_number, 'provider': 'esewa', 'payment': outcome})
    return HttpResponseRedirect(f'{base}/billings/{invoice.id}/?{query}')


@require_GET
def esewa_success(request, invoice_id):
    try:
        callback = decode_callback(request.GET.get('data'))
        invoice = Invoice.objects.get(pk=invoice_id, metadata__payment_provider='esewa')
        if callback.get('transaction_uuid') != (invoice.metadata or {}).get('esewa_transaction_uuid'):
            return HttpResponseBadRequest('Invalid eSewa transaction')
        try:
            reconcile_esewa_invoice(invoice, callback)
        except EsewaError as exc:
            logger.warning('eSewa return could not be reconciled: %s', exc)
        invoice.refresh_from_db()
    except (EsewaError, Invoice.DoesNotExist, KeyError):
        return HttpResponseBadRequest('Invalid eSewa response')
    return _frontend_return(invoice)


@require_GET
def esewa_failure(request, invoice_id):
    invoice = Invoice.objects.filter(pk=invoice_id, metadata__payment_provider='esewa').first()
    if not invoice:
        return HttpResponseBadRequest('Unknown eSewa invoice')
    try:
        reconcile_esewa_invoice(invoice)
    except EsewaError as exc:
        logger.warning('eSewa failure return could not be reconciled: %s', exc)
    invoice.refresh_from_db()
    return _frontend_return(invoice)
