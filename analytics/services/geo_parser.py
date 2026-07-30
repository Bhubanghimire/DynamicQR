# analytics/services/geo_parser.py
import ipaddress
import logging

import geoip2.database
from geoip2.errors import AddressNotFoundError
from django.conf import settings

from analytics.dto import ScanContext


logger = logging.getLogger(__name__)


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
        if not ip:
            self._set_default_geo_context()
            return

        try:
            ip_obj = ipaddress.ip_address(ip)
        except ValueError:
            self._set_default_geo_context()
            return

        if any(
            [
                ip_obj.is_loopback,
                ip_obj.is_private,
                ip_obj.is_reserved,
                ip_obj.is_multicast,
                ip_obj.is_unspecified,
            ]
        ):
            self._set_default_geo_context()
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

        except AddressNotFoundError:
            self._set_default_geo_context()
        except Exception:
            logger.exception("Unexpected GeoIP lookup failure for IP %s", ip)

    def _set_default_geo_context(self):
        self.context.country = ""
        self.context.country_code = ""
        self.context.region = ""
        self.context.city = ""
        self.context.timezone = ""
        self.context.latitude = None
        self.context.longitude = None
