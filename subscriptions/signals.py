
import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from subscriptions.models import PackagePlan, PackagePlanPrice
from subscriptions.services.dodo_product_service import DodoProductService

logger = logging.getLogger(__name__)


@receiver(post_save, sender=PackagePlan)
def sync_package_plan_with_dodo(sender, instance, created, **kwargs):
    """
    Automatically create/update the Dodo product whenever a PackagePlan
    is created or updated.

    CREATE:
        PackagePlan has no dodo_product_id
        -> create Dodo product
        -> save returned product ID

    UPDATE:
        PackagePlan already has dodo_product_id
        -> update existing Dodo product
    """

    # Do not synchronize inactive/deleted plans with Dodo.
    if not instance.is_active:
        logger.info(
            "Skipping Dodo sync for inactive PackagePlan %s",
            instance.pk,
        )
        return

    def sync():
        try:
            DodoProductService().sync_plan(instance)

        except Exception:
            logger.exception(
                "Failed to synchronize PackagePlan %s with Dodo Payments.",
                instance.pk,
            )

    transaction.on_commit(sync)


@receiver(post_save, sender=PackagePlanPrice)
def sync_package_plan_price_with_dodo(sender, instance, created, **kwargs):
    """Create/update the Dodo product belonging to one currency price."""
    if not instance.is_active or not instance.package_plan.is_active:
        return

    def sync():
        try:
            DodoProductService().sync_price(instance)
        except Exception:
            logger.exception(
                "Failed to synchronize PackagePlanPrice %s with Dodo Payments.",
                instance.pk,
            )

    transaction.on_commit(sync)
