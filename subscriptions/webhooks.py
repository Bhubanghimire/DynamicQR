# webhooks.py - COMPLETE FIXED VERSION

import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.utils import timezone
from dodopayments import DodoPayments
from rest_framework.decorators import api_view, schema, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.schemas.openapi import AutoSchema

from .models import Invoice, PaymentMethod, Subscription

logger = logging.getLogger(__name__)
# webhooks.py - Updated with improvements

import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.utils import timezone
from dodopayments import DodoPayments
from rest_framework.decorators import api_view, schema, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.schemas.openapi import AutoSchema

from .models import Invoice, PaymentMethod, Subscription, PaymentWebhook

logger = logging.getLogger(__name__)


def _get_dodo_client():
    return DodoPayments(
        bearer_token=settings.DODO_PAYMENTS_API_KEY,
        environment="test_mode" if settings.DEBUG else "live_mode",
    )


def _is_webhook_processed(event_id):
    """Check if webhook was already processed"""
    if not event_id:
        return False
    return PaymentWebhook.objects.filter(event_id=event_id, processed=True).exists()


def _mark_webhook_processed(event_id, event_type, event_data):
    """Mark webhook as processed"""
    if not event_id:
        return
    PaymentWebhook.objects.update_or_create(
        event_id=event_id,
        defaults={
            'event_type': event_type,
            'payload': event_data,
            'processed': True,
            'processed_at': timezone.now()
        }
    )


# ... rest of your existing functions (_select_saved_payment_method,
# _sync_payment_method, _ensure_paid_invoice_for_subscription_renewal,
# _sync_subscription_from_invoice) remain the same ...


# Update the main webhook handler
@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@require_http_methods(["POST"])
def dodo_webhook(request):
    """
    Dodo Payments webhook endpoint with idempotency
    """
    logger.info("=" * 60)
    logger.info("📨 WEBHOOK RECEIVED")

    try:
        body = request.body.decode('utf-8')
        logger.info(f"Raw Body: {body}")

        data = json.loads(body)
        logger.info(f"Parsed Data: {json.dumps(data, indent=2)}")

        event_type = data.get('type')
        event_data = data.get('data', {})
        event_id = data.get('id') or event_data.get('id')

        logger.info(f"Event Type: {event_type}")
        logger.info(f"Event ID: {event_id}")

        # ✅ Check idempotency
        if event_id and _is_webhook_processed(event_id):
            logger.info(f"ℹ️ Webhook {event_id} already processed, skipping")
            return JsonResponse({"status": "already_processed"})

        # Route to handlers
        if event_type == 'payment.succeeded':
            response = handle_payment_succeeded(event_data)
        elif event_type == 'payment.failed':
            response = handle_payment_failed(event_data)
        elif event_type == 'subscription.cancelled':
            response = handle_subscription_cancelled(event_data)
        elif event_type == 'subscription.active':
            response = handle_subscription_active(event_data)
        elif event_type == 'subscription.renewed':
            response = handle_subscription_renewed(event_data)
        elif event_type == 'subscription.updated':
            response = handle_subscription_updated(event_data)
        else:
            logger.warning(f"⚠️ Unhandled event type: {event_type}")
            response = JsonResponse({"status": "ignored", "event": event_type})

        # ✅ Mark as processed
        if event_id and response.status_code == 200:
            _mark_webhook_processed(event_id, event_type, event_data)

        return response

    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON: {str(e)}")
        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)

    except Exception as e:
        logger.error(f"❌ Webhook error: {str(e)}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)})


# Updated handle_subscription_cancelled
def handle_subscription_cancelled(event_data):
    """Handle subscription cancellation"""
    try:
        logger.info("⛔ Processing subscription.cancelled")

        subscription_id = event_data.get('subscription_id')
        metadata = event_data.get('metadata', {})
        cancel_reason = metadata.get('cancel_reason', '')

        if not subscription_id:
            logger.error("❌ Missing subscription_id")
            return JsonResponse({"status": "error", "message": "No subscription ID"}, status=400)

        try:
            subscription = Subscription.objects.get(dodo_subscription_id=subscription_id)

            # ✅ If cancelled by customer (auto-renew disabled), just update status
            if cancel_reason == "disabled_by_customer" or cancel_reason == "cancelled_by_customer":
                subscription.auto_renew = False
                subscription.save(update_fields=["auto_renew", "updated_at"])
                logger.info(f"✅ Auto-renew disabled for subscription {subscription.id}")
            else:
                # Full cancellation
                subscription.cancel()
                logger.info(f"✅ Subscription {subscription.id} cancelled")

        except Subscription.DoesNotExist:
            logger.error(f"❌ Subscription not found: {subscription_id}")

        return JsonResponse({"status": "success"})

    except Exception as e:
        logger.error(f"❌ Error processing subscription cancellation: {str(e)}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)})


# Add this if Dodo supports subscription.updated event
def handle_subscription_updated(event_data):
    """Handle subscription update (auto-renew toggle)"""
    try:
        logger.info("🔄 Processing subscription.updated")

        subscription_id = event_data.get('subscription_id')
        auto_renew = event_data.get('auto_renew', False)

        if not subscription_id:
            logger.error("❌ Missing subscription_id")
            return JsonResponse({"status": "error", "message": "No subscription ID"}, status=400)

        try:
            subscription = Subscription.objects.get(dodo_subscription_id=subscription_id)
            subscription.auto_renew = auto_renew
            subscription.save(update_fields=["auto_renew", "updated_at"])
            logger.info(f"✅ Subscription {subscription.id} auto_renew updated to {auto_renew}")
        except Subscription.DoesNotExist:
            logger.error(f"❌ Subscription not found: {subscription_id}")

        return JsonResponse({"status": "success"})

    except Exception as e:
        logger.error(f"❌ Error processing subscription update: {str(e)}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)})


# ... rest of your handlers (handle_payment_succeeded, handle_payment_failed,
# handle_subscription_active, handle_subscription_renewed) remain the same ...

def _get_dodo_client():
    return DodoPayments(
        bearer_token=settings.DODO_PAYMENTS_API_KEY,
        environment="test_mode" if settings.DEBUG else "live_mode",
    )


def _select_saved_payment_method(payment_methods, event_data):
    payment_method_id = event_data.get("payment_method_id")
    if payment_method_id:
        for item in payment_methods:
            if getattr(item, "payment_method_id", None) == payment_method_id:
                return item

    card_last_four = event_data.get("card_last_four")
    card_network = (event_data.get("card_network") or "").strip().lower()

    if card_last_four:
        for item in payment_methods:
            card = getattr(item, "card", None)
            method_last_four = getattr(card, "last4_digits", None)
            method_network = (getattr(card, "card_network", "") or "").strip().lower()
            if method_last_four == card_last_four and (
                not card_network or not method_network or method_network == card_network
            ):
                return item

    recurring_methods = [
        item for item in payment_methods if getattr(item, "recurring_enabled", False)
    ]
    if len(recurring_methods) == 1:
        return recurring_methods[0]
    if recurring_methods:
        recurring_methods.sort(
            key=lambda item: (
                getattr(item, "last_used_at", None).timestamp()
                if getattr(item, "last_used_at", None)
                else 0
            ),
            reverse=True,
        )
        return recurring_methods[0]

    if len(payment_methods) == 1:
        return payment_methods[0]

    if payment_methods:
        payment_methods.sort(
            key=lambda item: (
                getattr(item, "last_used_at", None).timestamp()
                if getattr(item, "last_used_at", None)
                else 0
            ),
            reverse=True,
        )
        return payment_methods[0]

    return None


def _sync_payment_method(invoice, event_data):
    customer = event_data.get("customer", {}) or {}
    customer_id = customer.get("customer_id")
    if not customer_id:
        return None

    try:
        response = _get_dodo_client().customers.retrieve_payment_methods(customer_id)
    except Exception as exc:
        logger.warning("Could not retrieve saved payment methods from Dodo: %s", exc)
        return None

    items = list(getattr(response, "items", []) or [])
    payment_method_data = _select_saved_payment_method(items, event_data)
    payment_method_id = getattr(payment_method_data, "payment_method_id", None) or event_data.get("payment_method_id")
    if not payment_method_id:
        return None

    card = getattr(payment_method_data, "card", None) if payment_method_data else None
    payment_method, _created = PaymentMethod.objects.update_or_create(
        dodo_payment_method_id=payment_method_id,
        defaults={
            "user": invoice.user,
            "payment_type": PaymentMethod.PaymentType.CARD,
            "dodo_customer_id": customer_id,
            "card_last_four": getattr(card, "last4_digits", None) or event_data.get("card_last_four") or "",
            "card_brand": getattr(card, "card_network", None) or event_data.get("card_network") or "",
            "card_expiry_month": getattr(card, "expiry_month", None) or "",
            "card_expiry_year": getattr(card, "expiry_year", None) or "",
            "is_default": True,
            "is_active": True,
            "billing_address": event_data.get("billing") or {},
        },
    )

    PaymentMethod.objects.filter(
        user=invoice.user,
        is_default=True,
    ).exclude(pk=payment_method.pk).update(is_default=False)

    return payment_method


def _extract_billing_address(event_data, payment_method=None):
    billing = (event_data or {}).get("billing") or {}
    if billing:
        return billing
    if payment_method and getattr(payment_method, "billing_address", None):
        return payment_method.billing_address
    return {}


def _find_existing_invoice_for_subscription_renewal(
    subscription,
    payment_id=None,
    invoice_number=None,
    metadata=None,
):
    metadata = metadata or {}

    if invoice_number:
        invoice = Invoice.objects.filter(invoice_number=invoice_number).first()
        if invoice:
            return invoice

    if payment_id:
        invoice = Invoice.objects.filter(dodo_payment_id=payment_id).first()
        if invoice:
            return invoice

    if subscription.dodo_subscription_id:
        invoice = Invoice.objects.filter(
            subscription=subscription,
            dodo_subscription_id=subscription.dodo_subscription_id,
        ).first()
        if invoice:
            return invoice

    invoice = (
        Invoice.objects.filter(
            user=subscription.user,
            package_plan=subscription.package_plan,
        )
        .exclude(status=Invoice.Status.CANCELLED)
        .order_by("-issued_at", "-created_at")
        .first()
    )
    if invoice:
        return invoice

    return None

def _ensure_paid_invoice_for_subscription_renewal(subscription, payment_id=None, invoice_number=None, metadata=None):
    invoice = _find_existing_invoice_for_subscription_renewal(
        subscription,
        payment_id=payment_id,
        invoice_number=invoice_number,
        metadata=metadata,
    )
    if invoice is None:
        raise Invoice.DoesNotExist(
            f"No existing invoice found for subscription {subscription.id}"
        )

    if not invoice.user_id and subscription.user_id:
        invoice.user = subscription.user

    if not invoice.subscription_id:
        invoice.subscription = subscription

    if not invoice.payment_method_id and subscription.payment_method_id:
        invoice.payment_method = subscription.payment_method

    if payment_id and not invoice.dodo_payment_id:
        invoice.dodo_payment_id = payment_id

    if subscription.dodo_subscription_id and not invoice.dodo_subscription_id:
        invoice.dodo_subscription_id = subscription.dodo_subscription_id

    if not invoice.metadata:
        invoice.metadata = {}

    invoice.metadata.update(
        {
            **(metadata or {}),
            "source": invoice.metadata.get("source", "subscription_renewal"),
            "auto_renew": True,
            "billing_duration_days": subscription.billing_duration_days,
        }
    )
    invoice.save()
    return invoice


def _sync_subscription_from_invoice(invoice, subscription_id=None):
    subscription = invoice.subscription or Subscription.get_or_create_subscription(invoice)

    if subscription_id:
        invoice.dodo_subscription_id = subscription_id
        subscription.dodo_subscription_id = subscription_id

    if invoice.payment_method and not subscription.payment_method:
        subscription.payment_method = invoice.payment_method

    if not subscription.billing_duration_days:
        duration = getattr(invoice.package_plan, "duration", None)
        subscription.billing_duration_days = getattr(duration, "days", 0) or 0

    if subscription.auto_renew is not True:
        subscription.auto_renew = True

    if not subscription.next_billing_date and subscription.billing_duration_days:
        subscription.next_billing_date = subscription.started_at + timezone.timedelta(days=subscription.billing_duration_days)

    subscription.status = Subscription.Status.ACTIVE
    subscription.save(
        update_fields=[
            "payment_method",
            "billing_duration_days",
            "auto_renew",
            "next_billing_date",
            "status",
            "dodo_subscription_id",
            "updated_at",
        ]
    )

    invoice.subscription = subscription
    invoice.save(update_fields=["subscription", "dodo_subscription_id", "updated_at"])
    return subscription


class DodoWebhookSchema(AutoSchema):
    def get_tags(self, path, method):
        return ["Subscription"]

    def get_operation_id(self, path, method):
        return "dodo_webhook"

    def get_request_body(self, path, method):
        if method.upper() != "POST":
            return {}
        return {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "description": "Dodo event type, for example payment.succeeded.",
                            },
                            "data": {
                                "type": "object",
                                "description": "Webhook event payload.",
                                "properties": {
                                    "payment_id": {
                                        "type": "string",
                                        "description": "Dodo payment identifier.",
                                    },
                                    "subscription_id": {
                                        "type": "string",
                                        "description": "Dodo subscription identifier when available.",
                                    },
                                    "metadata": {
                                        "type": "object",
                                        "properties": {
                                            "invoice_number": {
                                                "type": "string",
                                                "description": "Invoice number stored in the checkout metadata.",
                                            }
                                        },
                                    },
                                },
                            },
                        },
                        "required": ["type", "data"],
                    }
                }
            }
        }


@csrf_exempt
@api_view(["POST"])
@schema(DodoWebhookSchema())
@authentication_classes([])
@permission_classes([AllowAny])
@require_http_methods(["POST"])
def dodo_webhook(request):
    """
    Dodo Payments webhook endpoint
    """
    # Log the incoming request
    logger.info("=" * 60)
    logger.info("📨 WEBHOOK RECEIVED")

    try:
        # Get the raw body
        body = request.body.decode('utf-8')
        logger.info(f"Raw Body: {body}")

        # Parse JSON
        data = json.loads(body)
        logger.info(f"Parsed Data: {json.dumps(data, indent=2)}")

        # Extract event type and data
        event_type = data.get('type')
        event_data = data.get('data', {})

        logger.info(f"Event Type: {event_type}")

        # Handle payment.succeeded
        if event_type == 'payment.succeeded':
            return handle_payment_succeeded(event_data)

        # Handle payment.failed
        elif event_type == 'payment.failed':
            return handle_payment_failed(event_data)

        # Handle subscription events
        elif event_type == 'subscription.cancelled':
            return handle_subscription_cancelled(event_data)

        elif event_type == 'subscription.active':
            return handle_subscription_active(event_data)

        elif event_type == 'subscription.renewed':
            return handle_subscription_renewed(event_data)

        else:
            logger.warning(f"⚠️ Unhandled event type: {event_type}")
            return JsonResponse({"status": "ignored", "event": event_type})

    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON: {str(e)}")
        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)

    except Exception as e:
        logger.error(f"❌ Webhook error: {str(e)}", exc_info=True)
        # Always return 200 to acknowledge receipt
        return JsonResponse({"status": "error", "message": str(e)})


def handle_payment_succeeded(event_data):
    """Handle successful payment"""
    try:
        logger.info("💰 Processing payment.succeeded")

        # Extract data
        payment_id = event_data.get('payment_id')
        subscription_id = event_data.get('subscription_id')
        metadata = event_data.get('metadata', {})
        customer = event_data.get('customer', {})

        invoice_number = metadata.get('invoice_number')

        logger.info(f"   Payment ID: {payment_id}")
        logger.info(f"   Subscription ID: {subscription_id}")
        logger.info(f"   Invoice Number: {invoice_number}")
        logger.info(f"   Customer: {customer.get('email')}")
        logger.info(f"   Metadata: {metadata}")

        # Validate invoice number
        if not invoice_number and not subscription_id:
            logger.error("❌ Missing invoice_number and subscription_id in metadata")
            return JsonResponse({"status": "error", "message": "No invoice number"}, status=400)

        # Find invoice
        try:
            if invoice_number:
                invoice = Invoice.objects.get(invoice_number=invoice_number)
            else:
                subscription = Subscription.objects.get(dodo_subscription_id=subscription_id)
                invoice = _ensure_paid_invoice_for_subscription_renewal(
                    subscription,
                    payment_id=payment_id,
                    invoice_number=None,
                    metadata=metadata,
                )
            logger.info(f"✅ Found Invoice: {invoice.id}")
            logger.info(f"   Current Status: {invoice.status}")
            logger.info(f"   User: {invoice.user.email}")
            logger.info(f"   Amount: {invoice.total} {invoice.currency}")
            logger.info(f"   Package Plan: {invoice.package_plan}")

        except (Invoice.DoesNotExist, Subscription.DoesNotExist):
            logger.error(f"❌ Invoice or subscription not found: invoice={invoice_number} subscription={subscription_id}")
            return JsonResponse({"status": "error", "message": "Invoice not found"}, status=404)

        # Check if already processed
        if invoice.status == Invoice.Status.PAID:
            logger.info(f"ℹ️ Invoice {invoice_number} already paid, skipping")
            return JsonResponse({"status": "already_processed"})

        # MARK INVOICE AS PAID
        invoice.status = Invoice.Status.PAID
        invoice.paid_at = timezone.now()

        if payment_id:
            invoice.dodo_payment_id = payment_id
            logger.info(f"   Set Payment ID: {payment_id}")

        if subscription_id:
            invoice.dodo_subscription_id = subscription_id
            logger.info(f"   Set Subscription ID: {subscription_id}")

        payment_method = _sync_payment_method(invoice, event_data)
        if payment_method:
            invoice.payment_method = payment_method
            logger.info(f"   Synced Payment Method: {payment_method.dodo_payment_method_id}")
        invoice.billing_address = _extract_billing_address(event_data, payment_method)

        invoice.save()
        logger.info(f"✅ Invoice {invoice_number} marked as PAID")

        # CREATE/UPDATE SUBSCRIPTION
        if invoice.package_plan:
            logger.info("🔄 Creating/updating subscription...")
            try:
                subscription = Subscription.get_or_create_subscription(invoice)
                if subscription:
                    logger.info(f"✅ Subscription created/updated: {subscription.id}")
                    logger.info(f"   Status: {subscription.status}")
                    logger.info(f"   Expires: {subscription.expires_at}")

                    logger.info(f"✅ Invoice linked to subscription: {subscription.id}")
                else:
                    logger.error("❌ Failed to create subscription")
            except Exception as e:
                logger.error(f"❌ Error creating subscription: {str(e)}", exc_info=True)
        else:
            logger.warning("⚠️ No package plan on invoice")

        return JsonResponse({
            "status": "success",
            "invoice": invoice_number,
            "payment_id": payment_id,
            "subscription_id": subscription_id
        })

    except Exception as e:
        logger.error(f"❌ Error processing payment success: {str(e)}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)})


def handle_payment_failed(event_data):
    """Handle failed payment"""
    try:
        logger.info("❌ Processing payment.failed")

        metadata = event_data.get('metadata', {})
        invoice_number = metadata.get('invoice_number')

        if not invoice_number:
            logger.error("❌ Missing invoice_number in metadata")
            return JsonResponse({"status": "error", "message": "No invoice number"}, status=400)

        try:
            invoice = Invoice.objects.get(invoice_number=invoice_number)
            invoice.status = Invoice.Status.CANCELLED
            invoice.save()
            logger.info(f"✅ Invoice {invoice_number} marked as CANCELLED")
        except Invoice.DoesNotExist:
            logger.error(f"❌ Invoice not found: {invoice_number}")

        return JsonResponse({"status": "success"})

    except Exception as e:
        logger.error(f"❌ Error processing payment failed: {str(e)}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)})


def handle_subscription_cancelled(event_data):
    """Handle subscription cancellation"""
    try:
        logger.info("⛔ Processing subscription.cancelled")

        subscription_id = event_data.get('subscription_id')

        if not subscription_id:
            logger.error("❌ Missing subscription_id")
            return JsonResponse({"status": "error", "message": "No subscription ID"}, status=400)

        try:
            subscription = Subscription.objects.get(dodo_subscription_id=subscription_id)
            subscription.cancel()
            logger.info(f"✅ Subscription {subscription.id} cancelled")
        except Subscription.DoesNotExist:
            logger.error(f"❌ Subscription not found: {subscription_id}")

        return JsonResponse({"status": "success"})

    except Exception as e:
        logger.error(f"❌ Error processing subscription cancellation: {str(e)}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)})


def handle_subscription_active(event_data):
    """Handle mandate activation for on-demand subscriptions."""
    try:
        logger.info("✅ Processing subscription.active")

        subscription_id = event_data.get("subscription_id")
        metadata = event_data.get("metadata", {})
        invoice_number = metadata.get("invoice_number")

        if not subscription_id:
            logger.error("❌ Missing subscription_id")
            return JsonResponse({"status": "error", "message": "No subscription ID"}, status=400)

        if not invoice_number:
            logger.error("❌ Missing invoice_number in metadata for subscription.active")
            return JsonResponse({"status": "error", "message": "No invoice number"}, status=400)

        try:
            invoice = Invoice.objects.get(invoice_number=invoice_number)
        except Invoice.DoesNotExist:
            logger.error("❌ Invoice not found for subscription.active: %s", invoice_number)
            return JsonResponse({"status": "error", "message": "Invoice not found"}, status=404)

        subscription = _sync_subscription_from_invoice(invoice, subscription_id=subscription_id)
        logger.info(f"✅ Subscription activated: {subscription.id} / {subscription.dodo_subscription_id}")
        return JsonResponse({"status": "success"})

    except Exception as e:
        logger.error(f"❌ Error processing subscription active: {str(e)}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)})


def handle_subscription_renewed(event_data):
    """Handle subscription renewal"""
    try:
        logger.info("🔄 Processing subscription.renewed")

        subscription_id = event_data.get('subscription_id')
        payment_id = event_data.get('payment_id')
        metadata = event_data.get('metadata', {})
        invoice_number = metadata.get('invoice_number')

        if not subscription_id:
            logger.error("❌ Missing subscription_id")
            return JsonResponse({"status": "error", "message": "No subscription ID"}, status=400)

        try:
            subscription = Subscription.objects.get(dodo_subscription_id=subscription_id)
            invoice = _ensure_paid_invoice_for_subscription_renewal(
                subscription,
                payment_id=payment_id,
                invoice_number=invoice_number,
                metadata=metadata,
            )

            # Update invoice
            invoice.status = Invoice.Status.PAID
            invoice.paid_at = timezone.now()
            if payment_id:
                invoice.dodo_payment_id = payment_id
            if subscription_id:
                invoice.dodo_subscription_id = subscription_id
            invoice.save()
            logger.info(f"✅ Invoice {invoice_number} updated for renewal")

            subscription = Subscription.get_or_create_subscription(invoice)
            invoice.subscription = subscription
            invoice.save(update_fields=["subscription", "updated_at"])
            logger.info(f"✅ Subscription renewal synced: {subscription.id}")
            logger.info(f"   Current expiry: {subscription.expires_at}")

        except (Subscription.DoesNotExist, Invoice.DoesNotExist) as e:
            logger.error(f"❌ Error processing renewal: {str(e)}")

        return JsonResponse({"status": "success"})

    except Exception as e:
        logger.error(f"❌ Error processing subscription renewal: {str(e)}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)})
