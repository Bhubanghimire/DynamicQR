from celery import shared_task

from accounts.services.notification_mailer import NotificationMailer


@shared_task
def send_scan_notification(scan_event_id):
    return NotificationMailer().send_scan_alert(scan_event_id)


@shared_task
def send_weekly_notification_digest():
    return NotificationMailer().send_weekly_performance()


@shared_task
def send_product_notification(subject, context):
    return NotificationMailer().send_product_updates(subject, context)


@shared_task
def send_security_notification(subject, context):
    return NotificationMailer().send_security_alerts(subject, context)
