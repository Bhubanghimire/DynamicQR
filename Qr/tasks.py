from celery import shared_task

from .models import QRImportJob


@shared_task
def process_qr_import(import_job_id):
    try:
        import_job = QRImportJob.objects.get(
            id=import_job_id
        )

        # Actual Excel processing will be implemented next.
        #
        # For now:
        #
        # 1. Read Excel
        # 2. Validate headers
        # 3. Validate maximum 100 rows
        # 4. Select QR-type importer
        # 5. Create QRCode
        # 6. Create QRCodeData
        # 7. Update progress

        print(
            f"Processing QR import job: {import_job.id}"
        )

    except QRImportJob.DoesNotExist:
        return