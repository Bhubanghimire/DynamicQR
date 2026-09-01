
import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from subscriptions.models import PackagePlan
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

