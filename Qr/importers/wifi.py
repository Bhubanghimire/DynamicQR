from .base import BaseQRImporter
from ..models import QRCode


class WiFiImporter(BaseQRImporter):
    def __init__(self, *args, **kwargs):
        print("🔥 WiFiImporter initialized")
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
        print("it is created", qr)