import re

from .base import BaseQRImporter
from ..models import QRCode, QRCodeData


class ProductImporter(BaseQRImporter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    required_columns = [
        "QrName",
    ]

    def process_row(self, row, job, row_number):
        qr_name = row.get("QrName")
        theme_id = row.get("ThemeId")
        bg_color = row.get("BgColor")
        button_color = row.get("ButtonColor")
        button_corners = row.get("ButtonCorners")
        page_title = row.get("PageTitle")

        if not qr_name:
            raise ValueError("QrName is required.")

        item_pattern = re.compile(
            r"^Product(\d+)(Name|Brand|Description|Availability|Label|ContactType|ContactValue|Image|DownloadCatalog)$"
        )
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
            product_name = item.get("Name")
            brand = item.get("Brand")
            description = item.get("Description")
            availability = item.get("Availability")
            label = item.get("Label")
            contact_type = item.get("ContactType")
            contact_value = item.get("ContactValue")
            image = item.get("Image")
            download_catalog = item.get("DownloadCatalog")

            if (
                product_name in (None, "")
                and brand in (None, "")
                and description in (None, "")
                and availability in (None, "")
                and label in (None, "")
                and contact_type in (None, "")
                and contact_value in (None, "")
                and image in (None, "")
                and download_catalog in (None, "")
            ):
                continue

            if not product_name:
                raise ValueError(f"Product{index}Name is required.")

            if not brand:
                raise ValueError(f"Product{index}Brand is required.")

            if not description:
                raise ValueError(f"Product{index}Description is required.")

            product_json = {
                "product_name": product_name,
                "brand": brand,
                "description": description,
            }

            if availability:
                product_json["availability"] = availability

            if label:
                product_json["label"] = label

            if contact_type:
                product_json["contact_type"] = contact_type

            if contact_value:
                product_json["contact_value"] = contact_value

            if image:
                product_json["image"] = image

            if download_catalog:
                product_json["download_catalog"] = download_catalog

            items.append(product_json)

        if not items:
            raise ValueError("At least one product item is required.")

        qr_type = job.qr_type

        qr = QRCode.objects.create(
            name=qr_name,
            qr_type=qr_type,
            created_by=job.user,
            project=job.project,
        )

        content_json = {
            "page_title": page_title or "Featured Products",
            "theme_id": theme_id or "product-1",
            "bg_color": bg_color or "#F8FAFC",
            "button_color": button_color or "#009DE2",
            "button_corners": button_corners or "sharp",
            "items": items,
        }

        QRCodeData.objects.create(
            qr_code=qr,
            content_json=content_json,
        )
        self.create_design(qr, job)
