import re

from .base import BaseQRImporter
from ..models import QRCode, QRCodeData


class SocialMediaImporter(BaseQRImporter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    required_columns = [
        "QrName",
    ]

    def process_row(self, row, job, row_number):
        qr_name = row.get("QrName")
        header_image = row.get("HeaderImage")
        display_name = row.get("DisplayName")
        bio = row.get("Bio")
        is_multiple = row.get("IsMultiple")
        platform = row.get("Platform")
        profile_url = row.get("ProfileUrl")
        fallback_url = row.get("FallbackUrl")
        theme_id = row.get("ThemeId")
        button_color = row.get("ButtonColor")
        button_corners = row.get("ButtonCorners")

        if not qr_name:
            raise ValueError("QrName is required.")

        def as_bool(value):
            if isinstance(value, bool):
                return value
            if value is None:
                return False
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "y", "on"}
            return bool(value)

        item_pattern = re.compile(r"^Social(\d+)(Type|Title|Url|Value|Platform|OrderNo)$")
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
            item_url = item.get("Url")
            item_value = item.get("Value")
            item_platform = item.get("Platform")
            item_order_no = item.get("OrderNo")

            if (
                item_type in (None, "")
                and item_title in (None, "")
                and item_url in (None, "")
                and item_value in (None, "")
                and item_platform in (None, "")
                and item_order_no in (None, "")
            ):
                continue

            if not item_type:
                raise ValueError(f"Social{index}Type is required.")

            if not item_title:
                raise ValueError(f"Social{index}Title is required.")

            if item_url in (None, "") and item_value in (None, ""):
                raise ValueError(f"Social{index}Url or Social{index}Value is required.")

            try:
                parsed_order_no = int(item_order_no) if item_order_no not in (None, "") else index
            except (TypeError, ValueError):
                raise ValueError(f"Social{index}OrderNo must be an integer.")

            social_item = {
                "id": f"social-{index}",
                "type": item_type,
                "order_no": parsed_order_no,
                "title": item_title,
            }

            if item_url not in (None, ""):
                social_item["url"] = item_url

            if item_value not in (None, ""):
                social_item["value"] = item_value

            if item_platform not in (None, ""):
                social_item["platform"] = item_platform

            items.append(social_item)

        qr_type = job.qr_type

        qr = QRCode.objects.create(
            name=qr_name,
            qr_type=qr_type,
            created_by=job.user,
            project=job.project,
        )

        QRCodeData.objects.create(
            qr_code=qr,
            content_json={
                "header_image": header_image or "/media/header.png",
                "display_name": display_name or "",
                "bio": bio or "",
                "is_multiple": as_bool(is_multiple),
                "platform": platform or "instagram",
                "profile_url": profile_url or "",
                "fallback_url": fallback_url or "",
                "theme_id": theme_id or "social-1",
                "button_color": button_color or "#009DE2",
                "button_corners": button_corners or "rounded",
                "items": items,
            },
        )
        self.create_design(qr, job)


WiFiImporter = SocialMediaImporter
