# webhooks.py
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.utils import timezone
from dodopayments import DodoPayments
from .models import Invoice, Subscription

logger = logging.getLogger(__name__)


class DodoWebhookHandler:
    def __init__(self):
        self.client = DodoPayments(
            bearer_token=settings.DODO_PAYMENTS_API_KEY,
            environment="test_mode" if settings.DEBUG else "live_mode",
        )

    def verify_webhook(self, request):
        """Verify webhook signature"""
        try:
            webhook_id = request.headers.get('webhook-id')
            webhook_signature = request.headers.get('webhook-signature')
            webhook_timestamp = request.headers.get('webhook-timestamp')

            if not all([webhook_id, webhook_signature, webhook_timestamp]):
                raise ValueError("Missing webhook headers")

            # For testing without signature verification
            if settings.DEBUG and not webhook_signature:
                logger.warning("⚠️ Webhook signature missing - using test mode")
                return json.loads(request.body)

            event = self.client.webhooks.unwrap(
                request.body,
                headers={
                    "webhook-id": webhook_id,
                    "webhook-signature": webhook_signature,
                    "webhook-timestamp": webhook_timestamp,
                }
            )
            return event
        except Exception as e:
            logger.error(f"Webhook verification failed: {str(e)}")
            raise

    def handle_payment_succeeded(self, event):
        """Handle payment.succeeded event"""
        logger.info(f"💰 Processing payment.succeeded event: {event}")

        # Handle both object and dict formats
        if hasattr(event, 'data'):
            data = event.data
        else:
            data = event.get('data', {})

        # Extract data
        payment_id = data.get('payment_id')
        metadata = data.get('metadata', {})
        customer = data.get('customer', {})

        invoice_number = metadata.get('invoice_number')
        if not invoice_number:
            logger.error(f"❌ Missing invoice_number in metadata: {metadata}")
            return

        try:
            invoice = Invoice.objects.get(invoice_number=invoice_number)
        except Invoice.DoesNotExist:
            logger.error(f"❌ Invoice not found: {invoice_number}")
            return

        # Check for idempotency (already processed)
        if invoice.status == Invoice.Status.PAID:
            logger.info(f"ℹ️ Invoice {invoice_number} already paid, skipping")
            return

        # Get subscription ID
        subscription_id = data.get('subscription_id')

        # Mark invoice as paid
        invoice.mark_as_paid(
            payment_id=payment_id,
            subscription_id=subscription_id
        )

        # Create/update subscription
        if invoice.package_plan and invoice.package_plan.is_subscription:
            subscription = Subscription.get_or_create_subscription(invoice)
            logger.info(f"✅ Subscription created/updated: {subscription.id} for user {invoice.user.email}")

        logger.info(f"✅ Payment succeeded for invoice {invoice_number} (payment: {payment_id})")

    def handle_payment_failed(self, event):
        """Handle payment.failed event"""
        logger.info(f"❌ Processing payment.failed event")

        if hasattr(event, 'data'):
            data = event.data
        else:
            data = event.get('data', {})

        metadata = data.get('metadata', {})
        invoice_number = metadata.get('invoice_number')

        if not invoice_number:
            logger.error(f"❌ Missing invoice_number in metadata: {metadata}")
            return

        try:
            invoice = Invoice.objects.get(invoice_number=invoice_number)
            invoice.mark_as_failed()
            logger.info(f"❌ Payment failed for invoice {invoice_number}")
        except Invoice.DoesNotExist:
            logger.error(f"❌ Invoice not found: {invoice_number}")

    def handle_subscription_cancelled(self, event):
        """Handle subscription.cancelled event"""
        logger.info(f"⛔ Processing subscription.cancelled event")

        if hasattr(event, 'data'):
            data = event.data
        else:
            data = event.get('data', {})

        subscription_id = data.get('subscription_id')

        if not subscription_id:
            logger.error(f"❌ Missing subscription_id")
            return

        try:
            subscription = Subscription.objects.get(dodo_subscription_id=subscription_id)
            subscription.cancel()
            logger.info(f"✅ Subscription cancelled: {subscription.id}")
        except Subscription.DoesNotExist:
            logger.error(f"❌ Subscription not found: {subscription_id}")

    def handle_subscription_renewed(self, event):
        """Handle subscription.renewed event"""
        logger.info(f"🔄 Processing subscription.renewed event")

        if hasattr(event, 'data'):
            data = event.data
        else:
            data = event.get('data', {})

        subscription_id = data.get('subscription_id')
        payment_id = data.get('payment_id')
        metadata = data.get('metadata', {})
        invoice_number = metadata.get('invoice_number')

        if not invoice_number:
            logger.error(f"❌ Missing invoice_number in metadata")
            return

        try:
            subscription = Subscription.objects.get(dodo_subscription_id=subscription_id)
            invoice = Invoice.objects.get(invoice_number=invoice_number)

            # Update invoice
            invoice.mark_as_paid(payment_id=payment_id)

            # Update subscription - extend by duration
            if subscription.package_plan:
                duration_days = subscription.package_plan.duration.days
                subscription.end_date = timezone.now() + timezone.timedelta(days=duration_days)
                subscription.status = Subscription.Status.ACTIVE
                subscription.current_invoice = invoice
                subscription.save()

            logger.info(f"✅ Subscription renewed: {subscription.id} until {subscription.end_date}")
        except (Subscription.DoesNotExist, Invoice.DoesNotExist) as e:
            logger.error(f"❌ Error processing renewal: {str(e)}")

    def handle_webhook(self, request):
        """Main webhook handler"""
        try:
            # Verify webhook
            event = self.verify_webhook(request)

            # Get event type
            if hasattr(event, 'type'):
                event_type = event.type
            else:
                event_type = event.get('type')

            logger.info(f"📨 Processing webhook: {event_type}")

            # Route to appropriate handler
            handlers = {
                'payment.succeeded': self.handle_payment_succeeded,
                'payment.failed': self.handle_payment_failed,
                'subscription.cancelled': self.handle_subscription_cancelled,
                'subscription.renewed': self.handle_subscription_renewed,
                'subscription.active': self.handle_payment_succeeded,  # Treat as success
            }

            handler = handlers.get(event_type)
            if handler:
                handler(event)
            else:
                logger.warning(f"⚠️ Unhandled webhook event type: {event_type}")

            return True

        except Exception as e:
            logger.error(f"❌ Webhook processing error: {str(e)}", exc_info=True)
            return False


@csrf_exempt
@require_http_methods(["POST"])
def dodo_webhook(request):
    """
    Dodo Payments webhook endpoint
    """
    handler = DodoWebhookHandler()
    success = handler.handle_webhook(request)

    # Always return 200 to acknowledge receipt
    return JsonResponse({"status": "received" if success else "error"})