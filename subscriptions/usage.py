"""Package scan quota derived from the existing QR analytics summaries."""

from django.db.models import Sum
from django.db.models.functions import Coalesce

from analytics.models import QRAnalytics
from Qr.services.account_ownership import qrs_billed_to
from subscriptions.models import Subscription


class PackageScanLimitExceeded(Exception):
    def __init__(self, limit, used):
        self.limit = limit
        self.used = used
        super().__init__("Scan limit reached for your package.")


def get_package_scan_quota(user):
    subscription = Subscription.get_usage_subscription_for_user(user)
    if subscription is None:
        limit = 0
    else:
        limit = subscription.scan_limit
        if limit is None:
            limit = subscription.package_plan.max_scans

    used = QRAnalytics.objects.filter(
        qr__in=qrs_billed_to(user),
    ).aggregate(total=Coalesce(Sum("total_scans"), 0))["total"]
    return limit, used
