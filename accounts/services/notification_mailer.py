from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Count
from django.template.loader import render_to_string
from django.utils import timezone

from accounts.models import NotificationPreference
from analytics.models import ScanEvent


class NotificationMailer:
    def _send_email(self, *, user, subject, template_name, context):
        html_content = render_to_string(f"email/notifications/{template_name}.html", context=context)
        text_content = render_to_string(f"email/notifications/{template_name}.txt", context=context)

        message = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        message.attach_alternative(html_content, "text/html")
        message.send(fail_silently=False)

    def send_scan_alert(self, scan_event_id):
        scan_event = (
            ScanEvent.objects.select_related("qr", "qr__created_by")
            .get(pk=scan_event_id)
        )
        user = scan_event.qr.created_by
        try:
            preference = user.notification_preference
        except NotificationPreference.DoesNotExist:
            return 0
        if not preference.scan_alert:
            return 0

        context = {
            "user": user,
            "qr": scan_event.qr,
            "scan_event": scan_event,
        }
        self._send_email(
            user=user,
            subject=f"New scan on {scan_event.qr.name or scan_event.qr.short_code}",
            template_name="scan_alert",
            context=context,
        )
        return 1

    def send_weekly_performance(self, for_date=None):
        end_date = for_date or timezone.localdate()
        start_date = end_date - timedelta(days=6)
        sent = 0

        preferences = (
            NotificationPreference.objects.select_related("user")
            .filter(weekly_performance=True, user__is_active=True)
        )

        for preference in preferences:
            user = preference.user
            weekly_scans = (
                ScanEvent.objects.filter(
                    qr__created_by=user,
                    scanned_at__date__range=(start_date, end_date),
                )
                .values("qr_id")
                .annotate(total=Count("id"))
                .order_by("-total")
            )
            context = {
                "user": user,
                "start_date": start_date,
                "end_date": end_date,
                "scan_count": ScanEvent.objects.filter(
                    qr__created_by=user,
                    scanned_at__date__range=(start_date, end_date),
                ).count(),
                "weekly_scans": weekly_scans,
            }
            self._send_email(
                user=user,
                subject=f"Weekly QR performance for {start_date:%Y-%m-%d} to {end_date:%Y-%m-%d}",
                template_name="weekly_digest",
                context=context,
            )
            sent += 1

        return sent

    def send_product_updates(self, subject, context):
        preferences = (
            NotificationPreference.objects.select_related("user")
            .filter(product_updates=True, user__is_active=True)
        )
        sent = 0
        for preference in preferences:
            user = preference.user
            self._send_email(
                user=user,
                subject=subject,
                template_name="product_update",
                context={"user": user, **context},
            )
            sent += 1
        return sent

    def send_security_alerts(self, subject, context):
        preferences = (
            NotificationPreference.objects.select_related("user")
            .filter(security_alerts=True, user__is_active=True)
        )
        sent = 0
        for preference in preferences:
            user = preference.user
            self._send_email(
                user=user,
                subject=subject,
                template_name="security_alert",
                context={"user": user, **context},
            )
            sent += 1
        return sent
