from .base import BaseQRImporter
from ..models import QRCode, QRCodeData


class LandingPageImporter(BaseQRImporter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    required_columns = [
        "QrName",
        "Title",
        "Item1Title",
        "Item1Content",
        "Item2Title",
        "Item2Url",
    ]

    def process_row(self, row, job, row_number):
        qr_name = row.get("QrName")
        title = row.get("Title")

        item1_title = row.get("Item1Title")
        item1_content = row.get("Item1Content")
        item1_type = row.get("Item1Type")
        item1_order_no = row.get("Item1OrderNo")

        item2_title = row.get("Item2Title")
        item2_url = row.get("Item2Url")
        item2_type = row.get("Item2Type")
        item2_order_no = row.get("Item2OrderNo")

        bg_color = row.get("BgColor")
        button_color = row.get("ButtonColor")
        theme_id = row.get("ThemeId")
        button_corners = row.get("ButtonCorners")

        if not qr_name:
            raise ValueError("QrName is required.")

        if not title:
            raise ValueError("Title is required.")

        if not item1_title:
            raise ValueError("Item1Title is required.")

        if not item1_content:
            raise ValueError("Item1Content is required.")

        if not item2_title:
            raise ValueError("Item2Title is required.")

        if not item2_url:
            raise ValueError("Item2Url is required.")

        def parse_int(value, field_name):
            if value in (None, ""):
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                raise ValueError(f"{field_name} must be an integer.")

        qr_type = job.qr_type

        qr = QRCode.objects.create(
            name=qr_name,
            qr_type=qr_type,
            created_by=job.user,
        )

        content_json = {
            "title": title,
            "theme_id": theme_id or "modern-slate",
            "bg_color": bg_color or "#F8FAFC",
            "button_color": button_color or "#2563EB",
            "button_corners": button_corners or "rounded",
            "items": [
                {
                    "id": "lp-item-1",
                    "type": item1_type or "text",
                    "order_no": parse_int(item1_order_no, "Item1OrderNo") or 1,
                    "title": item1_title,
                    "content": item1_content,
                },
                {
                    "id": "lp-item-2",
                    "type": item2_type or "button",
                    "order_no": parse_int(item2_order_no, "Item2OrderNo") or 2,
                    "title": item2_title,
                    "url": item2_url,
                },
            ],
        }

        QRCodeData.objects.create(
            qr_code=qr,
            content_json=content_json,
        )


WiFiImporter = LandingPageImporter
#   QrName,Title,Item1Title,Item1Content,Item2Title,Item2Url,Item1Type,Item1OrderNo,Item2Type,Item2OrderNo,BgColor,ButtonColor,ThemeId,ButtonCorners
