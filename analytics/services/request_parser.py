from analytics.dto import ScanContext


class RequestParser:

    def __init__(self, context: ScanContext):

        self.context = context

    def parse(self):

        request = self.context.request_data

        self.context.ip_address = request.get("ip", "")

        self.context.user_agent = request.get("user_agent", "")

        self.context.referer = request.get("referer", "")

        self.context.language = request.get("language", "")