

from .base import BaseQRImporter
from ..models import QRCode, QRCodeData


class WiFiImporter(BaseQRImporter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    required_columns = [
        "QrName",
        "WifiName",
        "password",
    ]

    def process_row(self, row, job, row_number):
        qr_name = row.get("QrName")
        wifi_name = row.get("WifiName")
        password = row.get("password")

        if not qr_name:
            raise ValueError("QrName is required.")

        if not wifi_name:
            raise ValueError("WifiName is required.")

        if password is None or password == "":
            raise ValueError("password is required.")

        qr_type = job.qr_type

        qr= QRCode.objects.create(name=qr_name, qr_type=qr_type,created_by=job.user)
        QRCodeData.objects.create(qr_code=qr,
                                  content_json={
                                    "title": "Annual Tech Conference 2026",
                                    "cover_image": "/media/event-cover.png",
                                    "description": "Join us for keynotes and workshops.",
                                    "is_multi_day": true,
                                    "start_date": "15/09/2026",
                                    "start_time": "09:00 AM",
                                    "end_date": "17/09/2026",
                                    "end_time": "05:00 PM",
                                    "map_url": "https://maps.google.com/?q=Convention+Center",
                                    "address": "Convention Center, Grand Hall, City Center",
                                    "organizer_logo": "/media/organizer-logo.png",
                                    "organizer_info": "Tech Events Global Ltd.",
                                    "registration_url": "https://example.com/register",
                                    "button_label": "Register Now"
                                    }
        )

