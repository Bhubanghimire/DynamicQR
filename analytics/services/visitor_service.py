from django.db.models import F

from analytics.models import Visitor
from analytics.utils.fingerprint import FingerprintGenerator


class VisitorService:

    def __init__(self, context):

        self.context = context

    def process(self):

        fingerprint = FingerprintGenerator.generate(
            ip=self.context.ip_address,
            user_agent=self.context.user_agent,
            language=self.context.language,
        )

        self.context.fingerprint = fingerprint

        visitor, created = Visitor.objects.get_or_create(
            visitor_hash=fingerprint,
            defaults={
                "total_scans": 1
            }
        )

        if created:

            self.context.is_unique_scan = True

        else:

            self.context.is_unique_scan = False

            Visitor.objects.filter(
                pk=visitor.pk
            ).update(
                total_scans=F("total_scans") + 1
            )

            visitor.refresh_from_db()

        self.context.visitor = visitor