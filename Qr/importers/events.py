from .base import BaseQRImporter
from ..models import QRCode, QRCodeData
from datetime import date, datetime, time


class EventImporter(BaseQRImporter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    required_columns = [
        "QrName",
        "Title",
        "Description",
        "StartDate",
        "StartTime",
        "EndDate",
        "EndTime",
        "Address",
        "RegistrationUrl",
        "ButtonLabel",
    ]

    def process_row(self, row, job, row_number):
        qr_name = row.get("QrName")
        title = row.get("Title")
        description = row.get("Description")
        cover_image = row.get("CoverImage")
        is_multi_day = row.get("IsMultiDay")
        start_date = row.get("StartDate")
        start_time = row.get("StartTime")
        end_date = row.get("EndDate")
        end_time = row.get("EndTime")
        map_url = row.get("MapUrl")
        address = row.get("Address")
        organizer_logo = row.get("OrganizerLogo")
        organizer_info = row.get("OrganizerInfo")
        registration_url = row.get("RegistrationUrl")
        button_label = row.get("ButtonLabel")

        if not qr_name:
            raise ValueError("QrName is required.")

        if not title:
            raise ValueError("Title is required.")

        if not description:
            raise ValueError("Description is required.")

        if not start_date:
            raise ValueError("StartDate is required.")

        if not start_time:
            raise ValueError("StartTime is required.")

        if not end_date:
            raise ValueError("EndDate is required.")

        if not end_time:
            raise ValueError("EndTime is required.")

        if not address:
            raise ValueError("Address is required.")

        if not registration_url:
            raise ValueError("RegistrationUrl is required.")

        if not button_label:
            raise ValueError("ButtonLabel is required.")

        qr_type = job.qr_type

        def to_json_value(value):
            if isinstance(value, (datetime, date)):
                return value.isoformat()
            if isinstance(value, time):
                return value.isoformat()
            return value

        def as_bool(value):
            if isinstance(value, bool):
                return value
            if value is None:
                return False
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "y", "on"}
            return bool(value)

        qr = QRCode.objects.create(
            name=qr_name,
            qr_type=qr_type,
            created_by=job.user,
            project=job.project,
        )
        content_json = {
            "title": title,
            "description": description,
            "is_multi_day": as_bool(is_multi_day),
            "start_date": to_json_value(start_date),
            "start_time": to_json_value(start_time),
            "end_date": to_json_value(end_date),
            "end_time": to_json_value(end_time),
            "address": address,
            "registration_url": registration_url,
            "button_label": button_label,
            "theme_id": "event-1",
            "bg_color": "#F8FAFC",
            "button_color": "#009DE2",
            "button_corners": "rounded",
            "page_style": {
                "theme": "event-1",
                "color": "#009DE2",
                "corner_style": "rounded",
            },
        }

        if cover_image:
            content_json["cover_image"] = cover_image

        if map_url:
            content_json["map_url"] = map_url

        if organizer_logo:
            content_json["organizer_logo"] = organizer_logo

        if organizer_info:
            content_json["organizer_info"] = organizer_info

        QRCodeData.objects.create(
            qr_code=qr,
            content_json=content_json,
        )


# WiFiImporter = EventImporter


#  Required columns:

#   - QrName
#   - Title
#   - Description
#   - StartDate
#   - StartTime
#   - EndDate
#   - EndTime
#   - Address
#   - RegistrationUrl
#   - ButtonLabel

#   Optional columns:

#   - CoverImage
#   - IsMultiDay
#   - MapUrl
#   - OrganizerLogo
#   - OrganizerInfo
