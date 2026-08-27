from .base import BaseQRImporter
from ..models import QRCode, QRCodeData


class WhatsappImporter(BaseQRImporter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    required_columns = [
        "QrName",
        "phone_number",
        "pre_filled_message",
    ]

    def process_row(self, row, job, row_number):
        qr_name = row.get("QrName")
        phone_number = row.get("phone_number")
        pre_filled_message = row.get("pre_filled_message")

        if not qr_name:
            raise ValueError("QrName is required.")

        if not phone_number:
            raise ValueError("Phone number is required.")

        if not pre_filled_message:
            raise ValueError("Pre-filled message is required.")

        qr_type = job.qr_type

        qr= QRCode.objects.create(name=qr_name, qr_type=qr_type,created_by=job.user, project=job.project)
        QRCodeData.objects.create(qr_code=qr,
                                  content_json={
                                    "phone_number": f"{phone_number}",
                                    "pre_filled_message": f"{pre_filled_message}"
                                    })
        self.create_design(qr, job)
