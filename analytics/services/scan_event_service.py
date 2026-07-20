from analytics.models import ScanEvent
from django.utils import timezone



class ScanEventService:

    def __init__(self, context):
        self.context = context

    def create(self):

        scan_event = ScanEvent.objects.create(

            qr=self.context.qr,

            visitor=self.context.visitor,

            scanned_at=(
                    self.context.request_data.get("scanned_at")
                    or timezone.now()
            ),

            ip_address=self.context.ip_address,

            user_agent=self.context.user_agent,

            referer=self.context.referer,

            language=self.context.language,

            country=self.context.country,

            country_code=self.context.country_code,

            region=self.context.region,

            city=self.context.city,

            timezone=self.context.timezone,

            latitude=self.context.latitude,

            longitude=self.context.longitude,

            browser=self.context.browser,

            browser_version=self.context.browser_version,

            os=self.context.os,

            os_version=self.context.os_version,

            device_type=self.context.device_type,

            device_brand=self.context.device_brand,

            device_model=self.context.device_model,

            screen_width=self.context.screen_width,

            screen_height=self.context.screen_height,

            is_bot=self.context.is_bot,
        )

        self.context.scan_event = scan_event

        return scan_event