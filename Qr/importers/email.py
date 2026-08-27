from .base import BaseQRImporter
from ..models import QRCode, QRCodeData


class EmailImporter(BaseQRImporter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    required_columns = [
        "QrName",
        "email",
    ]

    def process_row(self, row, job, row_number):
        qr_name = row.get("QrName")
        email = row.get("email")
        cc = row.get("cc")
        subject = row.get("subject")
        pre_filled_message = row.get("pre_filled_message")

        if not qr_name:
            raise ValueError("QrName is required.")

        if not email:
            raise ValueError("email is required.")

        qr_type = job.qr_type

        qr = QRCode.objects.create(name=qr_name, qr_type=qr_type, created_by=job.user, project=job.project)
        content_json = {
            "email": f"{email}",
        }
        if cc:
            content_json["cc"] = f"{cc}"
        if subject:
            content_json["subject"] = f"{subject}"
        if pre_filled_message:
            content_json["pre_filled_message"] = f"{pre_filled_message}"

        QRCodeData.objects.create(
            qr_code=qr,
            content_json=content_json,
        )
