# analytics/services/tracker.py

import logging

from django.db import transaction
from rest_framework.exceptions import ValidationError

from analytics.dto import ScanContext
from Qr.models import QRScanSetting

from analytics.services.request_parser import RequestParser
from analytics.services.user_agent_parser import UserAgentParser
from analytics.services.geo_parser import GeoParser

from analytics.services.visitor_service import VisitorService
from analytics.services.scan_event_service import ScanEventService
from analytics.services.qr_summary_service import QRAnalyticsService
from analytics.services.analytics_time_service import AnalyticsTimeService
from analytics.services.analytics_dimension_service import AnalyticsDimensionService

logger = logging.getLogger(__name__)


class AnalyticsTracker:

    def __init__(self, qr, request_data):

        self.context = ScanContext(
            qr=qr,
            request_data=request_data,
        )

    def process(self, suppress_exceptions=True):

        try:

            #
            # Parse request
            #
            RequestParser(self.context).parse()

            #
            # Parse user agent
            #
            UserAgentParser(self.context).parse()

            #
            # Geo lookup
            #
            GeoParser(self.context).parse()

            #
            # Find/Create Visitor
            #
            VisitorService(self.context).process()

            self._enforce_scan_limit()

            #
            # Database Updates
            #
            with transaction.atomic():

                scan_event = ScanEventService(self.context).create()
                self.context.scan_event = scan_event

                QRAnalyticsService(self.context).update()
                AnalyticsTimeService(self.context).update()
                AnalyticsDimensionService(self.context).update()

        except Exception:

            if not suppress_exceptions:
                raise

            logger.exception("Analytics processing failed")

    def _enforce_scan_limit(self):
        scan_setting = QRScanSetting.objects.filter(
            qr_code=self.context.qr,
            is_scan_limit=True,
        ).first()

        if scan_setting is None or scan_setting.scan_limit is None:
            return

        if not self.context.visitor:
            return

        existing_scans = self.context.qr.scan_events.filter(visitor=self.context.visitor).count()
        if existing_scans >= scan_setting.scan_limit:
            raise ValidationError("Scan limit reached for this QR code.")
