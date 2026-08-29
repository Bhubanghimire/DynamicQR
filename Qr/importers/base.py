class BaseQRImporter:

    required_columns = []

    def row_errors(self, row):
        return []

    def _missing(self, value):
        return value in (None, "")

    def add_required_error(self, errors, field_name, label=None):
        errors.append(f"{label or field_name} is required.")
        return errors

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

    def create_design(self, qr_code, job):
        design_data = getattr(job, "design_data", None)
        if not design_data:
            return None

        from ..models import QRDesign

        return QRDesign.objects.create(
            qr_code=qr_code,
            design_data=design_data,
        )
