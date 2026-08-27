from .base import BaseQRImporter
from ..models import QRCode, QRCodeData
import re


class LandingPageImporter(BaseQRImporter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    required_columns = [
        "QrName",
        "Title",
    ]

    def process_row(self, row, job, row_number):
        qr_name = row.get("QrName")
        title = row.get("Title")

        bg_color = row.get("BgColor")
        button_color = row.get("ButtonColor")
        theme_id = row.get("ThemeId")
        button_corners = row.get("ButtonCorners")

        if not qr_name:
            raise ValueError("QrName is required.")

        if not title:
            raise ValueError("Title is required.")

        def parse_int(value, field_name):
            if value in (None, ""):
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                raise ValueError(f"{field_name} must be an integer.")

        item_pattern = re.compile(r"^Item(\d+)(Title|Content|Url|Type|OrderNo)$")
        grouped_items = {}
        for key, value in row.items():
            match = item_pattern.match(key or "")
            if not match:
                continue
            item_no = int(match.group(1))
            field = match.group(2)
            grouped_items.setdefault(item_no, {})[field] = value

        items = []
        for item_no in sorted(grouped_items):
            item_data = grouped_items[item_no]
            title_value = item_data.get("Title")
            content_value = item_data.get("Content")
            url_value = item_data.get("Url")
            item_type = item_data.get("Type")
            order_no = parse_int(item_data.get("OrderNo"), f"Item{item_no}OrderNo") or item_no

            if not title_value:
                raise ValueError(f"Item{item_no}Title is required.")

            if not content_value and not url_value:
                raise ValueError(
                    f"Item{item_no}Content or Item{item_no}Url is required."
                )

            item = {
                "id": f"lp-item-{item_no}",
                "type": item_type or ("button" if url_value else "text"),
                "order_no": order_no,
                "title": title_value,
            }
            if content_value:
                item["content"] = content_value
            if url_value:
                item["url"] = url_value
            items.append(item)

        if not items:
            raise ValueError("At least one item is required.")

        qr_type = job.qr_type

        qr = QRCode.objects.create(
            name=qr_name,
            qr_type=qr_type,
            created_by=job.user,
            project=job.project,
        )

        content_json = {
            "title": title,
            "theme_id": theme_id or "modern-slate",
            "bg_color": bg_color or "#F8FAFC",
            "button_color": button_color or "#2563EB",
            "button_corners": button_corners or "rounded",
            "items": items,
        }

        QRCodeData.objects.create(
            qr_code=qr,
            content_json=content_json,
        )


# Required:
#   QrName,Title
#
# Item columns are parsed dynamically:
#   Item1Title, Item1Content or Item1Url, Item1Type, Item1OrderNo
#   Item2Title, Item2Content or Item2Url, Item2Type, Item2OrderNo
#   ...
