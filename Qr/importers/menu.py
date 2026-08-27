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

        qr= QRCode.objects.create(name=qr_name, qr_type=qr_type,created_by=job.user, project=job.project)
        QRCodeData.objects.create(qr_code=qr,
                                  content_json={
                                                "title": "Gourmet Restaurant Menu",
                                                "theme_id": "classic-blue",
                                                "bg_color": "#F1F3F6",
                                                "button_color": "#009DE2",
                                                "button_corners": "sharp",
                                                "items": [
                                                    {
                                                    "id": "menu-item-1",
                                                    "type": "image",
                                                    "order_no": 1,
                                                    "url": "/media/menu-page-1.jpg",
                                                    "media_id": "media-101",
                                                    "alignment": "center",
                                                    "size": "big",
                                                    "shape": "circle",
                                                    "title": "Starters & Appetizers",
                                                    "email": "",
                                                    "phone_number": "",
                                                    "button_text": "",
                                                    "link_url": "",
                                                    "platform": "instagram"
                                                    }
                                                ]
                                                }
        )
        self.create_design(qr, job)


