from .base import BaseQRImporter
from ..models import QRCode, QRCodeData
import re


class PDFImporter(BaseQRImporter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    required_columns = [
        "QrName",
        "PageTitle",
    ]

    def process_row(self, row, job, row_number):
        qr_name = row.get("QrName")
        page_title = row.get("PageTitle")

        pdf1_name = row.get("Pdf1Name")
        pdf1_title = row.get("Pdf1Title")
        pdf1_description = row.get("Pdf1Description")

        pdf2_name = row.get("Pdf2Name")
        pdf2_title = row.get("Pdf2Title")
        pdf2_description = row.get("Pdf2Description")

        page_subtitle = row.get("PageSubtitle")
        cover_image = row.get("CoverImage")
        theme_id = row.get("ThemeId")
        bg_color = row.get("BgColor")
        button_color = row.get("ButtonColor")
        button_corners = row.get("ButtonCorners")

        if not qr_name:
            raise ValueError("QrName is required.")

        if not page_title:
            raise ValueError("PageTitle is required.")

        item_pattern = re.compile(r"^Pdf(\d+)(Name|Title|Description)$")
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
            pdf_name = item.get("Name")
            pdf_title = item.get("Title")
            pdf_description = item.get("Description")

            if pdf_name in (None, "") and pdf_title in (None, "") and pdf_description in (None, ""):
                continue

            if not pdf_name:
                raise ValueError(f"Pdf{index}Name is required.")

            if not pdf_title:
                raise ValueError(f"Pdf{index}Title is required.")

            if not pdf_description:
                raise ValueError(f"Pdf{index}Description is required.")

            items.append(
                {
                    "pdf_name": pdf_name,
                    "title": pdf_title,
                    "description": pdf_description,
                }
            )

        if not items:
            raise ValueError("At least one PDF item is required.")

        qr_type = job.qr_type

        qr = QRCode.objects.create(
            name=qr_name,
            qr_type=qr_type,
            created_by=job.user,
        )

        content_json = {
            "page_title": page_title,
            "theme_id": theme_id or "document-1",
            "bg_color": bg_color or "#F8FAFC",
            "button_color": button_color or "#2563EB",
            "button_corners": button_corners or "rounded",
            "items": items,
        }

        if page_subtitle:
            content_json["page_subtitle"] = page_subtitle

        if cover_image:
            content_json["cover_image"] = cover_image

        QRCodeData.objects.create(
            qr_code=qr,
            content_json=content_json,
        )


WiFiImporter = PDFImporter
