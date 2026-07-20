# analytics/services/user_agent_parser.py

from user_agents import parse

from analytics.dto import ScanContext


class UserAgentParser:

    def __init__(self, context: ScanContext):
        self.context = context

    def parse(self):

        ua_string = self.context.user_agent

        if not ua_string:
            return

        ua = parse(ua_string)

        # Browser
        self.context.browser = ua.browser.family or ""
        self.context.browser_version = ".".join(
            map(str, ua.browser.version)
        )

        # Operating System
        self.context.os = ua.os.family or ""
        self.context.os_version = ".".join(
            map(str, ua.os.version)
        )

        # Device
        self.context.device_brand = ua.device.brand or ""
        self.context.device_model = ua.device.model or ""

        # Device Type
        if ua.is_mobile:
            self.context.device_type = "Mobile"

        elif ua.is_tablet:
            self.context.device_type = "Tablet"

        elif ua.is_pc:
            self.context.device_type = "Desktop"

        elif ua.is_bot:
            self.context.device_type = "Bot"

        else:
            self.context.device_type = "Other"

        self.context.is_bot = ua.is_bot