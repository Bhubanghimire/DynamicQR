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
                                    "page_title": "Company Documents & Brochure",
                                    "items": [
                                        {
                                        "id": "pdf-1",
                                        "url": "/media/documents/brochure.pdf",
                                        "pdf_name": "Company Brochure 2026",
                                        "order_no": 1,
                                        "title": "Annual Company Overview",
                                        "description": "Comprehensive document highlighting key achievements and services.",
                                        "pdf_id": "media-789"
                                        }
                                    ]
                                    }
        )






