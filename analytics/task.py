from celery import shared_task

from Qr.models import QRCode

from analytics.services.tracker import AnalyticsTracker


@shared_task
def track_scan(qr_id, request_data):

    qr = QRCode.objects.get(id=qr_id)

    AnalyticsTracker(
        qr=qr,
        request_data=request_data
    ).process()