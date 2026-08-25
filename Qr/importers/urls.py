from .base import BaseQRImporter


class URLImporter(BaseQRImporter):

    required_columns = [
        "name",
        "url",
        "link_name",
    ]

    def process_row(
        self,
        row,
        job,
        row_number,
    ):
        name = row.get("name")
        url = row.get("url")
        link_name = row.get("link_name")

        if not name:
            raise ValueError(
                "Name is required."
            )

        if not url:
            raise ValueError(
                "URL is required."
            )

        # QR creation will be added here.
        #
        # QRCode(...)
        # QRCodeData(...)

        print(
            f"Importing URL row {row_number}: {url}"
        )