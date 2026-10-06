"""eSewa ePay V2 form signing and server-side transaction verification."""
import base64
import binascii
import hashlib
import hmac
import json
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings


class EsewaError(Exception):
    pass


def _amount(value):
    try:
        amount = Decimal(str(value).replace(',', '')).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise EsewaError('Invalid eSewa amount') from exc
    return amount


def _signature(fields, names):
    message = ','.join(f'{name}={fields[name]}' for name in names)
    digest = hmac.new(settings.ESEWA_SECRET_KEY.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).digest()
    return base64.b64encode(digest).decode('ascii')


def form_for_invoice(invoice):
    if not settings.ESEWA_PRODUCT_CODE or not settings.ESEWA_SECRET_KEY or not settings.ESEWA_CALLBACK_BASE_URL:
        raise EsewaError('eSewa is not configured')
    amount = str(invoice.total)
    transaction_uuid = invoice.metadata["esewa_transaction_uuid"]
    base = settings.ESEWA_CALLBACK_BASE_URL.rstrip('/')
    fields = {
        'amount': amount,
        'tax_amount': '0',
        'total_amount': amount,
        'transaction_uuid': transaction_uuid,
        'product_code': settings.ESEWA_PRODUCT_CODE,
        'product_service_charge': '0',
        'product_delivery_charge': '0',
        'success_url': f'{base}/api/payment/esewa/success/{invoice.id}/',
        'failure_url': f'{base}/api/payment/esewa/failure/{invoice.id}/',
        'signed_field_names': 'total_amount,transaction_uuid,product_code',
    }
    fields['signature'] = _signature(fields, fields['signed_field_names'].split(','))
    host = 'rc-epay.esewa.com.np' if settings.ESEWA_TEST_MODE else 'epay.esewa.com.np'
    return f'https://{host}/api/epay/main/v2/form', fields


def decode_callback(encoded):
    if not encoded or len(encoded) > 8192:
        raise EsewaError('Missing or oversized eSewa response')
    try:
        payload = json.loads(base64.b64decode(encoded, validate=True))
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise EsewaError('Invalid eSewa response') from exc
    if not isinstance(payload, dict):
        raise EsewaError('Invalid eSewa response')
    names = payload.get('signed_field_names', '').split(',')
    expected = ['transaction_code', 'status', 'total_amount', 'transaction_uuid', 'product_code', 'signed_field_names']
    if names != expected or not all(name in payload for name in names):
        raise EsewaError('Invalid signed fields')
    signature = payload.get('signature', '')
    if not isinstance(signature, str) or not hmac.compare_digest(_signature(payload, names), signature):
        raise EsewaError('Invalid eSewa signature')
    return payload


def verify_status(invoice):
    """Ask eSewa about our stored amount and transaction UUID; never trust browser totals."""
    if not settings.ESEWA_PRODUCT_CODE:
        raise EsewaError('eSewa is not configured')
    host = 'rc.esewa.com.np' if settings.ESEWA_TEST_MODE else 'epay.esewa.com.np'
    transaction_uuid = (invoice.metadata or {}).get("esewa_transaction_uuid")
    if not transaction_uuid:
        raise EsewaError("Missing eSewa transaction UUID")
    query = urlencode({
        'product_code': settings.ESEWA_PRODUCT_CODE,
        'total_amount': str(invoice.total),
        'transaction_uuid': transaction_uuid,
    })
    url = f'https://{host}/api/epay/transaction/status/?{query}'
    try:
        with urlopen(Request(url, headers={'Accept': 'application/json'}), timeout=8) as response:
            data = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise EsewaError('Could not verify payment with eSewa') from exc
    if not isinstance(data, dict) or data.get('status') not in {
        'COMPLETE', 'PENDING', 'CANCELED', 'NOT_FOUND', 'FULL_REFUND', 'PARTIAL_REFUND', 'AMBIGUOUS'
    }:
        raise EsewaError('Unexpected eSewa status response')
    returned_amount = data.get('total_amount', data.get('totalAmount'))
    if returned_amount is None or _amount(returned_amount) != invoice.total:
        raise EsewaError('eSewa amount mismatch')
    returned_code = data.get('product_code', data.get('scd'))
    if returned_code and returned_code != settings.ESEWA_PRODUCT_CODE:
        raise EsewaError('eSewa merchant mismatch')
    returned_uuid = data.get('transaction_uuid', data.get('pid'))
    if returned_uuid and returned_uuid != invoice.metadata['esewa_transaction_uuid']:
        raise EsewaError('eSewa transaction mismatch')
    return data
