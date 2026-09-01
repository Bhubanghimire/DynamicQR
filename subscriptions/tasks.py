# import logging
#
# from celery import shared_task
# from django.db import transaction
# from django.utils import timezone
#
# from subscriptions.models import Invoice, Subscription
# from subscriptions.services import DodoBillingService
#
# logger = logging.getLogger(__name__)
#
#
# def _get_renewal_invoice(subscription):
#     return (
#         Invoice.objects.filter(
#             subscription=subscription,
#             metadata__source="subscription_renewal",
#             metadata__billing_duration_days=subscription.billing_duration_days,
#         )
#         .order_by("-created_at")
#         .first()
#     )
#
#
# @shared_task(bind=True)
# def process_due_subscription_renewals(self):
#     now = timezone.now()
#     due_subscriptions = (
#         Subscription.objects.select_related("user", "package_plan", "package_plan__package")
#         .filter(
#             status=Subscription.Status.ACTIVE,
#             auto_renew=True,
#             next_billing_date__lte=now,
#         )
#         .exclude(dodo_subscription_id__isnull=True)
#         .exclude(dodo_subscription_id="")
#         .order_by("next_billing_date", "created_at")
#     )
#
#     processed = 0
#     skipped = 0
#     failed = 0
#
#     for subscription in due_subscriptions:
#         invoice = None
#         with transaction.atomic():
#             locked_subscription = (
#                 Subscription.objects.select_for_update()
#                 .select_related("user", "package_plan", "package_plan__package")
#                 .get(pk=subscription.pk)
#             )
#
#             if not locked_subscription.auto_renew:
#                 skipped += 1
#                 continue
#
#             if locked_subscription.next_billing_date and locked_subscription.next_billing_date > timezone.now():
#                 skipped += 1
#                 continue
#
#             invoice = _get_renewal_invoice(locked_subscription)
#             if invoice and invoice.status in {Invoice.Status.PENDING, Invoice.Status.PAID}:
#                 skipped += 1
#                 continue
#
#             if not invoice:
#                 invoice = Invoice.objects.create(
#                     user=locked_subscription.user,
#                     subscription=locked_subscription,
#                     package_plan=locked_subscription.package_plan,
#                     payment_method=locked_subscription.payment_method,
#                     amount=locked_subscription.price,
#                     tax=0,
#                     total=locked_subscription.price,
#                     currency=locked_subscription.currency,
#                     due_date=now,
#                     status=Invoice.Status.PENDING,
#                     metadata={
#                         "source": "subscription_renewal",
#                         "auto_renew": True,
#                         "billing_duration_days": locked_subscription.billing_duration_days,
#                     },
#                 )
#             else:
#                 invoice.status = Invoice.Status.PENDING
#                 invoice.total = locked_subscription.price
#                 invoice.amount = locked_subscription.price
#                 invoice.currency = locked_subscription.currency
#                 invoice.due_date = now
#                 invoice.metadata = {
#                     **invoice.metadata,
#                     "source": "subscription_renewal",
#                     "auto_renew": True,
#                     "billing_duration_days": locked_subscription.billing_duration_days,
#                 }
#                 invoice.save()
#
#         try:
#             DodoBillingService().charge_subscription(locked_subscription, invoice=invoice)
#             processed += 1
#         except Exception:
#             failed += 1
#             logger.exception("Failed to trigger renewal charge for subscription %s", locked_subscription.pk)
#
#     return {
#         "processed": processed,
#         "skipped": skipped,
#         "failed": failed,
#     }
