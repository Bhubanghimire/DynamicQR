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
                                        "product_name": "Premium Wireless Headphones",
                                        "brand": "AudioTech",
                                        "description": "Noise-cancelling over-ear headphones with 30-hour battery life.",
                                        "images": [
                                            "/media/product-front.jpg",
                                            "/media/product-side.jpg"
                                        ],
                                        "availability": "in-stock",
                                        "label": "Buy Now",
                                        "contact_type": "email",
                                        "contact_value": "sales@audiotech.com",
                                        "download_catalog": "/media/catalog.pdf",
                                        "page_style": {
                                            "theme": "product-1",
                                            "color": "#009DE2",
                                            "corner_style": "sharp"
                                        }
                                        }
        )






