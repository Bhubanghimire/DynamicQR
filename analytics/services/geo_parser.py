# analytics/services/geo_parser.py
import traceback

import geoip2.database
from django.conf import settings

from analytics.dto import ScanContext


class GeoParser:

    _reader = None

    @classmethod
    def get_reader(cls):
        """
        Create the reader once and reuse it.
        """
        if cls._reader is None:
            cls._reader = geoip2.database.Reader(
                settings.GEOIP_DATABASE
            )

        return cls._reader

    def __init__(self, context: ScanContext):
        self.context = context

    def parse(self):

        ip = self.context.ip_address
        print("this is ip", ip)
        if not ip:
            return

        try:

            reader = self.get_reader()

            response = reader.city(ip)

            self.context.country = (
                response.country.name or ""
            )

            self.context.country_code = (
                response.country.iso_code or ""
            )

            self.context.region = (
                response.subdivisions.most_specific.name or ""
            )

            self.context.city = (
                response.city.name or ""
            )

            self.context.timezone = (
                response.location.time_zone or ""
            )

            self.context.latitude = (
                response.location.latitude
            )

            self.context.longitude = (
                response.location.longitude
            )

        except Exception:
            """
            Ignore lookup failures.

            Analytics should never fail because
            GeoIP failed.
            """
            print("error ")
            print("=" * 80)
            traceback.print_exc()
            print("=" * 80)