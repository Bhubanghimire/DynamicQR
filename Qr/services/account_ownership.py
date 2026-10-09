"""Resolve the subscription account responsible for QR usage."""

from django.db.models import Q

from Qr.models import QRCode


def account_owner_for_project(project, actor):
    """Return the billed account for an operation scoped to ``project``."""
    return project.owner if project is not None else actor


def account_owner_for_qr(qr):
    """Return the billed account for an existing QR code."""
    return qr.project.owner if qr.project_id else qr.created_by


def qrs_billed_to(user):
    """Active QR codes charged to ``user`` under the project ownership rule."""
    return QRCode.objects.filter(
        Q(project__owner=user)
        | Q(project__isnull=True, created_by=user)
    ).distinct()
