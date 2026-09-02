from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.utils import timezone
from dodopayments import DodoPayments

from Qr.tasks import logger
from subscriptions.models import Invoice, Subscription

ZERO_DECIMAL_CURRENCIES = {
    "BIF", "CLP", "DJF", "GNF", "JPY", "KMF",
    "KRW", "MGA", "PYG", "RWF", "UGX", "VND",
    "VUV", "XAF", "XOF", "XPF",
}

THREE_DECIMAL_CURRENCIES = {
    "BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND",
}


def currency_minor_unit(currency):
    currency = (currency or "USD").upper()

    if currency in ZERO_DECIMAL_CURRENCIES:
        return 0

    if currency in THREE_DECIMAL_CURRENCIES:
        return 3

    return 2


def to_minor_units(amount, currency):
    decimals = currency_minor_unit(currency)
    factor = Decimal(10) ** decimals

    return int(
        (Decimal(str(amount)) * factor).to_integral_value(
            rounding=ROUND_HALF_UP
        )
    )


class DodoBillingService:

    def __init__(self, client=None):
        self.client = client or DodoPayments(
            bearer_token=settings.DODO_PAYMENTS_API_KEY,
            environment="test_mode" if settings.DEBUG else "live_mode",
        )

    def charge_subscription(self, subscription, invoice=None):

        if not subscription.dodo_subscription_id:
            raise ValueError(
                "Subscription does not have a Dodo subscription id."
            )

        if invoice is None:
            invoice = Invoice.objects.create(
                user=subscription.user,
                subscription=subscription,
                package_plan=subscription.package_plan,
                payment_method=subscription.payment_method,
                amount=subscription.price,
                tax=0,
                total=subscription.price,
                currency=subscription.currency,
                due_date=timezone.now(),
                status=Invoice.Status.PENDING,
                billing_address=getattr(subscription.payment_method, "billing_address", {}) or {},
                metadata={
                    "source": "subscription_renewal",
                    "auto_renew": True,
                    "billing_duration_days": (
                        subscription.billing_duration_days
                    ),
                },
            )

        try:
            response = self.client.subscriptions.charge(
                subscription.dodo_subscription_id,
                {
                    "product_price": to_minor_units(
                        subscription.price,
                        subscription.currency,
                    ),
                    "product_currency": subscription.currency,
                    "product_description": (
                        f"{subscription.package_plan.package.title} renewal"
                    ),
                    "metadata": {
                        "invoice_number": invoice.invoice_number,
                        "subscription_uuid": str(subscription.id),
                        "billing_duration_days": str(
                            subscription.billing_duration_days
                        ),
                        "auto_renew": "true",
                    },
                },
            )

        except Exception:
            invoice.status = Invoice.Status.CANCELLED
            invoice.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )
            raise

        payment_id = getattr(response, "payment_id", None)

        if payment_id:
            invoice.dodo_payment_id = payment_id
            invoice.save(
                update_fields=[
                    "dodo_payment_id",
                    "updated_at",
                ]
            )

        return invoice, response

    def update_subscription_auto_renew(self, dodo_subscription_id, auto_renew):
        """
        Update auto-renew setting on Dodo subscription

        Note: Dodo may not support direct auto-renew update.
        If not supported, you may need to:
        1. Cancel the current subscription
        2. Create a new subscription with auto_renew setting
        """
        try:
            # Try to update directly
            response = self.client.subscriptions.update(
                dodo_subscription_id,
                auto_renew=auto_renew
            )
            logger.info(f"✅ Updated Dodo subscription {dodo_subscription_id} auto_renew to {auto_renew}")
            return response
        except AttributeError:
            # If direct update not supported, log and raise
            logger.warning(f"⚠️ Direct auto_renew update not supported by Dodo SDK")
            raise NotImplementedError(
                "Dodo API does not support updating auto_renew directly. "
                "You may need to cancel and recreate the subscription."
            )
        except Exception as e:
            logger.error(f"❌ Failed to update Dodo subscription auto_renew: {str(e)}")
            raise

    def get_subscription_details(self, dodo_subscription_id):
        """
        Get subscription details from Dodo
        """
        try:
            subscription = self.client.subscriptions.retrieve(dodo_subscription_id)
            return subscription
        except Exception as e:
            logger.error(f"❌ Failed to get Dodo subscription: {str(e)}")
            raise

    def sync_subscription_status(self, subscription):
        """
        Sync subscription status with Dodo
        """
        if not subscription.dodo_subscription_id:
            return

        try:
            dodo_sub = self.get_subscription_details(subscription.dodo_subscription_id)

            # Map Dodo status to your status
            status_map = {
                'active': Subscription.Status.ACTIVE,
                'cancelled': Subscription.Status.CANCELLED,
                'expired': Subscription.Status.EXPIRED,
                'past_due': Subscription.Status.FAILED,
            }

            dodo_status = getattr(dodo_sub, 'status', None)
            if dodo_status in status_map:
                subscription.status = status_map[dodo_status]
                subscription.save()
                logger.info(f"✅ Synced subscription {subscription.id} status to {subscription.status}")

        except Exception as e:
            logger.error(f"❌ Failed to sync subscription: {str(e)}")
