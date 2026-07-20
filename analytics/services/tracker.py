# analytics/services/tracker.py

import logging

from django.db import transaction

from analytics.dto import ScanContext

from analytics.services.request_parser import RequestParser
from analytics.services.user_agent_parser import UserAgentParser
from analytics.services.geo_parser import GeoParser

from analytics.services.visitor_service import VisitorService
from analytics.services.scan_event_service import ScanEventService
from analytics.services.qr_summary_service import QRSummaryService
from analytics.services.analytics_time_service import AnalyticsTimeService
from analytics.services.analytics_dimension_service import AnalyticsDimensionService

logger = logging.getLogger(__name__)


class AnalyticsTracker:

    def __init__(self, qr, request_data):

        self.context = ScanContext(
            qr=qr,
            request_data=request_data,
        )

    def process(self):

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

            #
            # Database Updates
            #
            with transaction.atomic():

                ScanEventService(self.context).create()

                QRSummaryService(self.context).update()

                AnalyticsTimeService(self.context).update()

                AnalyticsDimensionService(self.context).update()

        except Exception:

            logger.exception("Analytics processing failed")