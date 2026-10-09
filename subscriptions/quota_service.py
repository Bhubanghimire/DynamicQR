"""Central subscription quota checks for QR and project-member usage."""

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from accounts.models import User
from Qr.models import Invitations, Project, SharePermissions
from Qr.services.account_ownership import qrs_billed_to
from subscriptions.models import Subscription


class QRLimitExceeded(Exception):
    def __init__(self, limit, used, requested):
        self.limit = limit
        self.used = used
        self.requested = requested
        super().__init__("QR code limit reached for your package.")


class TeamMemberLimitExceeded(Exception):
    def __init__(self, limit, used, requested):
        self.limit = limit
        self.used = used
        self.requested = requested
        super().__init__("Team member limit reached for this account.")


def get_qr_limit(user):
    subscription = Subscription.get_usage_subscription_for_user(user)
    if subscription is None:
        return 0
    if subscription.qr_limit is not None:
        return subscription.qr_limit
    return subscription.package_plan.max_qrs if subscription.package_plan else 0


def get_bulk_upload_limit(user):
    subscription = Subscription.get_usage_subscription_for_user(user)
    if subscription is None:
        return 0
    if subscription.bulk_upload_limit is not None:
        return subscription.bulk_upload_limit
    return subscription.package_plan.max_bulk_upload if subscription.package_plan else 0


def get_team_member_limit(user):
    subscription = Subscription.get_usage_subscription_for_user(user)
    if subscription is None:
        return None
    if subscription.team_member_limit is not None:
        return subscription.team_member_limit
    return subscription.package_plan.max_team_members if subscription.package_plan else 0


def lock_account_owner(user):
    return User.objects.select_for_update().get(pk=user.pk)


def check_qr_capacity(user, requested=1):
    limit = get_qr_limit(user)
    used = qrs_billed_to(user).count()
    if limit is not None and used + requested > limit:
        raise QRLimitExceeded(limit=limit, used=used, requested=requested)
    return limit, used


def _team_member_identities(owner):
    content_type = ContentType.objects.get_for_model(Project)
    owned_project_ids = Project.objects.filter(owner=owner).values_list("id", flat=True)
    accepted_emails = SharePermissions.objects.filter(
        content_type=content_type,
        resource_id__in=owned_project_ids,
        is_deleted=False,
    ).exclude(user_id=owner).values_list("user_id__email", flat=True)
    pending_emails = Invitations.objects.filter(
        content_type=content_type,
        resource_id__in=owned_project_ids,
        status__name__iexact="pending",
        expires_at__gt=timezone.now(),
        is_deleted=False,
    ).values_list("email", flat=True)
    return {
        email.strip().lower()
        for email in (*accepted_emails, *pending_emails)
        if email and email.strip() and email.strip().lower() != owner.email.strip().lower()
    }


def check_team_member_capacity(owner, emails):
    limit = get_team_member_limit(owner)
    existing = _team_member_identities(owner)
    requested_identities = {
        email.strip().lower()
        for email in emails
        if email and email.strip() and email.strip().lower() != owner.email.strip().lower()
    }
    added = requested_identities - existing
    if limit is not None and len(existing) + len(added) > limit:
        raise TeamMemberLimitExceeded(
            limit=limit,
            used=len(existing),
            requested=len(added),
        )
    return limit, len(existing), len(added)
