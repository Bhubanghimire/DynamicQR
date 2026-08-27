import re

from .base import BaseQRImporter
from ..models import QRCode, QRCodeData


class VCardImporter(BaseQRImporter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    required_columns = [
        "QrName",
        "FirstName",
        "LastName",
    ]

    def process_row(self, row, job, row_number):
        qr_name = row.get("QrName")
        first_name = row.get("FirstName")
        last_name = row.get("LastName")
        title = row.get("Title")
        company = row.get("Company")
        bio = row.get("Bio")
        avatar_url = row.get("AvatarUrl")
        cover_url = row.get("CoverUrl")
        theme_id = row.get("ThemeId")
        button_color = row.get("ButtonColor")
        button_corners = row.get("ButtonCorners")

        if not qr_name:
            raise ValueError("QrName is required.")

        if not first_name:
            raise ValueError("FirstName is required.")

        if not last_name:
            raise ValueError("LastName is required.")

        item_pattern = re.compile(r"^Item(\d+)(Type|Title|Value|OrderNo)$")
        grouped_items = {}
        for key, value in row.items():
            if key is None:
                continue
            match = item_pattern.match(str(key))
            if not match:
                continue
            index = int(match.group(1))
            field_name = match.group(2)
            grouped_items.setdefault(index, {})[field_name] = value

        items = []
        for index in sorted(grouped_items):
            item = grouped_items[index]
            item_type = item.get("Type")
            item_title = item.get("Title")
            item_value = item.get("Value")
            item_order_no = item.get("OrderNo")

            if (
                item_type in (None, "")
                and item_title in (None, "")
                and item_value in (None, "")
                and item_order_no in (None, "")
            ):
                continue

            if not item_type:
                raise ValueError(f"Item{index}Type is required.")

            if not item_title:
                raise ValueError(f"Item{index}Title is required.")

            if not item_value:
                raise ValueError(f"Item{index}Value is required.")

            try:
                parsed_order_no = int(item_order_no) if item_order_no not in (None, "") else index
            except (TypeError, ValueError):
                raise ValueError(f"Item{index}OrderNo must be an integer.")

            items.append(
                {
                    "id": f"vc-item-{index}",
                    "type": item_type,
                    "order_no": parsed_order_no,
                    "title": item_title,
                    "value": item_value,
                }
            )

        if not items:
            raise ValueError("At least one contact item is required.")

        qr_type = job.qr_type

        qr = QRCode.objects.create(
            name=qr_name,
            qr_type=qr_type,
            created_by=job.user,
            project=job.project,
        )

        content_json = {
            "first_name": first_name,
            "last_name": last_name,
            "title": title or "",
            "company": company or "",
            "bio": bio or "",
            "avatar_url": avatar_url or "",
            "cover_url": cover_url or "",
            "theme_id": theme_id or "vcard-centered-grid",
            "button_color": button_color or "#009DE2",
            "button_corners": button_corners or "rounded",
            "items": items,
        }

        QRCodeData.objects.create(
            qr_code=qr,
            content_json=content_json,
        )

