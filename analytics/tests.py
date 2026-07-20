from django.test import TestCase

# Create your tests here.
from analytics.dto import ScanContext
from analytics.services.geo_parser import GeoParser
from analytics.services.user_agent_parser import UserAgentParser

ctx = ScanContext(
    qr=None,  # Only for testing
    request_data={},
    user_agent="Mozilla/5.0 (Linux; Android 15; SM-S938B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.7204.101 Mobile Safari/537.36"
)

UserAgentParser(ctx).parse()

# print(ctx.browser)
# print(ctx.os)
# print(ctx.device_type)
# print(ctx.device_brand)
# print(ctx.device_model)

ctx = ScanContext(
    qr=None,
    request_data={}
)

ctx.ip_address = "27.34.65.150"

GeoParser(ctx).parse()

print(ctx.country)
print(ctx.city)
print(ctx.latitude)
print(ctx.longitude)