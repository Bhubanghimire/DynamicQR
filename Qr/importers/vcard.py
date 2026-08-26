from .base import BaseQRImporter
from ..models import QRCode, QRCodeData


class WiFiImporter(BaseQRImporter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    required_columns = [
        "QrName",
        "first_name",
        "last_name",
        "title",
        "company",
        "bio",
        "avatar_url",
        "cover_url",
        "theme_id",
    ]

    def process_row(self, row, job, row_number):
        qr_name = row.get("QrName")
        first_name = row.get("first_name")
        last_name = row.get("last_name")

        if not qr_name:
            raise ValueError("QrName is required.")

        if not first_name:
            raise ValueError("First name is required.")

        if not last_name:
            raise ValueError("Last name is required.")

        qr_type = job.qr_type

        qr= QRCode.objects.create(name=qr_name, qr_type=qr_type,created_by=job.user)
        QRCodeData.objects.create(qr_code=qr,
                                  content_json={
                                        "first_name": first_name,
                                        "last_name": last_name,
                                        "title": "Chief Technology Officer",
                                        "company": "Acme Corp",
                                        "bio": "Passionate about innovation and software craftsmanship.",
                                        "avatar_url": "/media/avatar.png",
                                        "cover_url": "/media/cover.jpg",
                                        "theme_id": "vcard-centered-grid",
                                        "button_color": "#009DE2",
                                        "button_corners": "rounded",
                                        "items": [
                                            {
                                            "id": "vc-item-1",
                                            "type": "phone",
                                            "order_no": 1,
                                            "title": "Mobile Phone",
                                            "value": "+19876543210"
                                            },
                                            {
                                            "id": "vc-item-2",
                                            "type": "email",
                                            "order_no": 2,
                                            "title": "Work Email",
                                            "value": "jane.smith@acme.com"
                                            }
                                        ]
                                        })