from .base import BaseQRImporter
from ..models import QRCode, QRCodeData


class GoogleMapImporter(BaseQRImporter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    required_columns = [
        "QrName",
        "title",
        "description",
        "map_url",
        "address",
    ]

    def process_row(self, row, job, row_number):
        errors = []
        qr_name = row.get("QrName")
        title = row.get("title")
        description = row.get("description")
        map_url = row.get("map_url")
        address = row.get("address")
        image = row.get("image")
        theme = row.get("theme")
        color = row.get("color")
        corner_style = row.get("corner_style")

        if not qr_name:
            errors.append("QrName is required.")
        if not title:
            errors.append("title is required.")
        if not description:
            errors.append("description is required.")
        if not map_url:
            errors.append("map_url is required.")
        if not address:
            errors.append("address is required.")
        if errors:
            raise ValueError(" | ".join(errors))

        qr = QRCode.objects.create(
            name=qr_name,
            qr_type=job.qr_type,
            created_by=job.user,
            project=job.project,
        )

        content_json = {
            "title": title,
            "description": description,
            "map_url": map_url,
            "address": address,
            "page_style": {
                "theme": theme or "gmaps-1",
                "color": color or "#009DE2",
                "corner_style": corner_style or "sharp",
            },
        }

        if image:
            content_json["image"] = image

        QRCodeData.objects.create(
            qr_code=qr,
            content_json=content_json,
        )
        self.create_design(qr, job)
