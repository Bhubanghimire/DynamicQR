import re

from .base import BaseQRImporter
from ..models import QRCode, QRCodeData


class VideoImporter(BaseQRImporter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    required_columns = [
        "QrName",
        "page_title",
    ]

    def process_row(self, row, job, row_number):
        qr_name = row.get("QrName")
        page_title = row.get("page_title")

        if not qr_name:
            raise ValueError("QrName is required.")

        if not page_title:
            raise ValueError("page_title is required.")

        def parse_int(value, field_name):
            if value in (None, ""):
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                raise ValueError(f"{field_name} must be an integer.")

        item_pattern = re.compile(
            r"^Video(\d+)(Title|Description|Url|VideoUrl|Thumbnail|Duration|InputType|OrderNo|VideoId)$"
        )
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
            title = item_data.get("Title")
            description = item_data.get("Description")
            url = item_data.get("Url")
            video_url = item_data.get("VideoUrl")
            thumbnail = item_data.get("Thumbnail")
            duration = parse_int(item_data.get("Duration"), f"Video{item_no}Duration")
            input_type = item_data.get("InputType")
            order_no = parse_int(item_data.get("OrderNo"), f"Video{item_no}OrderNo") or item_no
            video_id = item_data.get("VideoId")

            if not title:
                raise ValueError(f"Video{item_no}Title is required.")

            if not url and not video_url:
                raise ValueError(f"Video{item_no}Url or Video{item_no}VideoUrl is required.")

            item = {
                "id": f"video-{item_no}",
                "input_type": input_type or "video-url",
                "url": url or video_url,
                "video_url": video_url or url,
                "order_no": order_no,
                "title": title,
            }
            if description:
                item["description"] = description
            if thumbnail:
                item["thumbnail"] = thumbnail
            if duration is not None:
                item["duration"] = duration
            if video_id:
                item["video_id"] = video_id

            items.append(item)

        if not items:
            raise ValueError("At least one video item is required.")

        qr = QRCode.objects.create(
            name=qr_name,
            qr_type=job.qr_type,
            created_by=job.user,
            project=job.project,
        )
        playlist_id = f"playlist-{qr.id + 12}"

        QRCodeData.objects.create(
            qr_code=qr,
            content_json={
                "open_mode": "landing-page-with-player",
                "page_title": page_title,
                "playlist_id": playlist_id,
                "items": items,
                "page_style": {
                    "theme": "video-1",
                    "color": "#009DE2",
                    "corner_style": "sharp",
                },
            },
        )
        self.create_design(qr, job)
