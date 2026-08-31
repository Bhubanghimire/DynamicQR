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

from .models import Invoice, Subscription

logger = logging.getLogger(__name__)


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
        if not invoice_number:
            logger.error("❌ Missing invoice_number in metadata")
            return JsonResponse({"status": "error", "message": "No invoice number"}, status=400)

        # Find invoice
        try:
            invoice = Invoice.objects.get(invoice_number=invoice_number)
            logger.info(f"✅ Found Invoice: {invoice.id}")
            logger.info(f"   Current Status: {invoice.status}")
            logger.info(f"   User: {invoice.user.email}")
            logger.info(f"   Amount: {invoice.total} {invoice.currency}")
            logger.info(f"   Package Plan: {invoice.package_plan}")

        except Invoice.DoesNotExist:
            logger.error(f"❌ Invoice not found: {invoice_number}")
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

                    # Link subscription to invoice
                    invoice.subscription = subscription
                    invoice.save(update_fields=["subscription"])
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
            invoice.status = Invoice.Status.FAILED
            invoice.save()
            logger.info(f"✅ Invoice {invoice_number} marked as FAILED")
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


def handle_subscription_renewed(event_data):
    """Handle subscription renewal"""
    try:
        logger.info("🔄 Processing subscription.renewed")

        subscription_id = event_data.get('subscription_id')
        payment_id = event_data.get('payment_id')
        metadata = event_data.get('metadata', {})
        invoice_number = metadata.get('invoice_number')

        if not invoice_number:
            logger.error("❌ Missing invoice_number in metadata")
            return JsonResponse({"status": "error", "message": "No invoice number"}, status=400)

        try:
            subscription = Subscription.objects.get(dodo_subscription_id=subscription_id)
            invoice = Invoice.objects.get(invoice_number=invoice_number)

            # Update invoice
            invoice.status = Invoice.Status.PAID
            invoice.paid_at = timezone.now()
            invoice.dodo_payment_id = payment_id
            invoice.save()
            logger.info(f"✅ Invoice {invoice_number} updated for renewal")

            # Update subscription
            if subscription.package_plan and subscription.package_plan.duration:
                duration_days = subscription.package_plan.duration.days or 30
                subscription.expires_at = timezone.now() + timezone.timedelta(days=duration_days)
                subscription.status = Subscription.Status.ACTIVE
                subscription.current_invoice = invoice
                subscription.last_renewal_date = timezone.now()
                subscription.next_billing_date = subscription.expires_at
                subscription.save()
                logger.info(f"✅ Subscription renewed: {subscription.id}")
                logger.info(f"   New expiry: {subscription.expires_at}")

        except (Subscription.DoesNotExist, Invoice.DoesNotExist) as e:
            logger.error(f"❌ Error processing renewal: {str(e)}")

        return JsonResponse({"status": "success"})

    except Exception as e:
        logger.error(f"❌ Error processing subscription renewal: {str(e)}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)})
