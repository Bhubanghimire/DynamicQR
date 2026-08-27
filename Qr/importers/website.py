from .base import BaseQRImporter
from ..models import QRCode, QRCodeData


class WebsiteImporter(BaseQRImporter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    required_columns = [
        "QrName",
        "url",
    ]

    def process_row(self, row, job, row_number):
        qr_name = row.get("QrName")
        url = row.get("url")

        if not qr_name:
            raise ValueError("QrName is required.")

        if not url:
            raise ValueError("URL is required.")

        qr_type = job.qr_type

        qr= QRCode.objects.create(name=qr_name, qr_type=qr_type,created_by=job.user, project=job.project)
        QRCodeData.objects.create(qr_code=qr,
                                  content_json={"url": f"{url}"})
        self.create_design(qr, job)
