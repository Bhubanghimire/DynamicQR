class BaseQRImporter:

    required_columns = []

    def validate_headers(self, headers):
        headers = {
            header.strip()
            for header in headers
            if header
        }

        missing_columns = set(
            self.required_columns
        ) - headers

        if missing_columns:
            raise ValueError(
                "Missing required columns: "
                + ", ".join(sorted(missing_columns))
            )

    def process_row(
        self,
        row,
        job,
        row_number,
    ):
        raise NotImplementedError